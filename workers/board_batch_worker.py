from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


class BoardBatchWorker(QObject):
    board_context_updated = Signal(object)
    image_event = Signal(object)
    board_image_ready = Signal(object)
    waiting_for_images = Signal(object)
    stitch_job_ready = Signal(object)
    log = Signal(str)

    def __init__(self):
        super().__init__()
        self._scanner_active = False
        self._pending_image_paths = deque()
        self._pending_board_batches = deque()

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
        self._pending_image_paths.append(image_path)
        summary = self._build_pending_batches_summary()
        self.image_event.emit(
            {
                "file_path": str(image_path),
                "metadata": dict(metadata or {}),
                "summary": summary,
            }
        )
        self._process_pending_board_batches()

    def _process_pending_board_batches(self):
        while self._pending_board_batches:
            batch = self._pending_board_batches[0]
            expected_count = batch["photo_count"]
            while batch["assigned_count"] < expected_count and self._pending_image_paths:
                image_path = self._pending_image_paths.popleft()
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
                }
            )

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
