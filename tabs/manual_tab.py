from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class ManualTab(QWidget):
    def __init__(self, on_restitch_latest_board=None):
        super().__init__()
        self.on_restitch_latest_board = on_restitch_latest_board
        self.create_ui()

    def create_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Tryb reczny")
        title.setObjectName("bigTitle")
        layout.addWidget(title)

        button1 = QPushButton("Wykonaj zdjecie")
        button2 = QPushButton("Uruchom test AI")
        button3 = QPushButton("Wyslij test do PLC")
        button4 = QPushButton("Przestitchuj ostatnia deske")
        button4.clicked.connect(self.handle_restitch_latest_board)

        layout.addWidget(button1)
        layout.addWidget(button2)
        layout.addWidget(button3)
        layout.addWidget(button4)
        layout.addStretch()

    def handle_restitch_latest_board(self):
        if self.on_restitch_latest_board is not None:
            self.on_restitch_latest_board()
