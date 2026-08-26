import os
import json
import shutil
import subprocess
import base64
from time import perf_counter, sleep
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from helpers.app_settings import AppSettings
from helpers.board_stitcher import stitch_board_folder


AI_PYTHON = Path(__file__).resolve().parent.parent / ".venv313" / "Scripts" / "python.exe"
AI_CONFIG_DIR = Path(__file__).resolve().parent.parent
DEFAULT_AI_MODEL = Path(r"D:\SpeedEyeWoodTraining\runs\merged_tiled_continue_20260824\weights\best.onnx")
AI_HELPER = Path(__file__).resolve().parent.parent / "helpers" / "onnx_knot_detector.py"
LEGACY_AI_MODEL_MARKERS = (
    r"D:\SpeedEyeWoodTraining\runs\datasetV1_tiled_v1\weights\best.pt",
    r"D:\SpeedEyeWoodTraining\runs\knot_tiled_v1\weights\best.pt",
    r"D:\SpeedEyeWoodTraining\runs\knot_tiled_v1\weights\last.pt",
)


class StitchWorker(QObject):
    finished = Signal(object)
    log = Signal(str)
    error = Signal(str)
    ai_model_loaded = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self._settings = AppSettings()
        self._ai_load_error = ""
        self._loaded_model_path = None
        self._loaded_helper_signature = None
        self._loaded_model_signature = None
        self._ai_process = None

    @Slot()
    def initialize_ai(self):
        success, message = self._ensure_ai_model_loaded()
        if success:
            success, message = self._warmup_ai_model()
        self.ai_model_loaded.emit(success, message)

    @Slot(object)
    def process_request(self, request):
        try:
            folder_path = request["folder_path"]
            self._prepare_board_folder(request)
            scan_duration_ms = self._calculate_scan_duration_ms(
                folder_path=folder_path,
                ordered_filenames=[Path(path_text).name for path_text in request.get("source_paths", [])],
            )
            started_at = perf_counter()
            stitch_result = stitch_board_folder(
                folder_path,
                ordered_filenames=[Path(path_text).name for path_text in request.get("source_paths", [])],
                max_horizontal_shift_px=request["max_horizontal_shift_px"],
                left_edge_anchor_px=request["left_edge_anchor_px"],
                crop_x_margin_percent=request["crop_x_margin_percent"],
                crop_y_margin_percent=request["crop_y_margin_percent"],
                final_crop_x_margin_percent=request["final_crop_x_margin_percent"],
                active_threshold_percent=request["active_threshold_percent"],
                stitch_mode="ai_ready",
                preserve_vertical_span=bool(request.get("has_placeholder_images")),
                on_log=self.log.emit,
                return_metadata=True,
            )
            if isinstance(stitch_result, tuple):
                stitched_path, stitch_metadata = stitch_result
            else:
                stitched_path = stitch_result
                stitch_metadata = {}
            elapsed_ms = (perf_counter() - started_at) * 1000.0
            payload = dict(request)
            payload["stitched_path"] = stitched_path
            payload["elapsed_ms"] = elapsed_ms
            payload["stitch_metadata"] = stitch_metadata
            payload["scan_duration_ms"] = scan_duration_ms
            if request.get("ai_enabled", True):
                payload.update(
                    self._run_ai_detection(
                        stitched_path,
                        request["confidence_threshold"],
                        request.get("knot_confidence_threshold", request["confidence_threshold"]),
                    )
                )
            else:
                payload.update(
                    {
                        "annotated_path": stitched_path,
                        "defect_count": 0,
                        "boxes": [],
                        "inference_ms": 0.0,
                        "ai_available": False,
                        "ai_error": "",
                    }
                )
            self.finished.emit(payload)
        except Exception as exc:
            self.error.emit(str(exc))

    def _prepare_board_folder(self, request):
        source_paths = request.get("source_paths") or []
        if not source_paths:
            return

        destination_directory = Path(request["folder_path"])
        destination_directory.mkdir(parents=True, exist_ok=True)
        moved_count = 0

        for source_path_text in source_paths:
            source_path = Path(source_path_text)
            if not source_path.exists():
                continue
            destination_path = destination_directory / source_path.name
            if destination_path.exists():
                destination_path.unlink()
            try:
                source_path.replace(destination_path)
            except OSError:
                shutil.copy2(source_path, destination_path)
                self._delete_source_path_with_retries(source_path)
            moved_count += 1

        for source_path_text in source_paths:
            self._delete_source_path_with_retries(Path(source_path_text))

        if moved_count:
            self.log.emit(
                f"Przeniesiono {moved_count} zdjec do folderu {destination_directory.name}"
            )

    def _calculate_scan_duration_ms(self, folder_path, ordered_filenames):
        folder = Path(folder_path)
        timestamps = []
        for filename in ordered_filenames or []:
            image_path = folder / filename
            if not image_path.exists():
                continue
            try:
                timestamps.append(image_path.stat().st_mtime_ns)
            except OSError:
                continue
        if len(timestamps) < 2:
            return 0.0
        return max(0.0, (max(timestamps) - min(timestamps)) / 1_000_000.0)

    def _delete_source_path_with_retries(self, source_path, attempts=10, delay_seconds=0.1):
        source_path = Path(source_path)
        for attempt in range(attempts):
            if not source_path.exists():
                return True
            try:
                source_path.unlink()
                return True
            except OSError:
                if attempt == attempts - 1:
                    return False
                sleep(delay_seconds)
        return False

    def _run_ai_detection(self, stitched_path, confidence_threshold, knot_confidence_threshold):
        default_payload = {
            "annotated_path": stitched_path,
            "defect_count": 0,
            "boxes": [],
            "ai_available": False,
            "ai_error": "",
            "inference_ms": 0.0,
        }
        if stitched_path is None:
            return default_payload

        stitched_path = Path(stitched_path)
        if not self._wait_for_image_ready(stitched_path):
            default_payload["ai_error"] = "Obraz stitched.bmp nie jest gotowy do inferencji AI"
            return default_payload
        success, _ = self._ensure_ai_model_loaded()
        if not success:
            default_payload["ai_error"] = self._ai_load_error
            return default_payload

        annotated_path = stitched_path.with_name("stitched_annotated.bmp")
        try:
            response = self._send_ai_request(
                {
                    "image": str(stitched_path),
                    "output": str(annotated_path),
                    "conf": float(confidence_threshold),
                    "min_confidence": float(knot_confidence_threshold),
                },
                timeout_seconds=180,
            )
            if not response.get("ok"):
                raise RuntimeError(response.get("error") or "Helper AI zwrocil blad")
            result = response["result"]
            result["ai_available"] = True
            result["ai_error"] = ""
            return result
        except Exception as exc:
            default_payload["ai_error"] = str(exc)
            return default_payload

    def _ensure_ai_model_loaded(self):
        model_path = self._get_configured_ai_model_path()
        if not AI_PYTHON.exists() or not model_path.exists() or not AI_HELPER.exists():
            self._ai_load_error = "Brak interpretera AI, helpera lub modelu AI"
            return False, self._ai_load_error
        helper_signature = self._get_file_signature(AI_HELPER)
        model_signature = self._get_file_signature(model_path)
        if (
            self._loaded_model_path == model_path
            and self._loaded_helper_signature == helper_signature
            and self._loaded_model_signature == model_signature
            and self._is_ai_process_running()
        ):
            self._ai_load_error = ""
            return True, "Model AI gotowy"

        self._stop_ai_process()
        try:
            self._start_ai_process(model_path)
        except Exception as exc:
            self._ai_load_error = f"Nie udalo sie uruchomic helpera AI: {exc}"
            self._stop_ai_process()
            return False, self._ai_load_error

        self._ai_load_error = ""
        self._loaded_model_path = model_path
        self._loaded_helper_signature = helper_signature
        self._loaded_model_signature = model_signature
        return True, "Model AI gotowy"

    def _warmup_ai_model(self):
        model_path = self._get_configured_ai_model_path()
        if not AI_PYTHON.exists() or not model_path.exists() or not AI_HELPER.exists():
            return False, "Brak interpretera AI, helpera lub modelu AI"

        try:
            response = self._send_ai_request(
                {
                    "mode": "detect_boxes",
                    "image_base64": self._build_warmup_image_base64(),
                    "conf": 0.45,
                    "min_confidence": 0.35,
                },
                timeout_seconds=120,
            )
            if not response.get("ok"):
                return False, response.get("error") or "Warm-up AI nie potwierdzil gotowosci"
            return True, "Model AI zaladowany i rozgrzany"
        except Exception as exc:
            return False, f"Warm-up AI nieudany: {exc}"

    def _get_configured_ai_model_path(self):
        configured_path = self._settings.get("ai_model_path", "").strip()
        if configured_path:
            normalized_configured_path = str(Path(configured_path))
            if normalized_configured_path in LEGACY_AI_MODEL_MARKERS:
                self._settings.set("ai_model_path", "")
                return DEFAULT_AI_MODEL
            configured_model = Path(configured_path)
            if configured_model.exists():
                return configured_model
        return DEFAULT_AI_MODEL

    def _stop_ai_process(self):
        if self._ai_process is not None:
            try:
                if self._ai_process.stdin is not None:
                    self._ai_process.stdin.close()
            except Exception:
                pass
            try:
                if self._ai_process.poll() is None:
                    self._ai_process.terminate()
                    self._ai_process.wait(timeout=5)
            except Exception:
                try:
                    self._ai_process.kill()
                except Exception:
                    pass
            self._ai_process = None
        self._loaded_model_path = None
        self._loaded_helper_signature = None
        self._loaded_model_signature = None

    def _build_ai_serve_command(self, model_path):
        return [
            str(AI_PYTHON),
            str(AI_HELPER),
            "--model",
            str(model_path),
            "--serve",
        ]

    def _build_warmup_image_base64(self):
        import cv2
        import numpy as np

        image = np.zeros((768, 1536, 3), dtype=np.uint8)
        success, encoded = cv2.imencode(".png", image)
        if not success:
            raise RuntimeError("Nie udalo sie zakodowac obrazu warm-up")
        return base64.b64encode(encoded.tobytes()).decode("ascii")

    def _is_ai_process_running(self):
        return self._ai_process is not None and self._ai_process.poll() is None

    def _start_ai_process(self, model_path):
        environment = dict(os.environ)
        environment["YOLO_CONFIG_DIR"] = str(AI_CONFIG_DIR)
        command = self._build_ai_serve_command(model_path)
        self._ai_process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=environment,
            cwd=str(AI_CONFIG_DIR),
        )
        self._wait_for_ai_ready(timeout_seconds=120)

    def _wait_for_ai_ready(self, timeout_seconds):
        deadline = perf_counter() + timeout_seconds
        last_nonempty_line = ""
        while perf_counter() < deadline:
            remaining_seconds = max(0.1, deadline - perf_counter())
            line = self._read_ai_stdout_line(timeout_seconds=remaining_seconds)
            if not line:
                continue
            if line == "READY":
                return
            last_nonempty_line = line
        raise RuntimeError(
            f"Helper AI nie zglosil gotowosci: {last_nonempty_line or 'brak odpowiedzi'}"
        )

    def _read_ai_stdout_line(self, timeout_seconds):
        if not self._is_ai_process_running() or self._ai_process.stdout is None:
            raise RuntimeError("Proces helpera AI nie jest uruchomiony")

        import threading

        result = {"line": None, "error": None}

        def _reader():
            try:
                result["line"] = self._ai_process.stdout.readline()
            except Exception as exc:
                result["error"] = exc

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()
        reader_thread.join(timeout_seconds)
        if reader_thread.is_alive():
            raise TimeoutError("Przekroczono czas oczekiwania na odpowiedz helpera AI")
        if result["error"] is not None:
            raise result["error"]
        line = result["line"]
        if line is None:
            raise RuntimeError("Helper AI nie zwrocil odpowiedzi")
        return line.strip()

    def _send_ai_request(self, payload, timeout_seconds):
        if not self._is_ai_process_running():
            raise RuntimeError("Proces helpera AI nie jest uruchomiony")
        if self._ai_process.stdin is None:
            raise RuntimeError("Brak kanalu stdin helpera AI")

        try:
            self._ai_process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._ai_process.stdin.flush()
            return self._read_ai_json_response(timeout_seconds)
        except Exception:
            self._stop_ai_process()
            raise

    def _read_ai_json_response(self, timeout_seconds):
        deadline = perf_counter() + timeout_seconds
        last_nonempty_line = ""
        while perf_counter() < deadline:
            remaining_seconds = max(0.1, deadline - perf_counter())
            response_line = self._read_ai_stdout_line(remaining_seconds)
            if not response_line:
                continue
            last_nonempty_line = response_line
            try:
                response = json.loads(response_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(response, dict):
                raise RuntimeError("Helper AI zwrocil niepoprawny format odpowiedzi")
            return response
        raise RuntimeError(
            f"Helper AI nie zwrocil poprawnego JSON: {last_nonempty_line or 'brak odpowiedzi'}"
        )

    def _wait_for_image_ready(self, image_path, timeout_seconds=5.0, stable_reads_required=3):
        try:
            import cv2
        except Exception:
            return image_path.exists()

        deadline = perf_counter() + timeout_seconds
        previous_size = None
        stable_reads = 0

        while perf_counter() < deadline:
            if not image_path.exists():
                sleep(0.1)
                continue

            try:
                current_size = image_path.stat().st_size
            except OSError:
                sleep(0.1)
                continue

            image = cv2.imread(str(image_path))
            if image is None or image.size == 0:
                stable_reads = 0
                previous_size = current_size
                sleep(0.1)
                continue

            if current_size == previous_size:
                stable_reads += 1
            else:
                stable_reads = 1
                previous_size = current_size

            if stable_reads >= stable_reads_required:
                return True

            sleep(0.1)

        return False

    def _get_file_signature(self, path):
        try:
            stat = Path(path).stat()
            return (stat.st_mtime_ns, stat.st_size)
        except Exception:
            return None

    @Slot()
    def shutdown(self):
        self._stop_ai_process()
