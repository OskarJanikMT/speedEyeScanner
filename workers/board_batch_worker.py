from collections import deque
from datetime import datetime
from pathlib import Path
from time import perf_counter

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QColor, QImage

from helpers.app_settings import AppSettings


DEFAULT_PLACEHOLDER_WIDTH_PX = 2000
DEFAULT_PLACEHOLDER_HEIGHT_PX = 976


class BoardBatchWorker(QObject):
    board_context_updated = Signal(object)
    image_event = Signal(object)
    board_image_ready = Signal(object)
    waiting_for_images = Signal(object)
    stitch_job_ready = Signal(object)
    log = Signal(str)

    def __init__(self):
        super().__init__()
        self._settings = AppSettings()
        self._scanner_active = False
        self._pending_image_paths = deque()
        self._pending_board_batches = deque()
        self._last_image_width = DEFAULT_PLACEHOLDER_WIDTH_PX
        self._last_image_height = DEFAULT_PLACEHOLDER_HEIGHT_PX

    @Slot(bool)
    def set_scanner_active(self, active):
        self._scanner_active = bool(active)
        if not self._scanner_active:
            self._pending_image_paths.clear()
            self._pending_board_batches.clear()

    @Slot()
    def reset_state(self):
        self._pending_image_paths.clear()
        self._pending_board_batches.clear()

    @Slot(object)
    def handle_board_context(self, board_context):
        if not self._scanner_active:
            return

        self._process_pending_board_batches()
        self._finalize_incomplete_batches_with_placeholders()

        current_board_context = dict(board_context or {})
        board_id = current_board_context.get("board_id", "").strip()
        board_slot = current_board_context.get("board_slot", "").strip()
        length_mm = current_board_context.get("length_mm")
        photo_count = current_board_context.get("photo_count")
        normalized_photo_count = self._normalize_photo_count(photo_count)
        summary = self._build_pending_batches_summary()

        event = {
            "board_id": board_id,
            "board_slot": board_slot,
            "length_mm": length_mm,
            "photo_count": normalized_photo_count,
            "summary": summary,
        }
        self.board_context_updated.emit(event)

        if board_id and normalized_photo_count and normalized_photo_count > 0:
            self._pending_board_batches.append(
                {
                    "board_id": board_id,
                    "length_mm": length_mm,
                    "photo_count": normalized_photo_count,
                    "assigned_count": 0,
                    "source_files": [],
                    "received_at": datetime.now().isoformat(timespec="microseconds"),
                    "first_image_at": 0.0,
                    "last_image_at": 0.0,
                }
            )
            summary = self._build_pending_batches_summary()
            self.log.emit(
                f"Kolejka desek: dodano {board_id} oczekuje_na={normalized_photo_count} {summary}"
            )
            self._process_pending_board_batches()

    @Slot(str, object)
    def handle_camera_image_saved(self, file_path, metadata):
        if not self._scanner_active:
            return

        image_path = Path(file_path)
        self._last_image_width = max(1, int((metadata or {}).get("width") or self._last_image_width))
        self._last_image_height = max(1, int((metadata or {}).get("height") or self._last_image_height))
        self._pending_image_paths.append(image_path)
        summary = self._build_pending_batches_summary()
        self.image_event.emit(
            {
                "file_path": str(image_path),
                "metadata": dict(metadata or {}),
                "summary": summary,
                "is_placeholder": False,
            }
        )
        self._process_pending_board_batches()

    def _process_pending_board_batches(self):
        while self._pending_board_batches:
            batch = self._pending_board_batches[0]
            expected_count = batch["photo_count"]
            while batch["assigned_count"] < expected_count and self._pending_image_paths:
                image_path = self._pending_image_paths.popleft()
                assigned_at = perf_counter()
                if batch["first_image_at"] <= 0.0:
                    batch["first_image_at"] = assigned_at
                batch["last_image_at"] = assigned_at
                batch["source_files"].append(image_path)
                batch["assigned_count"] += 1
                self.board_image_ready.emit(
                    {
                        "board_id": batch["board_id"],
                        "length_mm": batch["length_mm"],
                        "file_path": str(image_path),
                        "image_index": batch["assigned_count"],
                        "image_count": expected_count,
                        "is_last_image": batch["assigned_count"] == expected_count,
                        "summary": self._build_pending_batches_summary(),
                        "is_placeholder": False,
                        "scan_started_at": batch["first_image_at"],
                        "scan_last_image_at": batch["last_image_at"],
                    }
                )

            if batch["assigned_count"] < expected_count:
                self.waiting_for_images.emit(
                    {
                        "board_id": batch["board_id"],
                        "missing_count": expected_count - batch["assigned_count"],
                        "summary": self._build_pending_batches_summary(),
                    }
                )
                break

            self._pending_board_batches.popleft()
            self.stitch_job_ready.emit(
                {
                    "board_id": batch["board_id"],
                    "length_mm": batch["length_mm"],
                    "image_count": len(batch["source_files"]),
                    "source_paths": [str(path) for path in batch["source_files"]],
                    "summary": self._build_pending_batches_summary(),
                    "has_placeholder_images": False,
                    "scan_started_at": batch["first_image_at"],
                    "scan_last_image_at": batch["last_image_at"],
                    "scan_duration_ms": self._calculate_scan_duration_ms(batch),
                }
            )

    def _finalize_incomplete_batches_with_placeholders(self):
        while self._pending_board_batches and self._pending_board_batches[0]["assigned_count"] < self._pending_board_batches[0]["photo_count"]:
            batch = self._pending_board_batches[0]
            missing_count = max(0, batch["photo_count"] - batch["assigned_count"])
            if missing_count <= 0:
                break

            self.log.emit(
                f"Brakujace zdjecia dla {batch['board_id']}: uzupelniam {missing_count} czarnymi placeholderami"
            )
            for _ in range(missing_count):
                placeholder_path = self._create_black_placeholder_image(
                    board_id=batch["board_id"],
                    image_index=batch["assigned_count"] + 1,
                )
                assigned_at = perf_counter()
                if batch["first_image_at"] <= 0.0:
                    batch["first_image_at"] = assigned_at
                batch["last_image_at"] = assigned_at
                batch["source_files"].append(placeholder_path)
                batch["assigned_count"] += 1
                self.board_image_ready.emit(
                    {
                        "board_id": batch["board_id"],
                        "length_mm": batch["length_mm"],
                        "file_path": str(placeholder_path),
                        "image_index": batch["assigned_count"],
                        "image_count": batch["photo_count"],
                        "is_last_image": batch["assigned_count"] == batch["photo_count"],
                        "summary": self._build_pending_batches_summary(),
                        "is_placeholder": True,
                        "scan_started_at": batch["first_image_at"],
                        "scan_last_image_at": batch["last_image_at"],
                    }
                )

            self._pending_board_batches.popleft()
            self.stitch_job_ready.emit(
                {
                    "board_id": batch["board_id"],
                    "length_mm": batch["length_mm"],
                    "image_count": len(batch["source_files"]),
                    "source_paths": [str(path) for path in batch["source_files"]],
                    "summary": self._build_pending_batches_summary(),
                    "has_placeholder_images": True,
                    "scan_started_at": batch["first_image_at"],
                    "scan_last_image_at": batch["last_image_at"],
                    "scan_duration_ms": self._calculate_scan_duration_ms(batch),
                }
            )

    def _create_black_placeholder_image(self, board_id, image_index):
        placeholder_root = self._get_camera_output_directory() / "_placeholders"
        placeholder_root.mkdir(parents=True, exist_ok=True)
        placeholder_path = placeholder_root / f"{self._sanitize_path_component(board_id)}_missing_{int(image_index):03d}.bmp"

        image = QImage(
            max(1, int(self._last_image_width or DEFAULT_PLACEHOLDER_WIDTH_PX)),
            max(1, int(self._last_image_height or DEFAULT_PLACEHOLDER_HEIGHT_PX)),
            QImage.Format.Format_RGB32,
        )
        image.fill(QColor(0, 0, 0))
        if not image.save(str(placeholder_path), "BMP"):
            raise RuntimeError(f"Nie udalo sie zapisac placeholdera: {placeholder_path}")
        return placeholder_path

    def _get_camera_output_directory(self):
        output_directory = self._settings.get("camera_output_directory", "").strip()
        if not output_directory:
            output_directory = self._settings.get("save_directory", "").strip()
        if not output_directory:
            output_directory = str(Path.cwd() / "scany")
        return Path(output_directory)

    def _sanitize_path_component(self, value):
        sanitized = str(value).strip()
        sanitized = "".join("_" if char in '<>:\"/\\|?*' else char for char in sanitized)
        sanitized = sanitized.rstrip(". ")
        return sanitized[:120] or "unknown_board"

    def _calculate_scan_duration_ms(self, batch):
        first_image_at = float(batch.get("first_image_at", 0.0) or 0.0)
        last_image_at = float(batch.get("last_image_at", 0.0) or 0.0)
        if first_image_at <= 0.0 or last_image_at <= 0.0:
            return 0.0
        return max(0.0, (last_image_at - first_image_at) * 1000.0)

    def _normalize_photo_count(self, value):
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return None
        return normalized if normalized > 0 else None

    def _build_pending_batches_summary(self):
        pending_boards = len(self._pending_board_batches)
        pending_photos = sum(
            max(0, batch.get("photo_count", 0) - batch.get("assigned_count", 0))
            for batch in self._pending_board_batches
        )
        buffered_photos = len(self._pending_image_paths)
        missing_photos = max(0, pending_photos - buffered_photos)
        return (
            f"| deski_w_kolejce={pending_boards} "
            f"zdjec_oczekiwanych={pending_photos} "
            f"zdjec_bufor={buffered_photos} "
            f"zdjec_brakuje={missing_photos}"
        )
