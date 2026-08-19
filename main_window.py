from PySide6.QtWidgets import QMainWindow, QTabWidget

from styles import APP_STYLE
from tabs.manual_tab import ManualTab
from tabs.settings_tab import SettingsTab
from tabs.view_tab import ViewTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("SpeedEyeScanner")
        self.resize_to_screen()
        self.create_ui()
        self.setStyleSheet(APP_STYLE)

    def resize_to_screen(self):
        screen = self.screen()
        if screen is None:
            return

        self.resize(screen.availableGeometry().size())
        self.showMaximized()

    def create_ui(self):
        self.tabs = QTabWidget()

        self.view_tab = ViewTab(self.show_status_message)
        self.settings_tab = SettingsTab()
        self.manual_tab = ManualTab(self.view_tab.restitch_latest_board)

        self.tabs.addTab(self.view_tab, "Podglad")
        self.tabs.addTab(self.settings_tab, "Ustawienia")
        self.tabs.addTab(self.manual_tab, "Tryb reczny")

        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("Gotowy")

    def show_status_message(self, text):
        self.statusBar().showMessage(text)

    def closeEvent(self, event):
        self.view_tab.shutdown()
        super().closeEvent(event)
