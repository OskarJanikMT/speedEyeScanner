import json
import os
import subprocess
import base64
from collections import deque
from pathlib import Path
from time import perf_counter, sleep

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtGui import QColor, QImage, QPainter

from helpers.app_settings import AppSettings
from helpers.board_stitcher import crop_ai_ready_qimage, rotate_qimage_180


AI_PYTHON = Path(__file__).resolve().parent.parent / ".venv313" / "Scripts" / "python.exe"
AI_CONFIG_DIR = Path(__file__).resolve().parent.parent
DEFAULT_AI_MODEL = Path(__file__).resolve().parent.parent / "model" / "weights" / "best.pt"
AI_HELPER = Path(__file__).resolve().parent.parent / "helpers" / "onnx_knot_detector.py"
LEGACY_AI_MODEL_MARKERS = (
    r"D:\SpeedEyeWoodTraining\runs\datasetV1_tiled_v1\weights\best.pt",
    r"D:\SpeedEyeWoodTraining\runs\knot_tiled_v1\weights\best.pt",
    r"D:\SpeedEyeWoodTraining\runs\knot_tiled_v1\weights\last.pt",
)
MODEL_TILE_HEIGHT = 768


class BoardAnalysisWorker(QObject):
    finished = Signal(object)
    log = Signal(str)
    error = Signal(str)
    ai_model_loaded = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self._settings = AppSettings()
        self._ai_enabled = True
        self._ai_load_error = ""
        self._loaded_model_path = None
        self._loaded_helper_signature = None
        self._loaded_model_signature = None
        self._ai_process = None
        self._current_board = None
        self._pending_segments = deque()
        self._pending_height = 0

    @Slot()
    def initialize_ai(self):
        success, message = self._ensure_ai_model_loaded()
        if success:
            success, message = self._warmup_ai_model()
        self.ai_model_loaded.emit(success, message)

    @Slot(bool)
    def set_ai_enabled(self, enabled):
        self._ai_enabled = bool(enabled)

    @Slot(object)
    def handle_board_image(self, event):
        try:
            if not self._ai_enabled:
                return
            self._ensure_board_session(event)
            is_placeholder = bool(event.get("is_placeholder"))
            resolved_image_path = self._resolve_image_path_for_ai(event)
            image_edit_started_at = perf_counter()
            source_image = rotate_qimage_180(
                QImage(str(resolved_image_path)).convertToFormat(QImage.Format.Format_RGB32)
            )
            if source_image.isNull():
                raise RuntimeError(f"Nie mozna wczytac obrazu do AI: {resolved_image_path}")

            if not is_placeholder:
                _, crop_window = crop_ai_ready_qimage(
                    source_image,
                    crop_x_margin_percent=self._settings.get_int("board_stitch_crop_x_margin_percent", 4),
                    active_threshold_percent=self._settings.get_int("board_stitch_active_threshold_percent", 28),
                    left_edge_anchor_px=self._settings.get_int("board_stitch_left_edge_anchor_px", 100),
                )
                if crop_window is not None:
                    crop_left_px, crop_right_px = crop_window
                    self._current_board["stream_crop_left_px"] = (
                        crop_left_px
                        if self._current_board["stream_crop_left_px"] is None
                        else min(self._current_board["stream_crop_left_px"], crop_left_px)
                    )
                    self._current_board["stream_crop_right_px"] = (
                        crop_right_px
                        if self._current_board["stream_crop_right_px"] is None
                        else max(self._current_board["stream_crop_right_px"], crop_right_px)
                    )
            self._current_board["edit_ms"] += (perf_counter() - image_edit_started_at) * 1000.0

            self._pending_segments.append(source_image)
            self._pending_height += source_image.height()
            self._current_board["received_images"] = int(event.get("image_index", 0))
            self._drain_ready_tiles()
        except Exception as exc:
            self.error.emit(str(exc))

    def _resolve_image_path_for_ai(self, event, timeout_seconds=5.0):
        original_path = Path(event["file_path"])
        fallback_path = (
            self._get_camera_output_directory()
            / self._sanitize_path_component(event["board_id"])
            / original_path.name
        )
        deadline = perf_counter() + timeout_seconds
        while perf_counter() < deadline:
            for candidate in (original_path, fallback_path):
                if candidate.exists():
                    return str(candidate)
            sleep(0.05)
        return str(original_path if original_path.exists() else fallback_path)

    @Slot(object)
    def handle_board_completed(self, event):
        try:
            if not self._ai_enabled:
                self.finished.emit(
                    {
                        "board_id": str(event.get("board_id", "")).strip(),
                        "length_mm": event.get("length_mm"),
                        "image_count": int(event.get("image_count", 0) or 0),
                        "defect_count": 0,
                        "boxes": [],
                        "scan_duration_ms": float(event.get("scan_duration_ms", 0.0) or 0.0),
                        "inference_ms": 0.0,
                        "machine_ready_latency_ms": 0.0,
                        "edit_ms": 0.0,
                        "total_pipeline_ms": float(event.get("scan_duration_ms", 0.0) or 0.0),
                        "first_image_at": float(event.get("scan_started_at", 0.0) or 0.0),
                        "last_model_output_at": 0.0,
                        "image_height_px": 0,
                        "ai_available": False,
                        "ai_error": "",
                        "detections_path": "",
                    }
                )
                self._reset_board_session()
                return
            if self._current_board is None or self._current_board["board_id"] != event["board_id"]:
                return
            self._drain_ready_tiles(flush=True)
            ready_started_at = perf_counter()
            self._current_board["boxes"] = self._aggregate_stream_boxes(self._current_board["boxes"])
            vector_ready_at = perf_counter()
            result = {
                "board_id": self._current_board["board_id"],
                "length_mm": self._current_board["length_mm"],
                "image_count": self._current_board["image_count"],
                "defect_count": len(self._current_board["boxes"]),
                "boxes": self._current_board["boxes"],
                "scan_duration_ms": float(self._current_board.get("scan_duration_ms", 0.0) or 0.0),
                "inference_ms": self._current_board["inference_ms"],
                "machine_ready_latency_ms": 0.0,
                "edit_ms": float(self._current_board.get("edit_ms", 0.0) or 0.0),
                "total_pipeline_ms": 0.0,
                "first_image_at": float(self._current_board.get("first_image_at", 0.0) or 0.0),
                "last_model_output_at": float(self._current_board.get("last_model_output_at", 0.0) or 0.0),
                "image_height_px": self._current_board["image_height_px"],
                "image_width_px": self._current_board["image_width_px"],
                "stream_crop_left_px": self._current_board["stream_crop_left_px"],
                "stream_crop_right_px": self._current_board["stream_crop_right_px"],
                "ai_available": True,
                "ai_error": "",
                "detections_path": "",
            }
            last_model_output_at = float(result.get("last_model_output_at", 0.0) or 0.0)
            if last_model_output_at > 0.0:
                result["machine_ready_latency_ms"] = max(
                    0.0,
                    (vector_ready_at - last_model_output_at) * 1000.0,
                )
            first_image_at = float(result.get("first_image_at", 0.0) or 0.0)
            if first_image_at > 0.0:
                result["total_pipeline_ms"] = max(0.0, (vector_ready_at - first_image_at) * 1000.0)
            else:
                result["total_pipeline_ms"] = (
                    float(result.get("scan_duration_ms", 0.0) or 0.0)
                    + float(result.get("inference_ms", 0.0) or 0.0)
                    + float(result.get("machine_ready_latency_ms", 0.0) or 0.0)
                )
            self.finished.emit(result)
            self._reset_board_session()
        except Exception as exc:
            self.error.emit(str(exc))

    def _ensure_board_session(self, event):
        board_id = str(event.get("board_id", "")).strip()
        if not board_id:
            raise RuntimeError("Brak board_id dla streamingu AI")

        if self._current_board is not None and self._current_board["board_id"] != board_id:
            self._reset_board_session()

        if self._current_board is None:
            self._current_board = {
                "board_id": board_id,
                "length_mm": event.get("length_mm"),
                "image_count": int(event.get("image_count", 0) or 0),
                "received_images": 0,
                "image_height_px": 0,
                "image_width_px": 0,
                "tile_index": 0,
                "boxes": [],
                "scan_duration_ms": float(event.get("scan_duration_ms", 0.0) or 0.0),
                "first_image_at": float(event.get("scan_started_at", 0.0) or 0.0),
                "inference_ms": 0.0,
                "last_model_output_at": 0.0,
                "edit_ms": 0.0,
                "stream_crop_left_px": None,
                "stream_crop_right_px": None,
            }

    def _drain_ready_tiles(self, flush=False):
        while self._pending_height >= MODEL_TILE_HEIGHT or (flush and self._pending_height > 0):
            tile_height = MODEL_TILE_HEIGHT if self._pending_height >= MODEL_TILE_HEIGHT else self._pending_height
            tile_image = self._consume_tile_image(tile_height)
            self._run_tile_detection(tile_image)
            if not flush and self._pending_height < MODEL_TILE_HEIGHT:
                break

    def _consume_tile_image(self, tile_height):
        edit_started_at = perf_counter()
        slices = []
        remaining_height = tile_height
        max_width = 1

        while remaining_height > 0 and self._pending_segments:
            segment = self._pending_segments.popleft()
            if segment.height() <= remaining_height:
                slice_image = segment
                remaining_height -= segment.height()
            else:
                slice_image = segment.copy(0, 0, segment.width(), remaining_height)
                leftover = segment.copy(0, remaining_height, segment.width(), segment.height() - remaining_height)
                self._pending_segments.appendleft(leftover)
                remaining_height = 0
            slices.append(slice_image)
            max_width = max(max_width, slice_image.width())

        tile = QImage(max_width, tile_height, QImage.Format.Format_RGB32)
        tile.fill(QColor(0, 0, 0))
        painter = QPainter(tile)
        y_offset = 0
        for image in slices:
            painter.drawImage(0, y_offset, image)
            y_offset += image.height()
        painter.end()

        self._pending_height = max(0, self._pending_height - tile_height)
        if self._current_board is not None:
            self._current_board["edit_ms"] += (perf_counter() - edit_started_at) * 1000.0
        return tile

    def _run_tile_detection(self, tile_image):
        if self._current_board is None:
            return
        success, _ = self._ensure_ai_model_loaded()
        if not success:
            raise RuntimeError(self._ai_load_error or "Model AI nie jest gotowy")

        crop_left_px = int(self._current_board.get("stream_crop_left_px") or 0)
        crop_right_px = int(self._current_board.get("stream_crop_right_px") or tile_image.width())
        crop_left_px = max(0, min(tile_image.width() - 1, crop_left_px))
        crop_right_px = max(crop_left_px + 1, min(tile_image.width(), crop_right_px))
        edit_started_at = perf_counter()
        cropped_tile_image = tile_image.copy(crop_left_px, 0, crop_right_px - crop_left_px, tile_image.height())
        if cropped_tile_image.isNull():
            raise RuntimeError("Nie udalo sie przyciac gotowego tile AI")
        self._current_board["edit_ms"] += (perf_counter() - edit_started_at) * 1000.0

        tile_index = self._current_board["tile_index"]
        response = self._send_ai_request(
            {
                "mode": "detect_boxes",
                "image_base64": self._encode_qimage_to_base64(cropped_tile_image),
                "conf": float(self._settings.get_float("yolo_threshold", 0.25)),
                "min_confidence": float(self._settings.get_float("knot_confidence_threshold", 0.25)),
            },
            timeout_seconds=180,
        )
        if not response.get("ok"):
            raise RuntimeError(response.get("error") or "Helper AI zwrocil blad")

        result = response["result"]
        self._current_board["last_model_output_at"] = perf_counter()
        global_y_offset = self._current_board["image_height_px"]
        for box in result.get("boxes", []):
            self._current_board["boxes"].append(
                {
                    "x1": int(box.get("x1", 0)) + int(crop_left_px),
                    "y1": int(box.get("y1", 0)) + global_y_offset,
                    "x2": int(box.get("x2", 0)) + int(crop_left_px),
                    "y2": int(box.get("y2", 0)) + global_y_offset,
                    "confidence": float(box.get("confidence", 0.0)),
                    "tile_index": int(box.get("tile_index", tile_index)),
                }
            )
        self._current_board["inference_ms"] += float(result.get("inference_ms", 0.0))
        self._current_board["image_height_px"] += int(tile_image.height())
        self._current_board["image_width_px"] = max(
            int(self._current_board.get("image_width_px", 0) or 0),
            int(tile_image.width()),
        )
        self._current_board["tile_index"] += 1

    def _encode_qimage_to_base64(self, image):
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG"):
            raise RuntimeError("Nie udalo sie zakodowac obrazu tile do pamieci")
        return base64.b64encode(bytes(byte_array)).decode("ascii")

    def _aggregate_stream_boxes(self, boxes, iou_threshold=0.45, vertical_gap_px=12, x_overlap_ratio=0.55):
        normalized_boxes = []
        for box in boxes or []:
            x1 = int(box.get("x1", 0))
            y1 = int(box.get("y1", 0))
            x2 = int(box.get("x2", 0))
            y2 = int(box.get("y2", 0))
            if x2 <= x1 or y2 <= y1:
                continue
            normalized_boxes.append(
                {
                    **box,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "confidence": float(box.get("confidence", 0.0)),
                }
            )

        normalized_boxes.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
        aggregated = []

        for candidate in normalized_boxes:
            merged = False
            for existing in aggregated:
                if (
                    self._calculate_iou(existing, candidate) >= iou_threshold
                    or self._should_join_adjacent_boxes(
                        existing,
                        candidate,
                        max_vertical_gap_px=vertical_gap_px,
                        min_x_overlap_ratio=x_overlap_ratio,
                    )
                ):
                    existing["x1"] = min(existing["x1"], candidate["x1"])
                    existing["y1"] = min(existing["y1"], candidate["y1"])
                    existing["x2"] = max(existing["x2"], candidate["x2"])
                    existing["y2"] = max(existing["y2"], candidate["y2"])
                    existing["confidence"] = max(existing.get("confidence", 0.0), candidate.get("confidence", 0.0))
                    merged = True
                    break
            if not merged:
                aggregated.append(dict(candidate))

        aggregated.sort(key=lambda item: (item["y1"], item["x1"]))
        return aggregated

    def _calculate_iou(self, first, second):
        inter_x1 = max(first["x1"], second["x1"])
        inter_y1 = max(first["y1"], second["y1"])
        inter_x2 = min(first["x2"], second["x2"])
        inter_y2 = min(first["y2"], second["y2"])
        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0

        intersection = float((inter_x2 - inter_x1) * (inter_y2 - inter_y1))
        first_area = float((first["x2"] - first["x1"]) * (first["y2"] - first["y1"]))
        second_area = float((second["x2"] - second["x1"]) * (second["y2"] - second["y1"]))
        union = first_area + second_area - intersection
        if union <= 0.0:
            return 0.0
        return intersection / union

    def _should_join_adjacent_boxes(self, first, second, max_vertical_gap_px, min_x_overlap_ratio):
        vertical_gap = max(first["y1"], second["y1"]) - min(first["y2"], second["y2"])
        if vertical_gap < 0:
            vertical_gap = 0
        if vertical_gap > max_vertical_gap_px:
            return False

        overlap_x1 = max(first["x1"], second["x1"])
        overlap_x2 = min(first["x2"], second["x2"])
        if overlap_x2 <= overlap_x1:
            return False

        overlap_width = float(overlap_x2 - overlap_x1)
        smaller_width = min(
            float(first["x2"] - first["x1"]),
            float(second["x2"] - second["x1"]),
        )
        if smaller_width <= 0.0:
            return False
        return (overlap_width / smaller_width) >= min_x_overlap_ratio

    def _reset_board_session(self):
        self._current_board = None
        self._pending_segments.clear()
        self._pending_height = 0

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
        if not self._is_ai_process_running():
            return False, "Proces helpera AI nie jest uruchomiony"
        warmup_image = QImage(1536, 768, QImage.Format.Format_RGB32)
        warmup_image.fill(QColor(0, 0, 0))
        response = self._send_ai_request(
            {
                "mode": "detect_boxes",
                "image_base64": self._encode_qimage_to_base64(warmup_image),
                "conf": 0.45,
                "min_confidence": 0.35,
            },
            timeout_seconds=120,
        )
        if not response.get("ok"):
            return False, response.get("error") or "Warm-up AI nie potwierdzil gotowosci"
        return True, "Model AI zaladowany i rozgrzany"

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

    def _get_camera_output_directory(self):
        output_directory = self._settings.get("camera_output_directory", "").strip()
        if not output_directory:
            output_directory = self._settings.get("save_directory", "").strip()
        if not output_directory:
            output_directory = str(Path.cwd() / "scany")
        return Path(output_directory)

    def _sanitize_path_component(self, value):
        sanitized = str(value).strip()
        sanitized = "".join("_" if char in '<>:"/\\|?*' else char for char in sanitized)
        sanitized = sanitized.rstrip(". ")
        return sanitized[:120] or "unknown_board"

    def _build_ai_serve_command(self, model_path):
        return [
            str(AI_PYTHON),
            str(AI_HELPER),
            "--model",
            str(model_path),
            "--serve",
        ]

    def _is_ai_process_running(self):
        return self._ai_process is not None and self._ai_process.poll() is None

    def _start_ai_process(self, model_path):
        environment = dict(os.environ)
        environment["YOLO_CONFIG_DIR"] = str(AI_CONFIG_DIR)
        self._ai_process = subprocess.Popen(
            self._build_ai_serve_command(model_path),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
            if not self._is_ai_process_running():
                raise RuntimeError(self._get_ai_process_error())
            line = self._read_ai_stdout_line(max(0.1, deadline - perf_counter()))
            if not line:
                continue
            if line == "READY":
                return
            last_nonempty_line = line
        raise RuntimeError(f"Helper AI nie zglosil gotowosci: {last_nonempty_line or 'brak odpowiedzi'}")

    def _get_ai_process_error(self):
        if self._ai_process is None or self._ai_process.stderr is None:
            return "Proces helpera AI zakonczyl sie podczas uruchamiania"
        try:
            details = self._ai_process.stderr.read().strip()
        except Exception:
            details = ""
        return details or "Proces helpera AI zakonczyl sie podczas uruchamiania"

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
        if result["line"] is None:
            raise RuntimeError("Helper AI nie zwrocil odpowiedzi")
        return result["line"].strip()

    def _send_ai_request(self, payload, timeout_seconds):
        if not self._is_ai_process_running() or self._ai_process.stdin is None:
            raise RuntimeError("Proces helpera AI nie jest uruchomiony")
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
            response_line = self._read_ai_stdout_line(max(0.1, deadline - perf_counter()))
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
        raise RuntimeError(f"Helper AI nie zwrocil poprawnego JSON: {last_nonempty_line or 'brak odpowiedzi'}")

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

    def _get_file_signature(self, path):
        try:
            stat = Path(path).stat()
            return (stat.st_mtime_ns, stat.st_size)
        except Exception:
            return None

    @Slot()
    def shutdown(self):
        self._reset_board_session()
        self._stop_ai_process()
