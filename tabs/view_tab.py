from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QPixmap, QTransform
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
from workers.camera_worker import CameraWorker
from workers.stitch_worker import StitchWorker
from workers.tcp_server_worker import TcpServerWorker
from widgets.status_indicator import StatusIndicator


class ViewTab(QWidget):
    stitch_requested = Signal(object)

    def __init__(self, status_message_callback):
        super().__init__()
        self.scanner_active = False
        self.plc_running = False
        self.camera_running = False
        self.server_thread = None
        self.server_worker = None
        self.camera_thread = None
        self.camera_worker = None
        self.stitch_thread = None
        self.stitch_worker = None
        self.current_board_context = {}
        self.pending_image_paths = deque()
        self.pending_board_batches = deque()
        self.pending_stitch_jobs = 0
        self.preview_pixmap = None
        self.settings_store = AppSettings()
        self.status_message_callback = status_message_callback
        self.create_ui()
        self.start_stitch_worker()

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

        self.start_button = QPushButton("Uruchom skaner")
        self.start_button.setObjectName("startButton")
        self.start_button.setMinimumSize(180, 55)
        self.start_button.setProperty("running", False)
        self.start_button.clicked.connect(self.toggle_scanner)

        top_layout.addWidget(self.plc_button)
        top_layout.addWidget(self.camera_button)
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

        content_layout = QHBoxLayout()

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

        image_layout.addWidget(image_title)
        image_layout.addWidget(self.image_view)
        content_layout.addWidget(image_panel, 4)

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
        self.scan_status = QLabel("OCZEKIWANIE")

        info_grid.addWidget(QLabel("ID deski:"), 0, 0)
        info_grid.addWidget(self.board_id, 0, 1)
        info_grid.addWidget(QLabel("Liczba wad:"), 1, 0)
        info_grid.addWidget(self.defect_count, 1, 1)
        info_grid.addWidget(QLabel("Czas skanu:"), 2, 0)
        info_grid.addWidget(self.scan_time, 2, 1)
        info_grid.addWidget(QLabel("Czas AI:"), 3, 0)
        info_grid.addWidget(self.ai_time, 3, 1)
        info_grid.addWidget(QLabel("Status:"), 4, 0)
        info_grid.addWidget(self.scan_status, 4, 1)

        scan_layout.addLayout(info_grid)
        scan_layout.addStretch()
        content_layout.addWidget(scan_panel, 1)

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
        main_layout.addWidget(log_panel)

        self.add_log("Aplikacja uruchomiona")
        self.add_log("GUI gotowe")

    def toggle_scanner(self):
        if not self.scanner_active:
            self.start_scanner()
            return

        self.stop_scanner()

    def add_log(self, text):
        time = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{time}] {text}")

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
        self.pending_image_paths.clear()
        self.pending_board_batches.clear()
        self.add_log("Skaner zatrzymany")
        self.status_message_callback("Skaner zatrzymany")

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
        self.server_worker.board_context_changed.connect(self.handle_board_context_changed)
        self.server_worker.stopped.connect(self.server_thread.quit)
        self.server_worker.stopped.connect(self.server_worker.deleteLater)
        self.server_thread.finished.connect(self.server_thread.deleteLater)
        self.server_thread.finished.connect(self.cleanup_server_references)
        self.server_thread.start()
        self.plc_status.set_status("START...", False)
        self.update_connection_buttons()
        self.status_message_callback("Uruchamianie serwera TCP")

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
        self.camera_worker.image_saved.connect(self.handle_camera_image_saved)
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
        self.status_message_callback("Blad serwera TCP")

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

    def handle_board_context_changed(self, board_context):
        if not self.scanner_active:
            return

        self.current_board_context = dict(board_context or {})
        board_id = self.current_board_context.get("board_id", "").strip()
        board_slot = self.current_board_context.get("board_slot", "").strip()
        length_mm = self.current_board_context.get("length_mm")
        photo_count = self.current_board_context.get("photo_count")
        normalized_photo_count = self._normalize_photo_count(photo_count)

        if board_id:
            self.board_id.setText(board_id)
            details = []
            if board_slot:
                details.append(board_slot)
            if length_mm not in (None, ""):
                details.append(f"L={length_mm}")
            if normalized_photo_count is not None:
                details.append(f"F={normalized_photo_count}")
            suffix = f" ({', '.join(details)})" if details else ""
            self.add_log(f"Ustawiono aktywna deske: {board_id}{suffix}")
        elif board_slot:
            self.board_id.setText(board_slot)
            self.add_log(f"Odebrano kontekst deski bez ID: {board_slot}")
        elif length_mm not in (None, "") or normalized_photo_count is not None:
            synthetic_board_id = self.current_board_context.get("board_id", "").strip()
            self.board_id.setText(synthetic_board_id or "---")
            self.add_log(
                "Odebrano dane PLC: "
                f"folder={synthetic_board_id or '-'} "
                f"length_mm={length_mm if length_mm not in (None, '') else '-'} "
                f"photo_count={normalized_photo_count if normalized_photo_count is not None else '-'}"
            )

        if synthetic_board_id := self.current_board_context.get("board_id", "").strip():
            if normalized_photo_count and normalized_photo_count > 0:
                self.pending_board_batches.append(
                    {
                        "board_id": synthetic_board_id,
                        "length_mm": length_mm,
                        "photo_count": normalized_photo_count,
                        "received_at": datetime.now().isoformat(timespec="microseconds"),
                    }
                )
                self.add_log(
                    f"Kolejka desek: dodano {synthetic_board_id} oczekuje_na={normalized_photo_count}"
                )
                self.process_pending_board_batches()

    def handle_camera_image_saved(self, file_path, metadata):
        if not self.scanner_active:
            return

        image_path = Path(file_path)
        self.pending_image_paths.append(image_path)
        self.process_pending_board_batches()

        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            self.preview_pixmap = pixmap
            self.update_preview_pixmap()
        else:
            self.preview_pixmap = None
            self.image_view.setText(Path(file_path).name)

        self.scan_status.setText("OBRAZ ODEBRANY")
        self.scan_time.setText("--- ms")
        self.add_log(
            f"Image received: frame={metadata.get('frame_id')} saved={file_path}"
        )
        self.status_message_callback(f"Zapisano obraz: {Path(file_path).name}")

    def process_pending_board_batches(self):
        while self.pending_board_batches:
            batch = self.pending_board_batches[0]
            expected_count = batch["photo_count"]
            if len(self.pending_image_paths) < expected_count:
                break

            destination_directory = self.get_camera_output_directory() / self._sanitize_path_component(
                batch["board_id"]
            )
            destination_directory.mkdir(parents=True, exist_ok=True)

            moved_files = []
            for _ in range(expected_count):
                source_path = self.pending_image_paths.popleft()
                destination_path = destination_directory / source_path.name
                source_path.replace(destination_path)
                moved_files.append(destination_path)

            self.pending_board_batches.popleft()
            self.add_log(
                f"Przeniesiono {len(moved_files)} zdjec do folderu {destination_directory.name}"
            )
            self.pending_stitch_jobs += 1
            self.ai_time.setText("PRACA...")
            self.stitch_requested.emit(
                {
                    "board_id": batch["board_id"],
                    "image_count": len(moved_files),
                    "folder_path": str(destination_directory),
                    "max_horizontal_shift_px": self.settings_store.get_int(
                        "board_stitch_max_horizontal_shift_px", 36
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
                }
            )
            self.status_message_callback(
                f"Deska {destination_directory.name}: {len(moved_files)} zdjec"
            )

    def get_camera_output_directory(self):
        output_directory = self.settings_store.get("camera_output_directory", "").strip()
        if not output_directory:
            output_directory = self.settings_store.get("save_directory", "").strip()
        if not output_directory:
            output_directory = str(Path.cwd() / "scany")
        return Path(output_directory)

    def _normalize_photo_count(self, value):
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return None
        return normalized if normalized > 0 else None

    def _sanitize_path_component(self, value):
        sanitized = str(value).strip()
        sanitized = "".join("_" if char in '<>:"/\\|?*' else char for char in sanitized)
        sanitized = sanitized.rstrip(". ")
        return sanitized[:120] or "unknown_board"

    def cleanup_camera_references(self):
        self.camera_thread = None
        self.camera_worker = None
        self.update_connection_buttons()

    def cleanup_stitch_references(self):
        self.stitch_thread = None
        self.stitch_worker = None

    def handle_stitch_finished(self, result):
        self.pending_stitch_jobs = max(0, self.pending_stitch_jobs - 1)
        stitched_path = result.get("stitched_path")
        elapsed_ms = result.get("elapsed_ms", 0.0)
        self.ai_time.setText(f"{elapsed_ms:.0f} ms")
        if stitched_path is not None:
            stitched_path = Path(stitched_path)
            self.add_log(
                f"Zapisano obraz scalony: {stitched_path.name} "
                f"w {elapsed_ms:.0f} ms"
            )
            self.show_stitched_preview(stitched_path)

    def handle_stitch_error(self, message):
        self.pending_stitch_jobs = max(0, self.pending_stitch_jobs - 1)
        self.ai_time.setText("BLAD")
        self.add_log(f"Blad stitchingu: {message}")

    def restitch_latest_board(self):
        latest_board_directory = self._find_latest_board_directory()
        if latest_board_directory is None:
            self.add_log("Brak folderu deski do ponownego stitchingu")
            self.status_message_callback("Brak folderu deski")
            return

        image_paths = sorted(latest_board_directory.glob("*.bmp"))
        source_image_paths = [
            image_path for image_path in image_paths if image_path.name.lower() != "stitched.bmp"
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
                "folder_path": str(latest_board_directory),
                "max_horizontal_shift_px": self.settings_store.get_int(
                    "board_stitch_max_horizontal_shift_px", 36
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
            }
        )
        self.status_message_callback(f"Przestitchowanie: {latest_board_directory.name}")

    def show_stitched_preview(self, image_path):
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self.image_view.setText(image_path.name)
            self.preview_pixmap = None
            return

        rotated_pixmap = pixmap.transformed(QTransform().rotate(90), Qt.SmoothTransformation)
        self.preview_pixmap = rotated_pixmap
        self.update_preview_pixmap()

    def update_preview_pixmap(self):
        if self.preview_pixmap is None:
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

    def _find_latest_board_directory(self):
        base_directory = self.get_camera_output_directory()
        if not base_directory.exists():
            return None

        candidate_directories = []
        for directory in base_directory.iterdir():
            if not directory.is_dir():
                continue
            if any(path.name.lower() != "stitched.bmp" for path in directory.glob("*.bmp")):
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

    def shutdown(self):
        self.stop_scanner()
        self.stop_all_connections()
        if self.server_thread is not None:
            self.server_thread.wait(3000)
        if self.camera_thread is not None:
            self.camera_thread.wait(5000)
        if self.stitch_thread is not None:
            self.stitch_thread.quit()
            self.stitch_thread.wait(5000)
