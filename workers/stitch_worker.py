from time import perf_counter

from PySide6.QtCore import QObject, Signal, Slot

from helpers.board_stitcher import stitch_board_folder


class StitchWorker(QObject):
    finished = Signal(object)
    log = Signal(str)
    error = Signal(str)

    @Slot(object)
    def process_request(self, request):
        try:
            folder_path = request["folder_path"]
            started_at = perf_counter()
            stitched_path = stitch_board_folder(
                folder_path,
                max_horizontal_shift_px=request["max_horizontal_shift_px"],
                crop_x_margin_percent=request["crop_x_margin_percent"],
                crop_y_margin_percent=request["crop_y_margin_percent"],
                final_crop_x_margin_percent=request["final_crop_x_margin_percent"],
                active_threshold_percent=request["active_threshold_percent"],
                on_log=self.log.emit,
            )
            elapsed_ms = (perf_counter() - started_at) * 1000.0
            payload = dict(request)
            payload["stitched_path"] = stitched_path
            payload["elapsed_ms"] = elapsed_ms
            self.finished.emit(payload)
        except Exception as exc:
            self.error.emit(str(exc))
