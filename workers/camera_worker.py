from PySide6.QtCore import QObject, Signal, Slot

from helpers.baumer_camera_manager import BaumerCameraManager, CameraSettings


class CameraWorker(QObject):
    started = Signal()
    stopped = Signal()
    error = Signal(str)
    log = Signal(str)
    camera_status_changed = Signal(str, bool)
    image_saved = Signal(str, dict)

    def __init__(self, settings: CameraSettings):
        super().__init__()
        self.settings = settings
        self.manager = None

    @Slot()
    def run(self):
        try:
            self.manager = BaumerCameraManager(
                settings=self.settings,
                on_log=self.log.emit,
                on_status_changed=self._handle_state_change,
                on_image_saved=self.image_saved.emit,
            )
            self.started.emit()
            self.manager.run_forever()
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.stopped.emit()

    @Slot()
    def stop(self):
        if self.manager is not None:
            self.manager.stop()

    def _handle_state_change(self, state: str):
        self.camera_status_changed.emit(
            state, state in {"CONNECTED", "ACQUIRING"}
        )
