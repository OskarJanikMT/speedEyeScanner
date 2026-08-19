import socket
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


class TcpServerWorker(QObject):
    started = Signal()
    stopped = Signal()
    error = Signal(str)
    log = Signal(str)
    plc_status_changed = Signal(str, bool)
    board_context_changed = Signal(dict)

    def __init__(self, plc_host, port, bind_host="0.0.0.0"):
        super().__init__()
        self.plc_host = plc_host
        self.port = port
        self.bind_host = bind_host
        self._server_socket = None
        self._client_socket = None
        self._running = False
        self._tcp_log_path = None

    @Slot()
    def run(self):
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.bind_host, self.port))
            self._server_socket.listen(1)
            self._server_socket.settimeout(0.5)
        except OSError as exc:
            self.error.emit(
                f"Nie mozna uruchomic lokalnego TCP {self.bind_host}:{self.port} - {exc}"
            )
            self.cleanup()
            return

        self._running = True
        self._tcp_log_path = self._build_tcp_log_path()
        self.log.emit(
            f"Serwer TCP nasluchuje lokalnie na {self.bind_host}:{self.port} dla PLC {self.plc_host}"
        )
        self.log.emit(f"Log TCP zapisuje do: {self._tcp_log_path}")
        self.plc_status_changed.emit("NASLUCH", False)
        self.started.emit()

        while self._running:
            try:
                client_socket, client_address = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            self._client_socket = client_socket
            self._client_socket.settimeout(0.5)

            if self.plc_host and client_address[0] != self.plc_host:
                self.log.emit(
                    f"Odrzucono klienta spoza PLC: {client_address[0]}:{client_address[1]}"
                )
                self.close_client()
                continue

            self.log.emit(f"PLC polaczone: {client_address[0]}:{client_address[1]}")
            self.plc_status_changed.emit("POLACZONO", True)

            while self._running:
                try:
                    data = self._client_socket.recv(1024)
                except socket.timeout:
                    continue
                except OSError:
                    break

                if not data:
                    break

                message = data.decode("utf-8", errors="replace").strip()
                self._append_tcp_log(client_address, data, message)
                board_context = self._extract_board_context(data)
                if board_context is not None:
                    self.board_context_changed.emit(board_context)
                    self.log.emit(
                        "PLC bin -> "
                        f"length_mm={board_context['length_mm']} "
                        f"photo_count={board_context['photo_count']} "
                        f"hex={board_context['payload_hex']}"
                    )
                if message:
                    self.log.emit(f"PLC -> {message}")

            self.close_client()

            if self._running:
                self.log.emit("PLC rozlaczone")
                self.plc_status_changed.emit("NASLUCH", False)

        self.cleanup()
        self.stopped.emit()

    @Slot()
    def stop(self):
        self._running = False
        self.close_client()

        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass

    def close_client(self):
        if self._client_socket is not None:
            try:
                self._client_socket.close()
            except OSError:
                pass
            finally:
                self._client_socket = None

    def cleanup(self):
        self.close_client()

        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
            finally:
                self._server_socket = None

    def _build_tcp_log_path(self):
        log_directory = Path.cwd() / "logs"
        log_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return log_directory / f"tcp_raw_{timestamp}.log"

    def _append_tcp_log(self, client_address, data, message):
        if self._tcp_log_path is None:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        hex_payload = data.hex(" ")
        text_payload = message if message else "<empty-after-strip>"
        line = (
            f"[{timestamp}] {client_address[0]}:{client_address[1]} "
            f"bytes={len(data)} text={text_payload} hex={hex_payload}\n"
        )
        with self._tcp_log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(line)

    def _extract_board_context(self, data):
        if len(data) != 4:
            return None

        length_mm = int.from_bytes(data[0:2], byteorder="little", signed=True)
        photo_count = int.from_bytes(data[2:4], byteorder="little", signed=True)
        board_id = self._build_generated_board_id(length_mm, photo_count)
        return {
            "board_id": board_id,
            "length_mm": length_mm,
            "photo_count": photo_count,
            "payload_hex": data.hex(" "),
            "payload_size": len(data),
        }

    def _build_generated_board_id(self, length_mm, photo_count):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"L{length_mm}_P{photo_count}_{timestamp}"
