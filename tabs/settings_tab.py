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
        self.camera_enabled_input = QCheckBox("Wlacz kamere Baumer")
        self.camera_serial_input = QLineEdit()
        self.camera_output_directory_input = QLineEdit()
        self.camera_timeout_input = QSpinBox()
        self.camera_reconnect_input = QDoubleSpinBox()
        self.yolo_threshold_slider = QSlider(Qt.Horizontal)
        self.yolo_threshold_value = QLabel("0.45")
        self.camera_exposure_input = QSpinBox()
        self.camera_gain_input = QDoubleSpinBox()
        self.camera_brightness_input = QSpinBox()
        self.board_stitch_max_x_shift_input = QSpinBox()
        self.board_crop_x_margin_slider = QSlider(Qt.Horizontal)
        self.board_crop_y_margin_slider = QSlider(Qt.Horizontal)
        self.board_final_crop_x_margin_slider = QSlider(Qt.Horizontal)
        self.board_active_threshold_slider = QSlider(Qt.Horizontal)

        self.text_setting_inputs = {
            "plc_address": self.plc_address_input,
            "plc_port": self.plc_port_input,
            "save_directory": self.save_directory_input,
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
        self.board_crop_x_margin_slider.setRange(0, 15)
        self.board_crop_y_margin_slider.setRange(0, 10)
        self.board_final_crop_x_margin_slider.setRange(0, 10)
        self.board_active_threshold_slider.setRange(5, 60)
        self.yolo_threshold_slider.setRange(0, 100)
        self.yolo_threshold_slider.setValue(45)
        self.yolo_threshold_slider.valueChanged.connect(self.handle_yolo_threshold_change)
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

        threshold_layout = QHBoxLayout()
        threshold_layout.setContentsMargins(0, 0, 0, 0)
        threshold_layout.addWidget(self.yolo_threshold_slider)
        threshold_layout.addWidget(self.yolo_threshold_value)
        self.ai_threshold_layout = threshold_layout

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

        threshold_text = self.settings_store.get("yolo_threshold", "0.45")
        try:
            threshold_value = float(threshold_text)
        except ValueError:
            threshold_value = 0.45

        slider_value = max(0, min(100, int(round(threshold_value * 100))))
        self.yolo_threshold_slider.setValue(slider_value)
        self.update_yolo_threshold_label(slider_value)

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
        ai_form_layout.addRow("Prog wykrywania sekow:", self.ai_threshold_layout)
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

    def handle_yolo_threshold_change(self, value):
        self.update_yolo_threshold_label(value)
        self.save_setting("yolo_threshold", f"{value / 100:.2f}")

    def update_yolo_threshold_label(self, value):
        self.yolo_threshold_value.setText(f"{value / 100:.2f}")

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
