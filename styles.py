APP_STYLE = """
    QMainWindow {
        background-color: #0f1115;
    }

    QWidget {
        background-color: #0f1115;
        color: #e8e8e8;
        font-size: 14px;
    }

    QTabWidget::pane {
        border: none;
    }

    QTabBar::tab {
        background: #161a20;
        color: #9ba6b5;
        padding: 14px 24px;
        margin-right: 2px;
    }

    QTabBar::tab:selected {
        background: #222831;
        color: white;
    }

    QFrame#panel {
        background-color: #161a20;
        border: 1px solid #202630;
        border-radius: 4px;
    }

    QLabel#title {
        font-size: 16px;
        font-weight: bold;
    }

    QLabel#bigTitle {
        font-size: 22px;
        font-weight: bold;
    }

    QLabel {
        background-color: transparent;
    }

    QLabel#imageView {
        background-color: #0b0d11;
        border: 1px solid #202630;
        color: #708096;
        font-size: 18px;
    }

    QPushButton {
        background-color: #222831;
        border: none;
        padding: 12px 20px;
        border-radius: 4px;
    }

    QPushButton:hover {
        background-color: #2c3440;
    }

    QPushButton:pressed {
        background-color: #1b2027;
    }

    QPushButton#startButton {
        background-color: #2f8bea;
        color: white;
        font-size: 16px;
        font-weight: bold;
    }

    QPushButton#startButton:hover {
        background-color: #409cff;
    }

    QPushButton#startButton[running="true"] {
        background-color: #d64545;
    }

    QPushButton#startButton[running="true"]:hover {
        background-color: #ee5656;
    }

    QLineEdit {
        background-color: #161a20;
        border: 1px solid #202630;
        border-radius: 4px;
        padding: 10px 12px;
        color: #e8e8e8;
    }

    QLineEdit:focus {
        border: 1px solid #2f8bea;
    }

    QSpinBox, QDoubleSpinBox {
        background-color: #161a20;
        border: 1px solid #202630;
        border-radius: 4px;
        padding: 10px 12px;
        color: #e8e8e8;
    }

    QSpinBox:focus, QDoubleSpinBox:focus {
        border: 1px solid #2f8bea;
    }

    QSlider {
        background-color: transparent;
    }

    QSlider::groove:horizontal {
        background: transparent;
        border: none;
        height: 6px;
    }

    QSlider::sub-page:horizontal {
        background: #2f8bea;
        border-radius: 3px;
    }

    QSlider::add-page:horizontal {
        background: #202630;
        border-radius: 3px;
    }

    QSlider::handle:horizontal {
        background: #e8e8e8;
        border: none;
        width: 14px;
        margin: -4px 0;
        border-radius: 7px;
    }

    QPlainTextEdit {
        background-color: #0b0d11;
        border: none;
        color: #cdd6e0;
        font-family: Consolas;
        font-size: 12px;
    }

    QStatusBar {
        background-color: #0f1115;
        color: #8e99a8;
    }
"""
