from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from helpers.app_settings import AppSettings


class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.settings_store = AppSettings()
        self.text_setting_inputs = {}
        self.numeric_setting_inputs = {}
        self.slider_setting_inputs = {}
        self.slider_value_labels = {}
        self.create_ui()

    def create_ui(self):
        outer_layout = QVBoxLayout(self)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)

        title = QLabel("Ustawienia")
        title.setObjectName("bigTitle")
        layout.addWidget(title)

        self.plc_address_input = QLineEdit()
        self.plc_port_input = QLineEdit()
        self.save_directory_input = QLineEdit()
        self.ai_model_path_input = QLineEdit()
        self.camera_enabled_input = QCheckBox("Wlacz kamere Baumer")
        self.camera_serial_input = QLineEdit()
        self.camera_output_directory_input = QLineEdit()
        self.camera_timeout_input = QSpinBox()
        self.camera_reconnect_input = QDoubleSpinBox()
        self.yolo_threshold_input = QDoubleSpinBox()
        self.knot_confidence_input = QDoubleSpinBox()
        self.knot_min_area_input = QSpinBox()
        self.knot_max_area_input = QSpinBox()
        self.camera_exposure_input = QSpinBox()
        self.camera_gain_input = QDoubleSpinBox()
        self.camera_brightness_input = QSpinBox()
        self.board_stitch_max_x_shift_input = QSpinBox()
        self.board_left_edge_anchor_input = QSpinBox()
        self.cut_bad_zone_offset_input = QSpinBox()
        self.board_crop_x_margin_slider = QSlider(Qt.Horizontal)
        self.board_crop_y_margin_slider = QSlider(Qt.Horizontal)
        self.board_final_crop_x_margin_slider = QSlider(Qt.Horizontal)
        self.board_active_threshold_slider = QSlider(Qt.Horizontal)

        self.text_setting_inputs = {
            "plc_address": self.plc_address_input,
            "plc_port": self.plc_port_input,
            "save_directory": self.save_directory_input,
            "ai_model_path": self.ai_model_path_input,
            "camera_serial_number": self.camera_serial_input,
            "camera_output_directory": self.camera_output_directory_input,
        }

        self.numeric_setting_inputs = {
            "camera_exposure": self.camera_exposure_input,
            "camera_gain": self.camera_gain_input,
            "camera_brightness": self.camera_brightness_input,
            "camera_receive_timeout_ms": self.camera_timeout_input,
            "camera_reconnect_interval": self.camera_reconnect_input,
            "board_stitch_max_horizontal_shift_px": self.board_stitch_max_x_shift_input,
            "board_stitch_left_edge_anchor_px": self.board_left_edge_anchor_input,
            "cut_bad_zone_offset_mm": self.cut_bad_zone_offset_input,
            "yolo_threshold": self.yolo_threshold_input,
            "knot_confidence_threshold": self.knot_confidence_input,
            "knot_min_box_area_px": self.knot_min_area_input,
            "knot_max_box_area_px": self.knot_max_area_input,
        }
        self.slider_setting_inputs = {
            "board_stitch_crop_x_margin_percent": self.board_crop_x_margin_slider,
            "board_stitch_crop_y_margin_percent": self.board_crop_y_margin_slider,
            "board_stitch_final_crop_x_margin_percent": self.board_final_crop_x_margin_slider,
            "board_stitch_active_threshold_percent": self.board_active_threshold_slider,
        }

        self.plc_address_input.setPlaceholderText("np. 192.168.3.250")
        self.plc_port_input.setPlaceholderText("np. 5000")
        self.save_directory_input.setPlaceholderText("np. C:/SpeedEyeScanner/scany")
        self.ai_model_path_input.setPlaceholderText("np. D:/SpeedEyeWoodTraining/runs/merged_tiled_continue_20260824/weights/best.onnx")
        self.camera_serial_input.setPlaceholderText("np. 70012345")
        self.camera_output_directory_input.setPlaceholderText(
            "puste = uzyj katalogu zapisu zdjec"
        )
        self.camera_timeout_input.setRange(100, 60000)
        self.camera_timeout_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.camera_timeout_input.setSuffix(" ms")
        self.camera_timeout_input.setValue(1000)
        self.camera_reconnect_input.setRange(0.5, 60.0)
        self.camera_reconnect_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.camera_reconnect_input.setDecimals(1)
        self.camera_reconnect_input.setSingleStep(0.5)
        self.camera_reconnect_input.setSuffix(" s")
        self.camera_reconnect_input.setValue(3.0)
        self.camera_exposure_input.setRange(0, 100000)
        self.camera_exposure_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.camera_exposure_input.setSuffix(" us")
        self.camera_exposure_input.setValue(40000)
        self.camera_gain_input.setRange(0.0, 100.0)
        self.camera_gain_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.camera_gain_input.setDecimals(2)
        self.camera_gain_input.setSingleStep(0.1)
        self.camera_gain_input.setSuffix(" %")
        self.camera_gain_input.setValue(1.8)
        self.camera_brightness_input.setRange(0, 100)
        self.camera_brightness_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.camera_brightness_input.setSuffix(" %")
        self.camera_brightness_input.setValue(50)
        self.board_stitch_max_x_shift_input.setRange(0, 200)
        self.board_stitch_max_x_shift_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.board_stitch_max_x_shift_input.setSuffix(" px")
        self.board_stitch_max_x_shift_input.setValue(36)
        self.board_left_edge_anchor_input.setRange(0, 1000)
        self.board_left_edge_anchor_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.board_left_edge_anchor_input.setSuffix(" px")
        self.board_left_edge_anchor_input.setValue(100)
        self.cut_bad_zone_offset_input.setRange(0, 1000)
        self.cut_bad_zone_offset_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.cut_bad_zone_offset_input.setSuffix(" mm")
        self.cut_bad_zone_offset_input.setValue(120)
        self.board_crop_x_margin_slider.setRange(0, 15)
        self.board_crop_y_margin_slider.setRange(0, 10)
        self.board_final_crop_x_margin_slider.setRange(0, 10)
        self.board_active_threshold_slider.setRange(5, 60)
        self.yolo_threshold_input.setRange(0.0, 1.0)
        self.yolo_threshold_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.yolo_threshold_input.setDecimals(4)
        self.yolo_threshold_input.setSingleStep(0.0005)
        self.yolo_threshold_input.setValue(0.2500)
        self.knot_confidence_input.setRange(0.0, 1.0)
        self.knot_confidence_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.knot_confidence_input.setDecimals(4)
        self.knot_confidence_input.setSingleStep(0.0005)
        self.knot_confidence_input.setValue(0.2500)
        self.knot_min_area_input.setRange(0, 200000)
        self.knot_min_area_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.knot_min_area_input.setSuffix(" px2")
        self.knot_min_area_input.setValue(400)
        self.knot_max_area_input.setRange(0, 200000)
        self.knot_max_area_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.knot_max_area_input.setSuffix(" px2")
        self.knot_max_area_input.setValue(0)
        self.camera_enabled_input.toggled.connect(
            lambda checked: self.save_setting("camera_enabled", "true" if checked else "false")
        )

        plc_layout = QHBoxLayout()
        plc_layout.setContentsMargins(0, 0, 0, 0)
        plc_layout.setSpacing(8)
        plc_layout.addWidget(self.plc_address_input, 1)
        plc_layout.addWidget(QLabel(":"))
        plc_layout.addWidget(self.plc_port_input)
        self.plc_connection_layout = plc_layout

        self.board_crop_x_margin_layout = self.create_slider_layout(
            self.board_crop_x_margin_slider,
            "4 %",
        )
        self.board_crop_y_margin_layout = self.create_slider_layout(
            self.board_crop_y_margin_slider,
            "2 %",
        )
        self.board_final_crop_x_margin_layout = self.create_slider_layout(
            self.board_final_crop_x_margin_slider,
            "3 %",
        )
        self.board_active_threshold_layout = self.create_slider_layout(
            self.board_active_threshold_slider,
            "28 %",
        )

        layout.addWidget(self.create_plc_settings_widget())
        layout.addWidget(self.create_ai_settings_widget())
        layout.addWidget(self.create_camera_settings_widget())
        layout.addStretch()

        scroll_area.setWidget(content_widget)
        outer_layout.addWidget(scroll_area)

        self.load_settings()
        self.install_numeric_cursor_guards()

        for key, widget in self.text_setting_inputs.items():
            widget.textChanged.connect(
                lambda text, setting_key=key: self.save_setting(setting_key, text)
            )

        for key, widget in self.numeric_setting_inputs.items():
            widget.valueChanged.connect(
                lambda value, setting_key=key: self.save_setting(setting_key, str(value))
            )
        for key, widget in self.slider_setting_inputs.items():
            widget.valueChanged.connect(
                lambda value, setting_key=key: self.handle_slider_setting_change(setting_key, value)
            )

    def load_settings(self):
        for key, widget in self.text_setting_inputs.items():
            widget.setText(self.settings_store.get(key))

        self.camera_exposure_input.setValue(
            self.settings_store.get_int("camera_exposure", 40000)
        )
        self.camera_gain_input.setValue(
            self.settings_store.get_float("camera_gain", 1.8)
        )
        self.camera_brightness_input.setValue(
            self.settings_store.get_int("camera_brightness", 50)
        )
        self.board_stitch_max_x_shift_input.setValue(
            self.settings_store.get_int("board_stitch_max_horizontal_shift_px", 36)
        )
        self.board_left_edge_anchor_input.setValue(
            self.settings_store.get_int("board_stitch_left_edge_anchor_px", 100)
        )
        self.cut_bad_zone_offset_input.setValue(
            self.settings_store.get_int("cut_bad_zone_offset_mm", 120)
        )
        self.board_crop_x_margin_slider.setValue(
            self.settings_store.get_int("board_stitch_crop_x_margin_percent", 4)
        )
        self.board_crop_y_margin_slider.setValue(
            self.settings_store.get_int("board_stitch_crop_y_margin_percent", 2)
        )
        self.board_final_crop_x_margin_slider.setValue(
            self.settings_store.get_int("board_stitch_final_crop_x_margin_percent", 3)
        )
        self.board_active_threshold_slider.setValue(
            self.settings_store.get_int("board_stitch_active_threshold_percent", 28)
        )
        self.camera_timeout_input.setValue(
            self.settings_store.get_int("camera_receive_timeout_ms", 1000)
        )
        self.camera_reconnect_input.setValue(
            self.settings_store.get_float("camera_reconnect_interval", 3.0)
        )
        self.camera_enabled_input.setChecked(
            self.settings_store.get("camera_enabled", "false").lower() == "true"
        )

        threshold_text = self.settings_store.get("yolo_threshold", "0.2500")
        try:
            threshold_value = float(threshold_text)
        except ValueError:
            threshold_value = 0.2500
        self.yolo_threshold_input.setValue(max(0.0, min(1.0, threshold_value)))

        knot_confidence_text = self.settings_store.get("knot_confidence_threshold", "0.2500")
        try:
            knot_confidence_value = float(knot_confidence_text)
        except ValueError:
            knot_confidence_value = 0.2500
        self.knot_confidence_input.setValue(max(0.0, min(1.0, knot_confidence_value)))
        self.knot_min_area_input.setValue(
            self.settings_store.get_int("knot_min_box_area_px", 400)
        )
        self.knot_max_area_input.setValue(
            self.settings_store.get_int("knot_max_box_area_px", 0)
        )

    def save_setting(self, key, value):
        self.settings_store.set(key, value)

    def create_slider_layout(self, slider, initial_text):
        value_label = QLabel(initial_text)
        value_label.setMinimumWidth(40)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.slider_value_labels[slider] = value_label

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(slider)
        layout.addWidget(value_label)
        return layout

    def create_tooltip_label(self, text, tooltip):
        label = QLabel(text)
        label.setToolTip(tooltip)
        return label

    def install_numeric_cursor_guards(self):
        for widget in self.numeric_setting_inputs.values():
            editor = widget.lineEdit()
            editor.installEventFilter(self)
            editor.cursorPositionChanged.connect(
                lambda old_pos, new_pos, current_widget=widget: self.ensure_cursor_before_suffix(current_widget)
            )

    def ensure_cursor_before_suffix(self, widget):
        editor = widget.lineEdit()
        max_position = len(widget.cleanText())
        if editor.cursorPosition() > max_position:
            editor.setCursorPosition(max_position)

    def create_plc_settings_widget(self):
        plc_panel = QFrame()
        plc_panel.setObjectName("panel")

        plc_panel_layout = QVBoxLayout(plc_panel)

        plc_title = QLabel("Ustawienia komunikacji PLC")
        plc_title.setObjectName("title")
        plc_panel_layout.addWidget(plc_title)

        plc_form_layout = QFormLayout()
        plc_form_layout.setSpacing(12)
        plc_form_layout.addRow("TCP PLC adress:", self.plc_connection_layout)

        plc_panel_layout.addLayout(plc_form_layout)

        return plc_panel

    def create_ai_settings_widget(self):
        ai_panel = QFrame()
        ai_panel.setObjectName("panel")

        ai_panel_layout = QVBoxLayout(ai_panel)

        ai_title = QLabel("Ustawienia modelu AI")
        ai_title.setObjectName("title")
        ai_panel_layout.addWidget(ai_title)

        ai_form_layout = QFormLayout()
        ai_form_layout.setSpacing(12)
        ai_form_layout.addRow(
            self.create_tooltip_label(
                "Prog modelu YOLO:",
                "Minimalny confidence, od ktorego model w ogole zwraca kandydatow.",
            ),
            self.yolo_threshold_input,
        )
        ai_form_layout.addRow(
            self.create_tooltip_label(
                "Min. confidence sęka:",
                "Detekcje ponizej tej wartosci nie beda liczone ani rysowane na czerwono.",
            ),
            self.knot_confidence_input,
        )
        ai_form_layout.addRow(
            self.create_tooltip_label(
                "Min. pole sęka:",
                "Odrzuca bardzo male detekcje na podstawie pola boxa w pikselach.",
            ),
            self.knot_min_area_input,
        )
        ai_form_layout.addRow(
            self.create_tooltip_label(
                "Max. pole sęka:",
                "Odrzuca bardzo duze detekcje. Wartosc 0 oznacza brak limitu.",
            ),
            self.knot_max_area_input,
        )
        ai_form_layout.addRow(
            self.create_tooltip_label(
                "Sciezka modelu AI:",
                "Pelna sciezka do aktualnie uzywanego modelu .pt albo .onnx. Puste pole = domyslne D:/SpeedEyeWoodTraining/runs/datasetV1_tiled_v1/weights/best.pt. Zmiana przeladuje model przy kolejnym skanie.",
            ),
            self.ai_model_path_input,
        )
        ai_form_layout.addRow("Katalog zapisu zdjec:", self.save_directory_input)

        ai_panel_layout.addLayout(ai_form_layout)

        return ai_panel

    def create_camera_settings_widget(self):
        camera_panel = QFrame()
        camera_panel.setObjectName("panel")

        camera_layout = QVBoxLayout(camera_panel)

        camera_title = QLabel("Ustawienia kamery")
        camera_title.setObjectName("title")
        camera_layout.addWidget(camera_title)

        camera_form_layout = QFormLayout()
        camera_form_layout.setSpacing(12)
        camera_form_layout.addRow("", self.camera_enabled_input)
        camera_form_layout.addRow("Serial kamery:", self.camera_serial_input)
        camera_form_layout.addRow(
            "Katalog zdjec kamery:", self.camera_output_directory_input
        )
        camera_form_layout.addRow("Timeout odbioru:", self.camera_timeout_input)
        camera_form_layout.addRow("Reconnect:", self.camera_reconnect_input)
        camera_form_layout.addRow("Ekspozycja:", self.camera_exposure_input)
        camera_form_layout.addRow("Gain:", self.camera_gain_input)
        camera_form_layout.addRow("Jasnosc:", self.camera_brightness_input)
        camera_form_layout.addRow(
            self.create_tooltip_label(
                "Max przesuniecie X deski:",
                "Maksymalna roznica polozenia lewej i prawej krawedzi deski miedzy zdjeciami.",
            ),
            self.board_stitch_max_x_shift_input,
        )
        camera_form_layout.addRow(
            self.create_tooltip_label(
                "Kotwica lewej krawedzi:",
                "Przyblizona pozycja lewej krawedzi deski. Algorytm szuka krawedzi lokalnie w okolicy tej pozycji, a nie na calym obrazie.",
            ),
            self.board_left_edge_anchor_input,
        )
        camera_form_layout.addRow(
            self.create_tooltip_label(
                "+margines ciecia:",
                "Poszerza obszar odrzutu przed i za sekami o zadany zapas dla pily.",
            ),
            self.cut_bad_zone_offset_input,
        )
        camera_form_layout.addRow(
            self.create_tooltip_label(
                "Margines X crop klatki:",
                "Dodaje boczny zapas do wykrytej szerokosci deski w pojedynczej klatce.",
            ),
            self.board_crop_x_margin_layout,
        )
        camera_form_layout.addRow(
            self.create_tooltip_label(
                "Margines Y crop klatki:",
                "Dodaje pionowy zapas przy obcieciu poczatku i konca deski na pierwszej i ostatniej klatce.",
            ),
            self.board_crop_y_margin_layout,
        )
        camera_form_layout.addRow(
            self.create_tooltip_label(
                "Margines X crop final:",
                "Dodaje boczny zapas po zlozeniu wszystkich zdjec w jeden obraz.",
            ),
            self.board_final_crop_x_margin_layout,
        )
        camera_form_layout.addRow(
            self.create_tooltip_label(
                "Prog wykrycia deski:",
                "Okresla jak mocno piksel musi odrozniac sie od tla, zeby zaliczyc go do obszaru deski.",
            ),
            self.board_active_threshold_layout,
        )

        camera_layout.addLayout(camera_form_layout)

        return camera_panel

    def handle_slider_setting_change(self, key, value):
        label = self.slider_value_labels.get(self.slider_setting_inputs[key])
        if label is not None:
            label.setText(f"{int(value)} %")
        self.save_setting(key, str(value))

    def eventFilter(self, watched, event):
        for widget in self.numeric_setting_inputs.values():
            if watched is not widget.lineEdit():
                continue

            if event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
                QTimer.singleShot(0, lambda current_widget=widget: self.ensure_cursor_before_suffix(current_widget))
                break

        return super().eventFilter(watched, event)
