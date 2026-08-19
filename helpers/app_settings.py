from PySide6.QtCore import QSettings


class AppSettings:
    def __init__(self):
        self.store = QSettings("SpeedEyeScanner", "SpeedEyeScanner")

    def get(self, key, default=""):
        return self.store.value(key, default, type=str)

    def get_int(self, key, default=0):
        return self.store.value(key, default, type=int)

    def get_float(self, key, default=0.0):
        return self.store.value(key, default, type=float)

    def set(self, key, value):
        self.store.setValue(key, value)
