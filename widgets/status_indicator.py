from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StatusIndicator(QWidget):
    def __init__(self, name, status="OFFLINE", active=False):
        super().__init__()

        self.name_label = QLabel(name)
        self.dot = QLabel("●")
        self.status_label = QLabel(status)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self.name_label)
        layout.addWidget(self.dot)
        layout.addWidget(self.status_label)

        self.set_status(status, active)

    def set_status(self, text, active):
        self.status_label.setText(text)
        self.dot.setStyleSheet(
            "color: #3ddc84;" if active else "color: #e05252;"
        )
