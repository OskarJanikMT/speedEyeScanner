import socket
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


class TcpServerWorker(QObject):
    FRAME_SIZE_BYTES = 10

    started = Signal()
    stopped = Signal()
    error = Signal(str)
    log = Signal(str)
    plc_status_changed = Signal(str, bool)
    board_context_changed = Signal(dict)

    def __init__(self, plc_host, port, reconnect_interval_seconds=3.0):
        super().__init__()
        self.plc_host = plc_host
        self.port = port
        self.reconnect_interval_seconds = max(0.5, float(reconnect_interval_seconds))
        self._client_socket = None
        self._running = False
        self._tcp_log_path = None
        self._receive_buffer = bytearray()
        self._started_emitted = False

    @Slot()
    def run(self):
        self._running = True
        self._tcp_log_path = self._build_tcp_log_path()
        self.log.emit(f"Klient TCP PLC zapisuje log do: {self._tcp_log_path}")
        self.plc_status_changed.emit("ROZLACZONE", False)

        while self._running:
            if not self.plc_host or not self.port:
                self.error.emit("Brak konfiguracji TCP PLC")
                break

            self.plc_status_changed.emit("LACZENIE", False)
            self.log.emit(f"Laczenie z PLC {self.plc_host}:{self.port}...")

            try:
                self._connect_client()
            except OSError as exc:
                self.log.emit(
                    f"Nie mozna polaczyc z PLC {self.plc_host}:{self.port} - {exc}"
                )
                self.plc_status_changed.emit("ROZLACZONE", False)
                if not self._running:
                    break
                time.sleep(self.reconnect_interval_seconds)
                continue

            if not self._started_emitted:
                self.started.emit()
                self._started_emitted = True

            self.log.emit(f"PLC polaczone: {self.plc_host}:{self.port}")
            self.plc_status_changed.emit("POLACZONO", True)
            self._receive_buffer.clear()

            while self._running:
                try:
                    data = self._client_socket.recv(1024)
                except socket.timeout:
                    continue
                except OSError as exc:
                    self.log.emit(f"Blad odbioru z PLC: {exc}")
                    break

                if not data:
                    self.log.emit("PLC zamknelo polaczenie")
                    break

                message = data.decode("utf-8", errors="replace").strip()
                self._append_tcp_log((self.plc_host, self.port), data, message)
                board_contexts = self._extract_board_contexts(data)
                for board_context in board_contexts:
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
            self.plc_status_changed.emit("ROZLACZONE", False)

            if self._running:
                self.log.emit(
                    f"Ponawianie polaczenia z PLC za {self.reconnect_interval_seconds:.1f} s"
                )
                time.sleep(self.reconnect_interval_seconds)

        self.cleanup()
        self.stopped.emit()

    @Slot()
    def stop(self):
        self._running = False
        self.close_client()

    def _connect_client(self):
        self.close_client()
        self._client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._client_socket.settimeout(3.0)
        self._client_socket.connect((self.plc_host, self.port))
        self._client_socket.settimeout(0.5)

    def close_client(self):
        if self._client_socket is not None:
            try:
                self._client_socket.close()
            except OSError:
                pass
            finally:
                self._client_socket = None
        self._receive_buffer.clear()

    def cleanup(self):
        self.close_client()

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

    def _extract_board_contexts(self, data):
        self._receive_buffer.extend(data)
        board_contexts = []

        while len(self._receive_buffer) >= self.FRAME_SIZE_BYTES:
            frame = bytes(self._receive_buffer[: self.FRAME_SIZE_BYTES])
            del self._receive_buffer[: self.FRAME_SIZE_BYTES]
            board_contexts.append(self._build_board_context(frame))

        if self._receive_buffer:
            self.log.emit(
                "PLC stream buffer oczekuje na "
                f"{self.FRAME_SIZE_BYTES - len(self._receive_buffer)} bajt(y) do pelnej ramki "
                f"({self.FRAME_SIZE_BYTES} B)"
            )

        return board_contexts

    def _build_board_context(self, frame):
        words = [
            int.from_bytes(frame[index : index + 2], byteorder="little", signed=True)
            for index in range(0, len(frame), 2)
        ]
        encoder_length = (
            self._combine_words_to_dint(words[0], words[1]) if len(words) >= 2 else None
        )
        length_mm = (
            self._combine_words_to_dint(words[2], words[3]) if len(words) >= 4 else None
        )
        photo_count = words[4] if len(words) >= 5 else None
        board_id = self._build_generated_board_id(length_mm, photo_count)
        return {
            "board_id": board_id,
            "encoder_length": encoder_length,
            "length_mm": length_mm,
            "photo_count": photo_count,
            "frame_words": words,
            "payload_hex": frame.hex(" "),
            "payload_size": len(frame),
        }

    def _combine_words_to_dint(self, low_word, high_word):
        low = int(low_word) & 0xFFFF
        high = int(high_word) & 0xFFFF
        value = low | (high << 16)
        if value >= 0x80000000:
            value -= 0x100000000
        return value

    def _build_generated_board_id(self, length_mm, photo_count):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"L{length_mm}_P{photo_count}_{timestamp}"
