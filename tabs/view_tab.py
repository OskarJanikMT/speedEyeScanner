from datetime import datetime
from pathlib import Path
from time import perf_counter

from PySide6.QtCore import QEvent, QPoint, QThread, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from helpers.app_settings import AppSettings
from helpers.baumer_camera_manager import CameraSettings
from workers.board_batch_worker import BoardBatchWorker
from workers.board_analysis_worker import BoardAnalysisWorker
from workers.camera_worker import CameraWorker
from workers.stitch_worker import StitchWorker
from workers.tcp_server_worker import TcpServerWorker
from widgets.status_indicator import StatusIndicator
from widgets.cut_plan_bar import CutPlanBar


DERIVED_STITCH_FILES = {
    "stitched.bmp",
    "stitched_annotated.bmp",
    "stitched_knots.json",
    "ai_warmup.bmp",
    "ai_warmup_out.bmp",
    "ai_debug_run.json",
}


def format_detection_confidence(confidence):
    if confidence >= 0.1:
        return f"{confidence:.2f}"
    if confidence >= 0.01:
        return f"{confidence:.3f}"
    return f"{confidence:.4f}"


class ViewTab(QWidget):
    stitch_requested = Signal(object)
    scanner_active_changed = Signal(bool)

    def __init__(self, status_message_callback):
        super().__init__()
        self.scanner_active = False
        self.plc_running = False
        self.camera_running = False
        self.server_thread = None
        self.server_worker = None
        self.camera_thread = None
        self.camera_worker = None
        self.batch_thread = None
        self.batch_worker = None
        self.stitch_thread = None
        self.stitch_worker = None
        self.analysis_thread = None
        self.analysis_worker = None
        self.current_board_context = {}
        self.pending_stitch_jobs = 0
        self.preview_pixmap = None
        self._last_preview_update_at = 0.0
        self._preview_update_interval_seconds = 0.2
        self.ai_enabled = True
        self.ai_warmup_started_at = None
        self._last_cut_plan_payload = None
        self._latest_machine_cut_payload = None
        self._analysis_results_by_board = {}
        self._preview_results_by_board = {}
        self._last_stitch_ms = 0.0
        self._last_ai_ms = 0.0
        self._stitched_preview_active = False
        self._hover_zoom_size_px = 220
        self._hover_crop_size_px = 600
        self.settings_store = AppSettings()
        self.status_message_callback = status_message_callback
        self.create_ui()
        self.start_board_batch_worker()
        self.start_stitch_worker()
        self.start_analysis_worker()

    def create_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        top_panel = QFrame()
        top_panel.setObjectName("panel")

        top_layout = QHBoxLayout(top_panel)

        self.plc_button = QPushButton("Polacz z PLC")
        self.plc_button.setMinimumSize(160, 55)
        self.plc_button.clicked.connect(self.toggle_plc_connection)

        self.camera_button = QPushButton("Polacz z kamera")
        self.camera_button.setMinimumSize(160, 55)
        self.camera_button.clicked.connect(self.toggle_camera_connection)

        self.ai_button = QPushButton("AI: WLACZONE")
        self.ai_button.setMinimumSize(160, 55)
        self.ai_button.clicked.connect(self.toggle_ai_processing)

        self.ai_warmup_label = QLabel("Warm-up AI: --")

        self.start_button = QPushButton("Uruchom skaner")
        self.start_button.setObjectName("startButton")
        self.start_button.setMinimumSize(180, 55)
        self.start_button.setProperty("running", False)
        self.start_button.clicked.connect(self.toggle_scanner)

        top_layout.addWidget(self.plc_button)
        top_layout.addWidget(self.camera_button)
        top_layout.addWidget(self.ai_button)
        top_layout.addWidget(self.ai_warmup_label)
        top_layout.addWidget(self.start_button)
        top_layout.addStretch()

        status_layout = QVBoxLayout()
        status_layout.setSpacing(6)

        self.machine_status = StatusIndicator("Maszyna", "WYLACZONA", False)
        self.plc_status = StatusIndicator("PLC", "BRAK POLACZENIA", False)
        self.camera_status = StatusIndicator("Kamera", "OFFLINE", False)
        self.ai_status = StatusIndicator("AI", "NIEZALADOWANE", False)

        status_layout.addWidget(self.machine_status)
        status_layout.addWidget(self.plc_status)
        status_layout.addWidget(self.camera_status)
        status_layout.addWidget(self.ai_status)

        top_layout.addLayout(status_layout)
        main_layout.addWidget(top_panel)

        content_layout = QVBoxLayout()

        image_panel = QFrame()
        image_panel.setObjectName("panel")

        image_layout = QVBoxLayout(image_panel)
        image_title = QLabel("Aktualny obraz")
        image_title.setObjectName("title")

        self.image_view = QLabel("Brak obrazu")
        self.image_view.setAlignment(Qt.AlignCenter)
        self.image_view.setMinimumHeight(320)
        self.image_view.setMaximumHeight(520)
        self.image_view.setMinimumWidth(0)
        self.image_view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.image_view.setObjectName("imageView")
        self.image_view.setMouseTracking(True)
        self.image_view.installEventFilter(self)
        self.cut_plan_bar = CutPlanBar()
        self.hover_zoom_label = QLabel(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.hover_zoom_label.setObjectName("hoverZoom")
        self.hover_zoom_label.setAlignment(Qt.AlignCenter)
        self.hover_zoom_label.setFixedSize(self._hover_zoom_size_px, self._hover_zoom_size_px)
        self.hover_zoom_label.setStyleSheet(
            "background-color: #0f1318; border: 2px solid #f1f3f5; padding: 0;"
        )
        self.hover_zoom_label.hide()

        image_layout.addWidget(image_title)
        image_layout.addWidget(self.image_view)
        image_layout.addWidget(self.cut_plan_bar)
        content_layout.addWidget(image_panel)

        scan_panel = QFrame()
        scan_panel.setObjectName("panel")

        scan_layout = QVBoxLayout(scan_panel)
        scan_title = QLabel("Aktualny skan")
        scan_title.setObjectName("title")
        scan_layout.addWidget(scan_title)

        info_grid = QGridLayout()

        self.board_id = QLabel("---")
        self.defect_count = QLabel("0")
        self.scan_time = QLabel("--- ms")
        self.ai_time = QLabel("--- ms")
        self.machine_ready_time = QLabel("--- ms")
        self.scan_status = QLabel("OCZEKIWANIE")

        info_grid.addWidget(QLabel("ID deski:"), 0, 0)
        info_grid.addWidget(self.board_id, 0, 1)
        info_grid.addWidget(QLabel("Liczba wad:"), 1, 0)
        info_grid.addWidget(self.defect_count, 1, 1)
        info_grid.addWidget(QLabel("Czas skanu:"), 2, 0)
        info_grid.addWidget(self.scan_time, 2, 1)
        info_grid.addWidget(QLabel("Czas AI:"), 3, 0)
        info_grid.addWidget(self.ai_time, 3, 1)
        info_grid.addWidget(QLabel("Model -> maszyna:"), 4, 0)
        info_grid.addWidget(self.machine_ready_time, 4, 1)
        info_grid.addWidget(QLabel("Status:"), 5, 0)
        info_grid.addWidget(self.scan_status, 5, 1)

        scan_layout.addLayout(info_grid)
        scan_layout.addStretch()
        main_layout.addLayout(content_layout)

        log_panel = QFrame()
        log_panel.setObjectName("panel")

        log_layout = QVBoxLayout(log_panel)
        log_title = QLabel("Log systemu")
        log_title.setObjectName("title")

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(220)

        log_layout.addWidget(log_title)
        log_layout.addWidget(self.log)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(log_panel, 4)
        bottom_layout.addWidget(scan_panel, 1)
        main_layout.addLayout(bottom_layout)

        self.add_log("Aplikacja uruchomiona")
        self.add_log("GUI gotowe")
        self.ai_warmup_timer = QTimer(self)
        self.ai_warmup_timer.setInterval(100)
        self.ai_warmup_timer.timeout.connect(self.update_ai_warmup_label)

    def toggle_scanner(self):
        if not self.scanner_active:
            self.start_scanner()
            return

        self.stop_scanner()

    def add_log(self, text):
        time = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{time}] {text}")
        document = self.log.document()
        while document.blockCount() > 20:
            cursor = self.log.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def toggle_plc_connection(self):
        plc_host = self.settings_store.get("plc_address", "").strip()
        port_text = self.settings_store.get("plc_port", "").strip()

        if self.server_thread is not None:
            self.stop_plc_server()
            return

        if plc_host and port_text:
            try:
                port = int(port_text)
            except ValueError:
                self.add_log("Nieprawidlowy port TCP PLC")
                self.plc_status.set_status("BLAD TCP", False)
            else:
                self.start_plc_server(plc_host, port)
        else:
            self.add_log("Brak konfiguracji PLC")
            self.plc_status.set_status("NIEAKTYWNE", False)

        self.update_connection_buttons()

    def toggle_camera_connection(self):
        camera_enabled = self.settings_store.get("camera_enabled", "false").lower() == "true"

        if self.camera_thread is not None:
            self.stop_camera_worker()
            return

        if not camera_enabled:
            self.camera_status.set_status("DISABLED", False)
            self.add_log("Kamera Baumer wylaczona w ustawieniach")
            self.status_message_callback("Wlacz kamere w ustawieniach")
            return

        self.start_camera_worker()
        self.update_connection_buttons()

    def start_scanner(self):
        if self.server_thread is None and self.camera_thread is None:
            self.add_log("Brak aktywnych polaczen do uruchomienia skanera")
            self.status_message_callback("Polacz PLC lub kamere")
            return

        self.scanner_active = True
        self.scanner_active_changed.emit(True)
        self.update_machine_button()
        self.machine_status.set_status("PRACUJE", True)
        self.scan_status.setText("GOTOWY")
        self.status_message_callback("Skaner uruchomiony")

    def stop_scanner(self):
        self.scanner_active = False
        self.update_machine_button()
        self.machine_status.set_status("WYLACZONA", False)
        self.scan_status.setText("OCZEKIWANIE")
        self.board_id.setText("---")
        self.current_board_context = {}
        self._last_cut_plan_payload = None
        self.cut_plan_bar.clear_plan()
        self.scanner_active_changed.emit(False)
        self.add_log("Skaner zatrzymany")
        self.status_message_callback("Skaner zatrzymany")

    def start_board_batch_worker(self):
        if self.batch_thread is not None:
            return

        self.batch_thread = QThread(self)
        self.batch_worker = BoardBatchWorker()
        self.batch_worker.moveToThread(self.batch_thread)
        self.batch_worker.board_context_updated.connect(self.handle_board_batch_context_updated)
        self.batch_worker.image_event.connect(self.handle_board_batch_image_event)
        self.batch_worker.board_image_ready.connect(self.handle_board_image_ready)
        self.batch_worker.waiting_for_images.connect(self.handle_board_batch_waiting)
        self.batch_worker.stitch_job_ready.connect(self.handle_stitch_job_ready)
        self.batch_worker.log.connect(self.add_log)
        self.scanner_active_changed.connect(self.batch_worker.set_scanner_active)
        self.batch_thread.finished.connect(self.batch_worker.deleteLater)
        self.batch_thread.finished.connect(self.batch_thread.deleteLater)
        self.batch_thread.finished.connect(self.cleanup_batch_references)
        self.batch_thread.start()

    def start_plc_server(self, plc_host, port):
        if self.server_thread is not None:
            return

        self.server_thread = QThread(self)
        self.server_worker = TcpServerWorker(plc_host, port)
        self.server_worker.moveToThread(self.server_thread)

        self.server_thread.started.connect(self.server_worker.run)
        self.server_worker.started.connect(self.handle_server_started)
        self.server_worker.stopped.connect(self.handle_server_stopped)
        self.server_worker.error.connect(self.handle_server_error)
        self.server_worker.log.connect(self.add_log)
        self.server_worker.plc_status_changed.connect(self.plc_status.set_status)
        self.server_worker.board_context_changed.connect(self.batch_worker.handle_board_context)
        self.server_worker.stopped.connect(self.server_thread.quit)
        self.server_worker.stopped.connect(self.server_worker.deleteLater)
        self.server_thread.finished.connect(self.server_thread.deleteLater)
        self.server_thread.finished.connect(self.cleanup_server_references)
        self.server_thread.start()
        self.plc_status.set_status("LACZENIE", False)
        self.update_connection_buttons()
        self.status_message_callback("Laczenie klienta TCP z PLC")

    def start_camera_worker(self):
        if self.camera_thread is not None:
            return

        self.camera_running = True
        self.camera_thread = QThread(self)
        self.camera_worker = CameraWorker(self.get_camera_settings())
        self.camera_worker.moveToThread(self.camera_thread)

        self.camera_thread.started.connect(self.camera_worker.run)
        self.camera_worker.started.connect(self.handle_camera_started)
        self.camera_worker.stopped.connect(self.handle_camera_stopped)
        self.camera_worker.error.connect(self.handle_camera_error)
        self.camera_worker.log.connect(self.add_log)
        self.camera_worker.image_saved.connect(self.batch_worker.handle_camera_image_saved)
        self.camera_worker.camera_status_changed.connect(self.handle_camera_status_changed)
        self.camera_worker.stopped.connect(self.camera_thread.quit)
        self.camera_worker.stopped.connect(self.camera_worker.deleteLater)
        self.camera_thread.finished.connect(self.camera_thread.deleteLater)
        self.camera_thread.finished.connect(self.cleanup_camera_references)

        self.camera_thread.start()
        self.camera_status.set_status("CONNECTING", False)
        self.update_connection_buttons()

    def get_camera_settings(self):
        output_directory = self.settings_store.get("camera_output_directory", "").strip()
        if not output_directory:
            output_directory = self.settings_store.get("save_directory", "").strip()
        if not output_directory:
            output_directory = str(Path.cwd() / "scany")

        return CameraSettings(
            enabled=self.settings_store.get("camera_enabled", "false").lower() == "true",
            serial_number=self.settings_store.get("camera_serial_number", "").strip(),
            output_directory=output_directory,
            exposure_us=self.settings_store.get_int("camera_exposure", 40000),
            gain_value=self.settings_store.get_float("camera_gain", 1.8),
            brightness_value=self.settings_store.get_int("camera_brightness", 50),
            receive_timeout_ms=self.settings_store.get_int("camera_receive_timeout_ms", 1000),
            reconnect_interval_seconds=self.settings_store.get_float("camera_reconnect_interval", 3.0),
        )

    def stop_plc_server(self):
        if self.server_worker is not None:
            self.server_worker.stop()

        self.plc_running = False
        self.plc_status.set_status("BRAK POLACZENIA", False)
        self.update_connection_buttons()
        self.update_machine_state()
        self.add_log("PLC zatrzymane")

    def stop_camera_worker(self):
        if self.camera_worker is not None:
            self.camera_worker.stop()

        self.camera_running = False
        self.camera_status.set_status("DISCONNECTED", False)
        self.update_connection_buttons()
        self.update_machine_state()
        self.add_log("Kamera zatrzymana")

    def stop_all_connections(self):
        self.stop_plc_server()
        self.stop_camera_worker()

    def handle_server_started(self):
        self.plc_running = True
        self.update_machine_state()
        self.update_connection_buttons()
        self.add_log("Polaczono PLC")
        self.status_message_callback("PLC polaczone")

    def handle_server_stopped(self):
        self.plc_running = False
        self.plc_status.set_status("BRAK POLACZENIA", False)
        self.update_machine_state()
        self.update_connection_buttons()

    def handle_server_error(self, message):
        self.plc_running = False
        self.plc_status.set_status("BLAD TCP", False)
        self.update_machine_state()
        self.update_connection_buttons()
        self.add_log(message)
        self.status_message_callback("Blad klienta TCP")

        if self.server_thread is not None:
            self.server_thread.quit()

    def cleanup_server_references(self):
        self.server_thread = None
        self.server_worker = None
        self.update_connection_buttons()

    def start_stitch_worker(self):
        if self.stitch_thread is not None:
            return

        self.stitch_thread = QThread(self)
        self.stitch_worker = StitchWorker()
        self.stitch_worker.moveToThread(self.stitch_thread)

        self.stitch_requested.connect(self.stitch_worker.process_request)
        self.stitch_worker.finished.connect(self.handle_stitch_finished)
        self.stitch_worker.log.connect(self.add_log)
        self.stitch_worker.error.connect(self.handle_stitch_error)
        self.stitch_thread.finished.connect(self.stitch_worker.deleteLater)
        self.stitch_thread.finished.connect(self.cleanup_stitch_references)
        self.stitch_thread.start()

    def start_analysis_worker(self):
        if self.analysis_thread is not None or self.batch_worker is None:
            return

        self.ai_warmup_started_at = perf_counter()
        self.ai_status.set_status("WARM-UP", False)
        self.update_ai_warmup_label()
        self.ai_warmup_timer.start()

        self.analysis_thread = QThread(self)
        self.analysis_worker = BoardAnalysisWorker()
        self.analysis_worker.moveToThread(self.analysis_thread)

        self.analysis_thread.started.connect(self.analysis_worker.initialize_ai)
        self.batch_worker.board_image_ready.connect(self.analysis_worker.handle_board_image)
        self.batch_worker.stitch_job_ready.connect(self.analysis_worker.handle_board_completed)
        self.analysis_worker.finished.connect(self.handle_analysis_finished)
        self.analysis_worker.log.connect(self.add_log)
        self.analysis_worker.error.connect(self.handle_analysis_error)
        self.analysis_worker.ai_model_loaded.connect(self.handle_ai_model_loaded)
        self.analysis_thread.finished.connect(self.analysis_worker.deleteLater)
        self.analysis_thread.finished.connect(self.cleanup_analysis_references)
        self.analysis_thread.start()
        self.analysis_worker.set_ai_enabled(self.ai_enabled)

    def toggle_ai_processing(self):
        self.ai_enabled = not self.ai_enabled
        if self.analysis_worker is not None:
            self.analysis_worker.set_ai_enabled(self.ai_enabled)
        self.update_ai_button()
        state_text = "wlaczone" if self.ai_enabled else "wylaczone"
        self.add_log(f"AI {state_text}")
        self.status_message_callback(f"AI {state_text}")

    def handle_ai_model_loaded(self, success, message):
        self.ai_warmup_timer.stop()
        if success:
            self.ai_status.set_status("GOTOWE", True)
            self.add_log(message)
            self.ai_warmup_label.setText(self.build_ai_warmup_label("Gotowe"))
        else:
            self.ai_status.set_status("BLAD MODELU", False)
            self.add_log(f"Blad ladowania AI: {message}")
            self.ai_enabled = False
            self.ai_warmup_label.setText(self.build_ai_warmup_label("Blad"))
        self.update_ai_button()

    def handle_camera_started(self):
        self.add_log("Camera worker started")
        self.update_connection_buttons()

    def handle_camera_stopped(self):
        self.camera_running = False
        self.update_machine_state()
        self.update_connection_buttons()

    def handle_camera_error(self, message):
        self.camera_running = False
        self.camera_status.set_status("ERROR", False)
        self.update_machine_state()
        self.update_connection_buttons()
        self.add_log(message)
        self.status_message_callback("Blad kamery Baumer")

    def handle_camera_status_changed(self, text, active):
        self.camera_status.set_status(text, active)
        if text == "ACQUIRING":
            self.add_log("Baumer camera acquisition started")
        self.update_machine_state()
        self.update_connection_buttons()

    def handle_board_batch_context_updated(self, event):
        if not self.scanner_active:
            return

        self.current_board_context = dict(event or {})
        board_id = self.current_board_context.get("board_id", "").strip()
        board_slot = self.current_board_context.get("board_slot", "").strip()
        length_mm = self.current_board_context.get("length_mm")
        photo_count = self.current_board_context.get("photo_count")

        if board_id:
            self.board_id.setText(board_id)
            details = []
            if board_slot:
                details.append(board_slot)
            if length_mm not in (None, ""):
                details.append(f"L={length_mm}")
            if photo_count is not None:
                details.append(f"F={photo_count}")
            suffix = f" ({', '.join(details)})" if details else ""
            self.add_log(f"Ustawiono aktywna deske: {board_id}{suffix}")
        elif board_slot:
            self.board_id.setText(board_slot)
            self.add_log(f"Odebrano kontekst deski bez ID: {board_slot}")
        elif length_mm not in (None, "") or photo_count is not None:
            synthetic_board_id = self.current_board_context.get("board_id", "").strip()
            self.board_id.setText(synthetic_board_id or "---")
            self.add_log(
                "Odebrano dane PLC: "
                f"folder={synthetic_board_id or '-'} "
                f"length_mm={length_mm if length_mm not in (None, '') else '-'} "
                f"photo_count={photo_count if photo_count is not None else '-'}"
            )

    def handle_board_batch_image_event(self, event):
        if not self.scanner_active:
            return

        file_path = event.get("file_path")
        metadata = event.get("metadata") or {}
        self._last_cut_plan_payload = None
        self.cut_plan_bar.clear_plan()

        now = perf_counter()
        if (
            self.preview_pixmap is None
            or now - self._last_preview_update_at >= self._preview_update_interval_seconds
        ):
            self._last_preview_update_at = now
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                self._stitched_preview_active = False
                self.preview_pixmap = pixmap
                self.update_preview_pixmap()
            else:
                self._hide_hover_zoom()
                self.preview_pixmap = None
                self.image_view.setText(Path(file_path).name)

        self.scan_status.setText("OBRAZ ODEBRANY")
        self.scan_time.setText("--- ms")
        self.add_log(
            f"Image received: frame={metadata.get('frame_id')} saved={file_path} "
            f"{event.get('summary', '')}"
        )
        self.status_message_callback(f"Zapisano obraz: {Path(file_path).name}")

    def handle_board_image_ready(self, event):
        if not self.scanner_active:
            return
        self.add_log(
            f"AI stream: {event['board_id']} frame={event['image_index']}/{event['image_count']} "
            f"{Path(event['file_path']).name}"
        )

    def handle_board_batch_waiting(self, event):
        if not self.scanner_active:
            return
        self.add_log(
            f"Oczekiwanie na zdjecia dla {event['board_id']}: "
            f"brakuje={event['missing_count']} "
            f"{event.get('summary', '')}"
        )

    def handle_stitch_job_ready(self, event):
        if not self.scanner_active:
            return

        destination_directory = self.get_camera_output_directory() / self._sanitize_path_component(
            event["board_id"]
        )
        self.add_log(
            f"Zamknieto paczke {destination_directory.name}: {event['image_count']} zdjec, przygotowanie w tle "
            f"{event.get('summary', '')}"
        )
        self.pending_stitch_jobs += 1
        self.ai_time.setText("PRACA...")
        self.stitch_requested.emit(
            {
                "board_id": event["board_id"],
                "image_count": event["image_count"],
                "length_mm": event.get("length_mm"),
                "folder_path": str(destination_directory),
                "source_paths": event["source_paths"],
                "max_horizontal_shift_px": self.settings_store.get_int(
                    "board_stitch_max_horizontal_shift_px", 36
                ),
                "left_edge_anchor_px": self.settings_store.get_int(
                    "board_stitch_left_edge_anchor_px", 100
                ),
                "crop_x_margin_percent": self.settings_store.get_int(
                    "board_stitch_crop_x_margin_percent", 4
                ),
                "crop_y_margin_percent": self.settings_store.get_int(
                    "board_stitch_crop_y_margin_percent", 2
                ),
                "final_crop_x_margin_percent": self.settings_store.get_int(
                    "board_stitch_final_crop_x_margin_percent", 3
                ),
                "active_threshold_percent": self.settings_store.get_int(
                    "board_stitch_active_threshold_percent", 28
                ),
                "confidence_threshold": self.settings_store.get_float("yolo_threshold", 0.25),
                "knot_confidence_threshold": self.settings_store.get_float(
                    "knot_confidence_threshold", 0.25
                ),
                "cut_bad_zone_offset_mm": self.settings_store.get_int(
                    "cut_bad_zone_offset_mm", 120
                ),
                "ai_enabled": False,
            }
        )
        self.status_message_callback(
            f"Deska {destination_directory.name}: {event['image_count']} zdjec"
        )

    def get_camera_output_directory(self):
        output_directory = self.settings_store.get("camera_output_directory", "").strip()
        if not output_directory:
            output_directory = self.settings_store.get("save_directory", "").strip()
        if not output_directory:
            output_directory = str(Path.cwd() / "scany")
        return Path(output_directory)

    def _sanitize_path_component(self, value):
        sanitized = str(value).strip()
        sanitized = "".join("_" if char in '<>:"/\\|?*' else char for char in sanitized)
        sanitized = sanitized.rstrip(". ")
        return sanitized[:120] or "unknown_board"

    def cleanup_batch_references(self):
        self.batch_thread = None
        self.batch_worker = None

    def cleanup_camera_references(self):
        self.camera_thread = None
        self.camera_worker = None
        self.update_connection_buttons()

    def cleanup_stitch_references(self):
        self.stitch_thread = None
        self.stitch_worker = None

    def cleanup_analysis_references(self):
        self.analysis_thread = None
        self.analysis_worker = None

    def handle_stitch_finished(self, result):
        self.pending_stitch_jobs = max(0, self.pending_stitch_jobs - 1)
        board_id = str(result.get("board_id", "")).strip()
        if board_id:
            self._preview_results_by_board[board_id] = dict(result)
        stitched_path = result.get("stitched_path")
        stitch_ms = result.get("elapsed_ms", 0.0)
        self._last_stitch_ms = stitch_ms
        self.ai_time.setText(f"S:{self._last_stitch_ms:.0f} / M:{self._last_ai_ms:.0f} ms")
        merged_result = dict(result)
        analysis_result = self._analysis_results_by_board.get(board_id)
        if analysis_result:
            projected_boxes = self._project_boxes_to_stitched_space(
                boxes=analysis_result.get("boxes", []),
                source_width_px=int(analysis_result.get("image_width_px", 0) or 0),
                source_height_px=int(analysis_result.get("image_height_px", 0) or 0),
                source_crop_left_px=analysis_result.get("stream_crop_left_px"),
                source_crop_right_px=analysis_result.get("stream_crop_right_px"),
                stitch_metadata=result.get("stitch_metadata"),
                stitched_path=stitched_path,
            )
            projected_boxes = self._filter_boxes_by_stitched_area(projected_boxes)
            merged_result.update(
                {
                    "boxes": projected_boxes,
                    "defect_count": len(projected_boxes),
                    "length_mm": analysis_result.get("length_mm", merged_result.get("length_mm")),
                    "cut_bad_zone_offset_mm": result.get(
                        "cut_bad_zone_offset_mm",
                        self.settings_store.get_int("cut_bad_zone_offset_mm", 120),
                    ),
                    "image_height_px": self._read_image_height(stitched_path) if stitched_path is not None else 0,
                    "image_width_px": self._read_image_width(stitched_path) if stitched_path is not None else 0,
                }
            )
        self._last_cut_plan_payload = self._build_cut_plan_payload(merged_result)
        preview_path = stitched_path
        if preview_path is not None:
            preview_path = Path(preview_path)
        if stitched_path is not None:
            stitched_path = Path(stitched_path)
            self.add_log(
                f"Zapisano obraz scalony: {stitched_path.name} "
                f"w {stitch_ms:.0f} ms"
            )
        if preview_path is not None:
            self.show_stitched_preview(preview_path, merged_result.get("boxes", []))
        else:
            self._apply_cut_plan_payload()

    def handle_stitch_error(self, message):
        self.pending_stitch_jobs = max(0, self.pending_stitch_jobs - 1)
        self.ai_time.setText("BLAD")
        self.add_log(f"Blad stitchingu: {message}")

    def handle_analysis_finished(self, result):
        board_id = str(result.get("board_id", "")).strip()
        final_boxes = list(result.get("boxes", []))
        machine_cut_payload = self._build_machine_cut_payload(result)
        self._latest_machine_cut_payload = machine_cut_payload
        machine_ready_latency_ms = float(result.get("machine_ready_latency_ms", 0.0) or 0.0)
        self.machine_ready_time.setText(f"{machine_ready_latency_ms:.0f} ms")
        if machine_cut_payload is not None:
            self.add_log(
                "Plan ciecia dla maszyny gotowy: "
                f"{machine_cut_payload['board_id']} "
                f"ciecia={len(machine_cut_payload['cut_positions_mm'])} "
                f"latencja={machine_ready_latency_ms:.0f} ms "
                f"strefy_zle={len(machine_cut_payload['bad_segments_mm'])} "
                f"wektor={machine_cut_payload['machine_segments_payload']}"
            )
        if board_id:
            self._analysis_results_by_board[board_id] = dict(result)
            preview_result = self._preview_results_by_board.get(board_id)
            if preview_result is not None:
                merged_result = dict(preview_result)
                projected_boxes = self._project_boxes_to_stitched_space(
                    boxes=result.get("boxes", []),
                    source_width_px=int(result.get("image_width_px", 0) or 0),
                    source_height_px=int(result.get("image_height_px", 0) or 0),
                    source_crop_left_px=result.get("stream_crop_left_px"),
                    source_crop_right_px=result.get("stream_crop_right_px"),
                    stitch_metadata=preview_result.get("stitch_metadata"),
                    stitched_path=preview_result.get("stitched_path"),
                )
                projected_boxes = self._filter_boxes_by_stitched_area(projected_boxes)
                merged_result.update(
                    {
                        "boxes": projected_boxes,
                        "defect_count": len(projected_boxes),
                        "length_mm": result.get("length_mm", merged_result.get("length_mm")),
                        "image_height_px": self._read_image_height(preview_result.get("stitched_path")),
                        "image_width_px": self._read_image_width(preview_result.get("stitched_path")),
                    }
                )
                final_boxes = projected_boxes
                self._last_cut_plan_payload = self._build_cut_plan_payload(merged_result)
                stitched_path = preview_result.get("stitched_path")
                if stitched_path is not None:
                    self.show_stitched_preview(Path(stitched_path), projected_boxes)
                    self._save_annotated_stitched_preview(Path(stitched_path), projected_boxes)
                self._apply_cut_plan_payload()
        self._last_ai_ms = float(result.get("inference_ms", 0.0))
        self.ai_time.setText(f"S:{self._last_stitch_ms:.0f} / M:{self._last_ai_ms:.0f} ms")
        self.defect_count.setText(str(len(final_boxes)))
        self.ai_status.set_status(
            "GOTOWE" if result.get("ai_available") else ("WYLACZONE" if not self.ai_enabled else "BRAK MODELU"),
            bool(result.get("ai_available")),
        )
        self.add_log(
            f"Wykryto sekow: {len(final_boxes)} "
            f"(model {self._last_ai_ms:.0f} ms)"
        )
        detections_path = result.get("detections_path")
        if detections_path:
            self.add_log(f"Log detekcji AI: {Path(detections_path).name}")
        for index, box in enumerate(final_boxes, start=1):
            self.add_log(
                "Sek "
                f"{index}: conf={format_detection_confidence(float(box.get('confidence', 0.0)))} "
                f"x1={int(box.get('x1', 0))} y1={int(box.get('y1', 0))} "
                f"x2={int(box.get('x2', 0))} y2={int(box.get('y2', 0))}"
            )

    def handle_analysis_error(self, message):
        self.ai_status.set_status("BLAD AI", False)
        self.ai_time.setText("BLAD")
        self.add_log(f"Blad AI stream: {message}")

    def restitch_latest_board(self):
        latest_board_directory = self._find_latest_board_directory()
        if latest_board_directory is None:
            self.add_log("Brak folderu deski do ponownego stitchingu")
            self.status_message_callback("Brak folderu deski")
            return

        image_paths = sorted(latest_board_directory.glob("*.bmp"))
        source_image_paths = [
            image_path
            for image_path in image_paths
            if image_path.name.lower() not in DERIVED_STITCH_FILES
        ]
        if not source_image_paths:
            self.add_log(f"Folder {latest_board_directory.name} nie zawiera zdjec zrodlowych")
            self.status_message_callback("Brak zdjec do stitchingu")
            return

        self.pending_stitch_jobs += 1
        self.ai_time.setText("PRACA...")
        self.add_log(
            f"Re-stitch ostatniej deski: {latest_board_directory.name} "
            f"({len(source_image_paths)} zdjec)"
        )
        self.stitch_requested.emit(
            {
                "board_id": latest_board_directory.name,
                "image_count": len(source_image_paths),
                "length_mm": self.current_board_context.get("length_mm"),
                "folder_path": str(latest_board_directory),
                "max_horizontal_shift_px": self.settings_store.get_int(
                    "board_stitch_max_horizontal_shift_px", 36
                ),
                "left_edge_anchor_px": self.settings_store.get_int(
                    "board_stitch_left_edge_anchor_px", 100
                ),
                "crop_x_margin_percent": self.settings_store.get_int(
                    "board_stitch_crop_x_margin_percent", 4
                ),
                "crop_y_margin_percent": self.settings_store.get_int(
                    "board_stitch_crop_y_margin_percent", 2
                ),
                "final_crop_x_margin_percent": self.settings_store.get_int(
                    "board_stitch_final_crop_x_margin_percent", 3
                ),
                "active_threshold_percent": self.settings_store.get_int(
                    "board_stitch_active_threshold_percent", 28
                ),
                "confidence_threshold": self.settings_store.get_float("yolo_threshold", 0.25),
                "knot_confidence_threshold": self.settings_store.get_float(
                    "knot_confidence_threshold", 0.25
                ),
                "cut_bad_zone_offset_mm": self.settings_store.get_int(
                    "cut_bad_zone_offset_mm", 120
                ),
                "ai_enabled": False,
            }
        )
        self.status_message_callback(f"Przestitchowanie: {latest_board_directory.name}")

    def show_stitched_preview(self, image_path, boxes=None):
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self.image_view.setText(image_path.name)
            self._hide_hover_zoom()
            self.preview_pixmap = None
            return

        annotated_pixmap = self._build_annotated_preview_pixmap(
            pixmap,
            boxes,
            self._extract_cut_positions_mm(self._last_cut_plan_payload),
            self._last_cut_plan_payload["board_length_mm"] if self._last_cut_plan_payload else None,
        )

        rotated_pixmap = annotated_pixmap.transformed(QTransform().rotate(90), Qt.SmoothTransformation)
        self._stitched_preview_active = True
        self.preview_pixmap = rotated_pixmap
        self.update_preview_pixmap()
        self._apply_cut_plan_payload()

    def _build_annotated_preview_pixmap(
        self,
        pixmap,
        boxes=None,
        cut_positions_mm=None,
        board_length_mm=None,
    ):
        annotated_pixmap = pixmap.copy()
        painter = QPainter(annotated_pixmap)
        painter.setRenderHint(QPainter.Antialiasing, False)

        if boxes:
            pen = QPen(QColor(255, 0, 0))
            pen.setWidth(11)
            painter.setPen(pen)
            confidence_font = QFont(painter.font())
            confidence_font.setPointSizeF(max(8.0, confidence_font.pointSizeF() * 3.0))
            painter.setFont(confidence_font)
            for box in boxes:
                x1 = int(box.get("x1", 0))
                y1 = int(box.get("y1", 0))
                x2 = int(box.get("x2", 0))
                y2 = int(box.get("y2", 0))
                width = max(1, x2 - x1)
                height = max(1, y2 - y1)
                painter.drawRect(x1, y1, width, height)
                confidence_text = format_detection_confidence(float(box.get("confidence", 0.0)))
                text_x = max(4, min(annotated_pixmap.width() - 120, x1 + 6))
                text_y = max(28, y1 - 10)
                painter.drawText(text_x, text_y, confidence_text)

        if cut_positions_mm and board_length_mm and board_length_mm > 0:
            painter.setPen(QPen(QColor(255, 220, 0), 11))
            image_height_px = annotated_pixmap.height()
            for cut_position_mm in cut_positions_mm:
                ratio = max(0.0, min(1.0, float(cut_position_mm) / float(board_length_mm)))
                y = int(round(float(image_height_px) * ratio))
                y = max(0, min(image_height_px - 1, y))
                painter.drawLine(0, y, annotated_pixmap.width() - 1, y)
        painter.end()
        return annotated_pixmap

    def _save_annotated_stitched_preview(self, stitched_path, boxes):
        pixmap = QPixmap(str(stitched_path))
        if pixmap.isNull():
            return
        annotated_pixmap = self._build_annotated_preview_pixmap(
            pixmap,
            boxes,
            self._extract_cut_positions_mm(self._last_cut_plan_payload),
            self._last_cut_plan_payload["board_length_mm"] if self._last_cut_plan_payload else None,
        )
        annotated_path = Path(stitched_path).with_name("stitched_annotated.bmp")
        annotated_pixmap.save(str(annotated_path), "BMP")

    def update_preview_pixmap(self):
        if self.preview_pixmap is None:
            self._hide_hover_zoom()
            return

        target_size = self.image_view.contentsRect().size()
        if not target_size.isValid() or target_size.width() <= 0 or target_size.height() <= 0:
            target_size = self.image_view.size()

        scaled_pixmap = self.preview_pixmap.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.image_view.setPixmap(scaled_pixmap)
        self._apply_cut_plan_payload()

    def eventFilter(self, watched, event):
        if watched is self.image_view:
            if event.type() == QEvent.Type.MouseMove:
                self._update_hover_zoom(event.position().toPoint(), event.globalPosition().toPoint())
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.Hide):
                self._hide_hover_zoom()
        return super().eventFilter(watched, event)

    def _update_hover_zoom(self, local_pos, global_pos):
        if not self._stitched_preview_active or self.preview_pixmap is None:
            self._hide_hover_zoom()
            return

        scaled_pixmap = self.image_view.pixmap()
        if scaled_pixmap is None or scaled_pixmap.isNull():
            self._hide_hover_zoom()
            return

        contents_rect = self.image_view.contentsRect()
        pixmap_left = contents_rect.left() + max(0, (contents_rect.width() - scaled_pixmap.width()) // 2)
        pixmap_top = contents_rect.top() + max(0, (contents_rect.height() - scaled_pixmap.height()) // 2)
        pixmap_rect = contents_rect.adjusted(
            pixmap_left - contents_rect.left(),
            pixmap_top - contents_rect.top(),
            pixmap_left - contents_rect.left() + scaled_pixmap.width() - contents_rect.width(),
            pixmap_top - contents_rect.top() + scaled_pixmap.height() - contents_rect.height(),
        )

        if not pixmap_rect.contains(local_pos):
            self._hide_hover_zoom()
            return

        relative_x = local_pos.x() - pixmap_rect.left()
        relative_y = local_pos.y() - pixmap_rect.top()
        source_x = int(round(relative_x * self.preview_pixmap.width() / max(1, scaled_pixmap.width())))
        source_y = int(round(relative_y * self.preview_pixmap.height() / max(1, scaled_pixmap.height())))

        half_crop = self._hover_crop_size_px // 2
        crop_x = max(0, min(self.preview_pixmap.width() - self._hover_crop_size_px, source_x - half_crop))
        crop_y = max(0, min(self.preview_pixmap.height() - self._hover_crop_size_px, source_y - half_crop))
        crop_width = min(self._hover_crop_size_px, self.preview_pixmap.width())
        crop_height = min(self._hover_crop_size_px, self.preview_pixmap.height())
        crop = self.preview_pixmap.copy(crop_x, crop_y, crop_width, crop_height)
        if crop.isNull():
            self._hide_hover_zoom()
            return

        zoom_pixmap = crop.scaled(
            self._hover_zoom_size_px,
            self._hover_zoom_size_px,
            Qt.KeepAspectRatio,
            Qt.FastTransformation,
        )
        self.hover_zoom_label.setPixmap(zoom_pixmap)
        self.hover_zoom_label.move(global_pos + QPoint(24, 24))
        self.hover_zoom_label.show()
        self.hover_zoom_label.raise_()

    def _hide_hover_zoom(self):
        if hasattr(self, "hover_zoom_label") and self.hover_zoom_label.isVisible():
            self.hover_zoom_label.hide()

    def _build_cut_plan_payload(self, result):
        length_mm = result.get("length_mm")
        stitched_path = result.get("stitched_path")
        boxes = result.get("boxes", [])
        image_height_px = int(result.get("image_height_px", 0) or 0)
        bad_zone_offset_mm = result.get(
            "cut_bad_zone_offset_mm",
            self.settings_store.get_int("cut_bad_zone_offset_mm", 120),
        )

        if not length_mm:
            return None

        image_height = image_height_px
        if image_height <= 0 and stitched_path is not None:
            image_height = self._read_image_height(stitched_path)
        if image_height <= 0:
            return None

        bad_segments_mm = self._build_bad_segments_mm(
            boxes=boxes,
            board_length_mm=length_mm,
            image_height_px=image_height,
            offset_mm=bad_zone_offset_mm,
        )
        return {
            "board_length_mm": float(length_mm),
            "bad_segments_mm": bad_segments_mm,
        }

    def _extract_cut_positions_mm(self, cut_plan_payload):
        if not cut_plan_payload:
            return []
        positions = []
        for start_mm, end_mm in cut_plan_payload.get("bad_segments_mm", []):
            positions.append(float(start_mm))
            positions.append(float(end_mm))
        unique_positions = sorted({position for position in positions if position > 0.0})
        board_length_mm = float(cut_plan_payload.get("board_length_mm", 0.0) or 0.0)
        return [position for position in unique_positions if position < board_length_mm]

    def _apply_cut_plan_payload(self):
        if not self._last_cut_plan_payload:
            self.cut_plan_bar.clear_plan()
            return

        self.cut_plan_bar.set_plan(
            self._last_cut_plan_payload["board_length_mm"],
            self._last_cut_plan_payload["bad_segments_mm"],
        )

    def _read_image_height(self, image_path):
        if image_path is None:
            return 0
        image = QPixmap(str(image_path))
        if image.isNull():
            return 0
        return image.height()

    def _read_image_width(self, image_path):
        if image_path is None:
            return 0
        image = QPixmap(str(image_path))
        if image.isNull():
            return 0
        return image.width()

    def _project_boxes_to_stitched_space(
        self,
        boxes,
        source_width_px,
        source_height_px,
        source_crop_left_px,
        source_crop_right_px,
        stitch_metadata,
        stitched_path,
    ):
        if stitched_path is None:
            return list(boxes or [])

        target_width_px = self._read_image_width(stitched_path)
        target_height_px = self._read_image_height(stitched_path)
        if source_width_px <= 0 or source_height_px <= 0 or target_width_px <= 0 or target_height_px <= 0:
            return list(boxes or [])

        source_crop_left_px = int(source_crop_left_px if source_crop_left_px is not None else 0)
        source_crop_right_px = int(source_crop_right_px if source_crop_right_px is not None else source_width_px)

        pre_crop_window = None
        final_crop_rect = None
        canvas_height_before_final_crop = source_height_px
        if isinstance(stitch_metadata, dict):
            pre_crop_window = stitch_metadata.get("pre_crop_window")
            final_crop_rect = stitch_metadata.get("final_crop_rect")
            canvas_height_before_final_crop = int(
                stitch_metadata.get("canvas_height_before_final_crop", source_height_px) or source_height_px
            )

        if (
            isinstance(final_crop_rect, (list, tuple))
            and len(final_crop_rect) >= 4
        ):
            stitch_pre_left = 0
            if isinstance(pre_crop_window, (list, tuple)) and len(pre_crop_window) >= 2:
                stitch_pre_left = int(pre_crop_window[0])
            final_left = int(final_crop_rect[0])
            final_top = int(final_crop_rect[1])
            total_left = stitch_pre_left + final_left
            projected_boxes = []
            for box in boxes or []:
                x1 = int(round(float(box.get("x1", 0.0)) - total_left))
                x2 = int(round(float(box.get("x2", 0.0)) - total_left))
                source_y1 = float(box.get("y1", 0.0))
                source_y2 = float(box.get("y2", 0.0))
                y1 = int(round(source_y1 - final_top))
                y2 = int(round(source_y2 - final_top))
                rotated_x1 = int(round(float(target_width_px) - x2))
                rotated_x2 = int(round(float(target_width_px) - x1))
                rotated_y1 = int(round(float(target_height_px) - y2))
                rotated_y2 = int(round(float(target_height_px) - y1))
                x1 = rotated_x1
                x2 = rotated_x2
                y1 = rotated_y1
                y2 = rotated_y2
                x1 = max(0, min(target_width_px - 1, x1))
                x2 = max(0, min(target_width_px, x2))
                y1 = max(0, min(target_height_px - 1, y1))
                y2 = max(0, min(target_height_px, y2))
                if x2 <= x1 or y2 <= y1:
                    continue
                projected_boxes.append(
                    {
                        **box,
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                    }
                )
            return projected_boxes

        crop_width_px = max(1, source_crop_right_px - source_crop_left_px)
        scale_y = float(target_height_px) / float(source_height_px)
        projected_boxes = []
        for box in boxes or []:
            x1 = int(
                round(
                    (float(box.get("x1", 0.0)) - source_crop_left_px)
                    * float(target_width_px)
                    / float(crop_width_px)
                )
            )
            x2 = int(
                round(
                    (float(box.get("x2", 0.0)) - source_crop_left_px)
                    * float(target_width_px)
                    / float(crop_width_px)
                )
            )
            source_y1 = float(box.get("y1", 0.0))
            source_y2 = float(box.get("y2", 0.0))
            y1 = int(round(source_y1 * scale_y))
            y2 = int(round(source_y2 * scale_y))
            rotated_x1 = int(round(float(target_width_px) - x2))
            rotated_x2 = int(round(float(target_width_px) - x1))
            rotated_y1 = int(round(float(target_height_px) - y2))
            rotated_y2 = int(round(float(target_height_px) - y1))
            x1 = rotated_x1
            x2 = rotated_x2
            y1 = rotated_y1
            y2 = rotated_y2
            x1 = max(0, min(target_width_px - 1, x1))
            x2 = max(0, min(target_width_px, x2))
            y1 = max(0, min(target_height_px - 1, y1))
            y2 = max(0, min(target_height_px, y2))
            if x2 <= x1 or y2 <= y1:
                continue
            projected_boxes.append(
                {
                    **box,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                }
            )
        return projected_boxes

    def _build_bad_segments_mm(self, boxes, board_length_mm, image_height_px, offset_mm):
        if not boxes or board_length_mm <= 0 or image_height_px <= 0:
            return []

        board_length_mm = float(board_length_mm)
        offset_mm = max(0.0, float(offset_mm))
        mm_per_px = board_length_mm / float(image_height_px)
        segments = []

        for box in boxes:
            y1 = max(0.0, float(box.get("y1", 0.0)))
            y2 = max(y1, float(box.get("y2", y1)))
            start_mm = max(0.0, y1 * mm_per_px - offset_mm)
            end_mm = min(board_length_mm, y2 * mm_per_px + offset_mm)
            if end_mm > start_mm:
                segments.append((start_mm, end_mm))

        if not segments:
            return []

        segments.sort(key=lambda item: item[0])
        merged_segments = [list(segments[0])]
        for start_mm, end_mm in segments[1:]:
            previous = merged_segments[-1]
            previous_center_mm = (previous[0] + previous[1]) / 2.0
            current_center_mm = (start_mm + end_mm) / 2.0
            centers_overlap = (
                previous[0] <= current_center_mm <= previous[1]
                or start_mm <= previous_center_mm <= end_mm
            )
            if start_mm <= previous[1] or centers_overlap:
                previous[1] = max(previous[1], end_mm)
                previous[0] = min(previous[0], start_mm)
            else:
                merged_segments.append([start_mm, end_mm])

        return [(segment[0], segment[1]) for segment in merged_segments]

    def _filter_boxes_by_stitched_area(self, boxes):
        min_area_px = max(0, int(self.settings_store.get_int("knot_min_box_area_px", 400)))
        max_area_px = max(0, int(self.settings_store.get_int("knot_max_box_area_px", 0)))
        filtered_boxes = []

        for box in boxes or []:
            width = max(0, int(box.get("x2", 0)) - int(box.get("x1", 0)))
            height = max(0, int(box.get("y2", 0)) - int(box.get("y1", 0)))
            area_px = width * height
            if area_px < min_area_px:
                continue
            if max_area_px > 0 and area_px > max_area_px:
                continue
            filtered_boxes.append(box)

        return filtered_boxes

    def _build_machine_cut_payload(self, result):
        board_id = str(result.get("board_id", "")).strip()
        board_length_mm = float(result.get("length_mm", 0) or 0)
        image_height_px = int(result.get("image_height_px", 0) or 0)
        boxes = list(result.get("boxes", []) or [])
        if not board_id or board_length_mm <= 0 or image_height_px <= 0:
            return None

        margin_mm = self.settings_store.get_int("cut_bad_zone_offset_mm", 120)
        bad_segments_mm = self._build_bad_segments_mm(
            boxes=boxes,
            board_length_mm=board_length_mm,
            image_height_px=image_height_px,
            offset_mm=margin_mm,
        )
        good_segments_mm = self._build_good_segments_mm(board_length_mm, bad_segments_mm)
        cut_positions_mm = [segment[0] for segment in good_segments_mm if segment[0] > 0.0]

        return {
            "board_id": board_id,
            "source": "ai_stream",
            "board_length_mm": board_length_mm,
            "margin_mm": int(margin_mm),
            "bad_segments_mm": bad_segments_mm,
            "good_segments_mm": good_segments_mm,
            "cut_positions_mm": cut_positions_mm,
            "machine_segments_payload": self._build_machine_segments_payload(
                board_length_mm,
                good_segments_mm,
                bad_segments_mm,
            ),
            "defect_count": len(boxes),
            "inference_ms": float(result.get("inference_ms", 0.0) or 0.0),
        }

    def _build_good_segments_mm(self, board_length_mm, bad_segments_mm):
        if board_length_mm <= 0:
            return []
        if not bad_segments_mm:
            return [(0.0, float(board_length_mm))]

        good_segments = []
        cursor_mm = 0.0
        for start_mm, end_mm in bad_segments_mm:
            start_mm = max(0.0, min(float(board_length_mm), float(start_mm)))
            end_mm = max(start_mm, min(float(board_length_mm), float(end_mm)))
            if start_mm > cursor_mm:
                good_segments.append((cursor_mm, start_mm))
            cursor_mm = max(cursor_mm, end_mm)

        if cursor_mm < float(board_length_mm):
            good_segments.append((cursor_mm, float(board_length_mm)))

        return good_segments

    def _build_machine_segments_payload(self, board_length_mm, good_segments_mm, bad_segments_mm):
        total_length_mm = max(0, int(round(float(board_length_mm))))
        segments = []

        for start_mm, end_mm in good_segments_mm or []:
            length_mm = max(0, int(round(float(end_mm) - float(start_mm))))
            if length_mm > 0:
                segments.append((float(start_mm), 1, length_mm))

        for start_mm, end_mm in bad_segments_mm or []:
            length_mm = max(0, int(round(float(end_mm) - float(start_mm))))
            if length_mm > 0:
                segments.append((float(start_mm), 3, length_mm))

        segments.sort(key=lambda item: item[0])

        payload = [total_length_mm]
        for _, segment_class, length_mm in segments:
            payload.append(int(segment_class))
            payload.append(int(length_mm))
        return payload

    def _find_latest_board_directory(self):
        base_directory = self.get_camera_output_directory()
        if not base_directory.exists():
            return None

        candidate_directories = []
        for directory in base_directory.iterdir():
            if not directory.is_dir():
                continue
            if any(
                path.name.lower() not in DERIVED_STITCH_FILES
                for path in directory.glob("*.bmp")
            ):
                candidate_directories.append(directory)

        if not candidate_directories:
            return None

        return max(candidate_directories, key=lambda path: path.stat().st_mtime_ns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_preview_pixmap()

    def update_machine_state(self):
        self.update_machine_button()
        if self.scanner_active:
            self.machine_status.set_status("PRACUJE", True)
            self.scan_status.setText("GOTOWY")
        else:
            self.machine_status.set_status("WYLACZONA", False)
            self.scan_status.setText("OCZEKIWANIE")

    def update_machine_button(self):
        self.start_button.setProperty("running", self.scanner_active)
        self.start_button.style().unpolish(self.start_button)
        self.start_button.style().polish(self.start_button)
        self.start_button.setText(
            "Zatrzymaj skaner" if self.scanner_active else "Uruchom skaner"
        )

    def update_connection_buttons(self):
        self.plc_button.setText(
            "Rozlacz PLC" if self.server_thread is not None else "Polacz z PLC"
        )
        self.camera_button.setText(
            "Rozlacz kamere" if self.camera_thread is not None else "Polacz z kamera"
        )

    def update_ai_button(self):
        self.ai_button.setText("AI: WLACZONE" if self.ai_enabled else "AI: WYLACZONE")

    def update_ai_warmup_label(self):
        if self.ai_warmup_started_at is None:
            self.ai_warmup_label.setText("Warm-up AI: --")
            return
        elapsed_seconds = perf_counter() - self.ai_warmup_started_at
        self.ai_warmup_label.setText(self.build_ai_warmup_label(f"{elapsed_seconds:.1f}s"))

    def build_ai_warmup_label(self, suffix):
        return f"Warm-up AI: {suffix}"

    def shutdown(self):
        self.stop_scanner()
        self.stop_all_connections()
        if self.stitch_worker is not None:
            self.stitch_worker.shutdown()
        if self.analysis_worker is not None:
            self.analysis_worker.shutdown()
        if self.server_thread is not None:
            self.server_thread.wait(3000)
        if self.camera_thread is not None:
            self.camera_thread.wait(5000)
        if self.batch_thread is not None:
            self.batch_thread.quit()
            self.batch_thread.wait(5000)
        if self.analysis_thread is not None:
            self.analysis_thread.quit()
            self.analysis_thread.wait(5000)
        if self.stitch_thread is not None:
            self.stitch_thread.quit()
            self.stitch_thread.wait(5000)
