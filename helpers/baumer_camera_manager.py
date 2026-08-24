import logging
import queue
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


LOGGER = logging.getLogger(__name__)


@dataclass
class CameraSettings:
    enabled: bool = False
    serial_number: str = ""
    output_directory: str = ""
    width_px: int = 2000
    height_px: int = 976
    exposure_us: int = 1200
    gain_value: float = 1.8
    brightness_value: int = 50
    receive_timeout_ms: int = 1000
    reconnect_interval_seconds: float = 3.0
    queue_size: int = 256


@dataclass
class CameraSnapshot:
    image: object
    metadata: dict


class BaumerCameraManager:
    STATE_DISCONNECTED = "DISCONNECTED"
    STATE_CONNECTING = "CONNECTING"
    STATE_CONNECTED = "CONNECTED"
    STATE_ACQUIRING = "ACQUIRING"
    STATE_ERROR = "ERROR"

    def __init__(
        self,
        settings: CameraSettings,
        on_log: Optional[Callable[[str], None]] = None,
        on_status_changed: Optional[Callable[[str], None]] = None,
        on_image_saved: Optional[Callable[[str, dict], None]] = None,
    ):
        self.settings = settings
        self.on_log = on_log
        self.on_status_changed = on_status_changed
        self.on_image_saved = on_image_saved

        self._stop_event = threading.Event()
        self._writer_stop_event = threading.Event()
        self._writer_thread: Optional[threading.Thread] = None
        self._save_queue: queue.Queue[CameraSnapshot] = queue.Queue(
            maxsize=max(1, settings.queue_size)
        )
        self._sequence_lock = threading.Lock()
        self._sequence = 0
        self._last_timeout_log_at = 0.0
        self._queue_full_logged = False
        self._received_frames_count = 0
        self._saved_frames_count = 0
        self._save_errors_count = 0
        self._last_received_monotonic = None
        self._neoapi = None
        self._camera = None
        self._state = self.STATE_DISCONNECTED

    def run_forever(self):
        if not self.settings.enabled:
            self._set_state(self.STATE_DISCONNECTED)
            self._log("Baumer camera disabled in settings")
            return

        self._start_writer_thread()

        try:
            self._neoapi = self._load_neoapi()
            while not self._stop_event.is_set():
                try:
                    self._connect_and_start_acquisition()
                    self._acquisition_loop()
                except Exception as exc:
                    self._set_state(self.STATE_ERROR)
                    self._log(f"acquisition error: {exc}")
                finally:
                    self._disconnect_camera()

                if self._stop_event.is_set():
                    break

                self._set_state(self.STATE_DISCONNECTED)
                self._log("reconnecting...")
                self._stop_event.wait(max(0.5, self.settings.reconnect_interval_seconds))
        finally:
            self.stop()
            if self._writer_thread is not None:
                self._writer_thread.join(timeout=5)
            self._set_state(self.STATE_DISCONNECTED)

    def stop(self):
        self._stop_event.set()
        self._writer_stop_event.set()
        self._disconnect_camera()

    def _start_writer_thread(self):
        if self._writer_thread is not None:
            return

        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="BaumerImageWriter",
            daemon=True,
        )
        self._writer_thread.start()

    def _load_neoapi(self):
        try:
            import neoapi  # type: ignore

            return neoapi
        except ImportError:
            desktop_sdk_root = Path.home() / "Desktop" / "Baumer_neoAPI_1.6.0_win_x86_64_python"
            wheel_dir = desktop_sdk_root / "wheel"
            wheel_candidates = sorted(wheel_dir.glob("baumer_neoapi-*.whl"))
            for wheel_path in wheel_candidates:
                wheel_str = str(wheel_path)
                if wheel_str not in sys.path:
                    sys.path.append(wheel_str)
                try:
                    import neoapi  # type: ignore

                    self._log(f"Loaded neoAPI from {wheel_path}")
                    return neoapi
                except ImportError:
                    continue

        raise RuntimeError(
            "neoAPI is not available. Install a Baumer neoAPI build compatible with the Python interpreter used by this application."
        )

    def _connect_and_start_acquisition(self):
        self._set_state(self.STATE_CONNECTING)
        info = self._select_camera_info()
        self._log(
            "Baumer camera found: "
            f"{info['model']} SN: {info['serial']} IP: {info['ip'] or 'n/a'}"
        )
        self._log("Connecting...")

        camera = self._neoapi.Cam()
        connect_id = info["id"] or info["ip"] or None
        if connect_id:
            camera.Connect(connect_id)
        else:
            camera.Connect()

        self._camera = camera
        self._set_state(self.STATE_CONNECTED)
        self._log("Connected")

        self._configure_runtime_features()
        if hasattr(self._camera, "SetImageBufferCount"):
            try:
                self._camera.SetImageBufferCount(max(8, self.settings.queue_size))
            except Exception:
                pass

        if hasattr(self._camera, "StartStreaming"):
            self._camera.StartStreaming()

        self._set_state(self.STATE_ACQUIRING)
        self._log("Acquisition started")
        self._log("Waiting for hardware trigger...")

    def _select_camera_info(self):
        info_list = self._neoapi.CamInfoList.Get()
        try:
            info_list.Refresh()
        except Exception:
            pass
        camera_infos = list(self._iterate_camera_infos(info_list))
        if not camera_infos:
            raise RuntimeError("No Baumer camera found")

        selected = None
        requested_serial = self.settings.serial_number.strip()
        if requested_serial:
            for info in camera_infos:
                if self._safe_call(info.GetSerialNumber, "") == requested_serial:
                    selected = info
                    break
            if selected is None:
                raise RuntimeError(
                    f"Configured Baumer camera serial not found: {requested_serial}"
                )
        elif len(camera_infos) == 1:
            selected = camera_infos[0]
        else:
            available = ", ".join(
                self._safe_call(info.GetSerialNumber, "unknown")
                for info in camera_infos
            )
            raise RuntimeError(
                "Multiple Baumer cameras detected. Configure camera_serial_number. "
                f"Available serials: {available}"
            )

        return {
            "id": self._safe_call(selected.GetId, ""),
            "model": self._safe_call(selected.GetModelName, "unknown"),
            "serial": self._safe_call(selected.GetSerialNumber, "unknown"),
            "ip": self._safe_call(selected.GetGevIpAddress, ""),
        }

    def _iterate_camera_infos(self, info_list):
        try:
            for item in info_list:
                yield item
            return
        except TypeError:
            pass

        for getter_name in ("Get", "ToList"):
            getter = getattr(info_list, getter_name, None)
            if getter is None:
                continue
            try:
                result = getter()
            except TypeError:
                continue

            try:
                for item in result:
                    yield item
                return
            except TypeError:
                pass

    def _configure_runtime_features(self):
        self._configure_trigger_features()
        self._configure_transport_features()
        self._configure_image_geometry()
        self._configure_line4_output()
        self._apply_manual_image_settings()

        trigger_selector = self._feature_get("TriggerSelector")
        trigger_mode = self._feature_get("TriggerMode")
        trigger_source = self._feature_get("TriggerSource")
        trigger_activation = self._feature_get("TriggerActivation")
        trigger_delay = self._feature_get("TriggerDelay")
        packet_size = self._feature_get("GevSCPSPacketSize")
        packet_delay = self._feature_get("GevSCPD")
        throughput_limit = self._feature_get("DeviceLinkThroughputLimit")

        if trigger_selector is not None:
            self._log(f"TriggerSelector: {self._format_feature_value('TriggerSelector', trigger_selector)}")
        if trigger_mode is not None:
            self._log(
                f"TriggerMode: {self._format_feature_value('TriggerMode', trigger_mode)}"
            )
        if trigger_source is not None:
            self._log(
                f"TriggerSource: {self._format_feature_value('TriggerSource', trigger_source)}"
            )
        if trigger_activation is not None:
            self._log(
                f"TriggerActivation: {self._format_feature_value('TriggerActivation', trigger_activation)}"
            )
        if trigger_delay is not None:
            self._log(f"TriggerDelay: {trigger_delay}")
        if packet_size is not None:
            self._log(f"GevSCPSPacketSize: {packet_size}")
        if packet_delay is not None:
            self._log(f"GevSCPD: {packet_delay}")
        if throughput_limit is not None:
            self._log(f"DeviceLinkThroughputLimit: {throughput_limit}")

    def _configure_image_geometry(self):
        width_px = max(1, int(self.settings.width_px))
        height_px = max(1, int(self.settings.height_px))

        width_set = self._feature_set_numeric_clamped("Width", width_px)
        height_set = self._feature_set_numeric_clamped("Height", height_px)

        if width_set or height_set:
            current_width = self._feature_get("Width")
            current_height = self._feature_get("Height")
            self._log(
                f"Image size set to {current_width or width_px}x{current_height or height_px}"
            )

    def _configure_line4_output(self):
        line_selector_line4 = self._enum_constant("LineSelector_Line4")
        if line_selector_line4 is not None:
            self._feature_set("LineSelector", line_selector_line4)
        else:
            self._feature_set("LineSelector", "Line4")

        line_inverter_targets = (
            ("LineInverter", True),
            ("LineLogic", True),
        )
        line_inverter_set = self._try_set_first_available(line_inverter_targets)

        line_source_set = False
        for candidate in ("UserOutput1", "User Output 1"):
            if self._try_set_first_available((("LineSource", candidate),)):
                line_source_set = True
                break

        if line_inverter_set or line_source_set:
            current_line_inverter = self._feature_get("LineInverter")
            current_line_source = self._feature_get("LineSource")
            self._log(
                "Line4 configured: "
                f"LineInverter={current_line_inverter if current_line_inverter is not None else True}, "
                f"LineSource={current_line_source if current_line_source is not None else 'User Output 1'}"
            )

    def _configure_trigger_features(self):
        trigger_selector_frame_start = self._enum_constant("TriggerSelector_FrameStart")
        if trigger_selector_frame_start is not None:
            self._feature_set("TriggerSelector", trigger_selector_frame_start)

        trigger_mode = self._feature_get("TriggerMode")
        trigger_mode_on = self._enum_constant("TriggerMode_On")
        if trigger_mode is not None and trigger_mode_on is not None and trigger_mode != trigger_mode_on:
            self._log(
                f"TriggerMode is {self._format_feature_value('TriggerMode', trigger_mode)}, attempting to switch to On"
            )
            self._feature_set("TriggerMode", trigger_mode_on)

        trigger_source_line1 = self._enum_constant("TriggerSource_Line1")
        if trigger_source_line1 is not None:
            self._feature_set("TriggerSource", trigger_source_line1)

        trigger_overlap_readout = self._enum_constant("TriggerOverlap_ReadOut")
        if trigger_overlap_readout is not None:
            self._feature_set("TriggerOverlap", trigger_overlap_readout)

        self._try_set_first_available(
            (
                ("TriggerDelay", 0.0),
                ("TriggerDelayAbs", 0.0),
                ("LineDebouncerTime", 0.0),
                ("LineDebouncerHighTimeAbs", 0.0),
                ("LineDebouncerLowTimeAbs", 0.0),
            )
        )

        short_exposure_enable = self._enum_constant("ShortExposureTimeEnable_On")
        if short_exposure_enable is not None:
            self._feature_set("ShortExposureTimeEnable", short_exposure_enable)
        else:
            self._try_set_first_available(
                (
                    ("ShortExposureTimeEnable", True),
                )
            )

    def _configure_transport_features(self):
        device_link_mode_on = self._enum_constant("DeviceLinkThroughputLimitMode_On")
        if device_link_mode_on is not None:
            self._feature_set("DeviceLinkThroughputLimitMode", device_link_mode_on)
        self._feature_set_numeric_fraction("DeviceLinkThroughputLimit", 0.90)
        self._feature_set_numeric_max("GevSCPSPacketSize")
        # Keep a small gap between GigE packets so the host NIC/driver can recover.
        self._feature_set_numeric_clamped("GevSCPD", preferred_value=7200)
        self._feature_set_numeric_clamped("InterPacketDelay", preferred_value=7200)

    def _apply_manual_image_settings(self):
        exposure_us = int(max(0, self.settings.exposure_us))
        gain_value = float(self.settings.gain_value)
        brightness_value = int(self.settings.brightness_value)

        exposure_auto = self._feature_get("ExposureAuto")
        exposure_auto_off = self._enum_constant("ExposureAuto_Off")
        if (
            exposure_auto is not None
            and exposure_auto_off is not None
            and exposure_auto != exposure_auto_off
        ):
            self._feature_set("ExposureAuto", exposure_auto_off)
        if self._try_set_first_available(
            (
                ("ExposureTime", exposure_us),
                ("ExposureTimeRaw", exposure_us),
            )
        ):
            self._log(f"Exposure set from app: {self.settings.exposure_us} us")

        gain_auto = self._feature_get("GainAuto")
        gain_auto_off = self._enum_constant("GainAuto_Off")
        if gain_auto is not None and gain_auto_off is not None and gain_auto != gain_auto_off:
            self._feature_set("GainAuto", gain_auto_off)
        if self._try_set_first_available(
            (
                ("Gain", gain_value),
                ("GainRaw", int(round(gain_value))),
            )
        ):
            self._log(f"Gain set from app: {gain_value}")

        brightness_targets = (
            ("BrightnessCorrection", brightness_value),
            ("BlackLevel", brightness_value),
            ("BlackLevelRaw", brightness_value),
        )
        if self._try_set_first_available(brightness_targets):
            self._log(f"Brightness set from app: {brightness_value}")
        else:
            self._log("Brightness feature not available on this camera")

    def _acquisition_loop(self):
        while not self._stop_event.is_set():
            try:
                image = self._camera.GetImage(int(self.settings.receive_timeout_ms))
            except Exception as exc:
                if self._is_timeout_exception(exc):
                    self._log_timeout()
                    continue
                raise

            if image is None or image.IsEmpty():
                continue

            receive_monotonic = time.monotonic()
            gap_ms = None
            if self._last_received_monotonic is not None:
                gap_ms = (receive_monotonic - self._last_received_monotonic) * 1000.0
            self._last_received_monotonic = receive_monotonic

            frame_identifiers = self._extract_frame_identifiers(image)
            frame_id = frame_identifiers["frame_id"]
            self._received_frames_count += 1
            received_at = datetime.now()
            metadata = {
                "frame_id": frame_id,
                "buffer_id": frame_identifiers["buffer_id"],
                "image_index": frame_identifiers["image_index"],
                "camera_timestamp": self._safe_image_call(image, "GetTimestamp"),
                "received_at": received_at.isoformat(timespec="microseconds"),
                "width": self._safe_image_call(image, "GetWidth"),
                "height": self._safe_image_call(image, "GetHeight"),
                "pixel_format": self._safe_image_call(image, "GetPixelFormat"),
                "received_frames_count": self._received_frames_count,
                "saved_frames_count": self._saved_frames_count,
                "receive_gap_ms": round(gap_ms, 3) if gap_ms is not None else None,
            }
            self._log(
                f"hardware trigger image received "
                f"frame_id={frame_id} "
                f"buffer_id={frame_identifiers['buffer_id']} "
                f"image_index={frame_identifiers['image_index']} "
                f"| received={self._received_frames_count} "
                f"saved={self._saved_frames_count} "
                f"save_errors={self._save_errors_count} "
                f"gap_ms={round(gap_ms, 3) if gap_ms is not None else 'n/a'} "
                f"queue={self._save_queue.qsize()}"
            )

            copy_started = time.monotonic()
            snapshot = CameraSnapshot(image=image.Copy(), metadata=metadata)
            copy_ms = (time.monotonic() - copy_started) * 1000.0
            snapshot.metadata["copy_ms"] = round(copy_ms, 3)
            if copy_ms >= 20.0:
                self._log(
                    f"image copy slow "
                    f"frame_id={frame_id} "
                    f"| copy_ms={round(copy_ms, 3)} "
                    f"received={self._received_frames_count} "
                    f"saved={self._saved_frames_count} "
                    f"queue={self._save_queue.qsize()}"
                )
            while not self._stop_event.is_set():
                try:
                    put_started = time.monotonic()
                    self._save_queue.put(snapshot, timeout=0.5)
                    put_ms = (time.monotonic() - put_started) * 1000.0
                    if put_ms >= 20.0:
                        self._log(
                            f"save queue put slow "
                            f"frame_id={frame_id} "
                            f"| put_ms={round(put_ms, 3)} "
                            f"received={self._received_frames_count} "
                            f"saved={self._saved_frames_count} "
                            f"queue={self._save_queue.qsize()}"
                        )
                    self._queue_full_logged = False
                    break
                except queue.Full:
                    if not self._queue_full_logged:
                        self._log(
                            "save queue full - waiting for writer thread "
                            f"| received={self._received_frames_count} "
                            f"saved={self._saved_frames_count} "
                            f"save_errors={self._save_errors_count} "
                            f"queue={self._save_queue.qsize()}"
                        )
                        self._queue_full_logged = True

    def _writer_loop(self):
        while not self._writer_stop_event.is_set() or not self._save_queue.empty():
            try:
                snapshot = self._save_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                file_path = self._build_output_path()
                save_started = time.monotonic()
                snapshot.image.Save(str(file_path))
                save_ms = (time.monotonic() - save_started) * 1000.0
                self._saved_frames_count += 1
                snapshot.metadata["file_path"] = str(file_path)
                snapshot.metadata["saved_frames_count"] = self._saved_frames_count
                snapshot.metadata["save_ms"] = round(save_ms, 3)
                self._log(
                    f"image saved: {file_path} "
                    f"| received={self._received_frames_count} "
                    f"saved={self._saved_frames_count} "
                    f"save_errors={self._save_errors_count} "
                    f"save_ms={round(save_ms, 3)} "
                    f"queue={self._save_queue.qsize()}"
                )
                if self.on_image_saved is not None:
                    self.on_image_saved(str(file_path), snapshot.metadata)
            except Exception as exc:
                self._save_errors_count += 1
                self._log(
                    f"save error: {exc} "
                    f"| received={self._received_frames_count} "
                    f"saved={self._saved_frames_count} "
                    f"save_errors={self._save_errors_count} "
                    f"queue={self._save_queue.qsize()}"
                )
            finally:
                self._save_queue.task_done()

    def _build_output_path(self) -> Path:
        directory = Path(self.settings.output_directory)
        directory.mkdir(parents=True, exist_ok=True)

        with self._sequence_lock:
            self._sequence += 1
            sequence = self._sequence

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return directory / f"{timestamp}_{sequence:06d}.bmp"

    def _disconnect_camera(self):
        if self._camera is None:
            return

        try:
            if hasattr(self._camera, "StopStreaming"):
                self._camera.StopStreaming()
        except Exception:
            pass

        try:
            self._camera.Disconnect()
        except Exception:
            pass
        finally:
            self._camera = None

    def _feature_get(self, feature_name: str):
        if self._camera is None:
            return None

        try:
            feature = getattr(self._camera.f, feature_name)
            return feature.Get()
        except Exception:
            return None

    def _feature_set(self, feature_name: str, value):
        if self._camera is None:
            return

        try:
            feature = getattr(self._camera.f, feature_name)
            feature.Set(value)
        except Exception as exc:
            self._log(f"Cannot set {feature_name} to {value}: {exc}")

    def _feature_set_numeric_max(self, feature_name: str):
        if self._camera is None:
            return False

        try:
            feature = getattr(self._camera.f, feature_name)
            max_value = feature.GetMax()
            feature.Set(max_value)
            return True
        except Exception:
            return False

    def _feature_set_numeric_fraction(self, feature_name: str, fraction: float):
        if self._camera is None:
            return False

        try:
            feature = getattr(self._camera.f, feature_name)
            min_value = feature.GetMin()
            max_value = feature.GetMax()
            target = min_value + (max_value - min_value) * max(0.0, min(1.0, fraction))
            if isinstance(min_value, int) and isinstance(max_value, int):
                target = int(round(target))
            feature.Set(target)
            return True
        except Exception:
            return False

    def _feature_set_numeric_clamped(self, feature_name: str, preferred_value):
        if self._camera is None:
            return False

        try:
            feature = getattr(self._camera.f, feature_name)
            min_value = feature.GetMin()
            max_value = feature.GetMax()
            target = max(min_value, min(max_value, preferred_value))
            if isinstance(min_value, int) and isinstance(max_value, int):
                target = int(round(target))
            feature.Set(target)
            return True
        except Exception:
            return False

    def _enum_constant(self, name: str):
        return getattr(self._neoapi, name, None) if self._neoapi is not None else None

    def _format_feature_value(self, feature_name: str, value):
        prefix_map = {
            "TriggerSelector": "TriggerSelector_",
            "TriggerMode": "TriggerMode_",
            "TriggerSource": "TriggerSource_",
            "TriggerActivation": "TriggerActivation_",
            "ExposureAuto": "ExposureAuto_",
            "GainAuto": "GainAuto_",
        }
        prefix = prefix_map.get(feature_name)
        if prefix is None or self._neoapi is None:
            return str(value)

        for attr_name in dir(self._neoapi):
            if not attr_name.startswith(prefix):
                continue
            try:
                if getattr(self._neoapi, attr_name) == value:
                    return attr_name.replace(prefix, "")
            except Exception:
                continue

        return str(value)

    def _try_set_first_available(self, candidates):
        for feature_name, value in candidates:
            if self._feature_get(feature_name) is None and not self._has_feature(feature_name):
                continue
            try:
                feature = getattr(self._camera.f, feature_name)
                feature.Set(value)
                return True
            except Exception:
                continue
        return False

    def _has_feature(self, feature_name: str):
        if self._camera is None:
            return False
        try:
            getattr(self._camera.f, feature_name)
            return True
        except Exception:
            return False

    def _extract_frame_identifiers(self, image):
        return {
            "frame_id": self._normalize_frame_identifier(
                self._safe_image_call(image, "GetFrameID")
            ),
            "buffer_id": self._normalize_frame_identifier(
                self._safe_image_call(image, "GetBufferID")
            ),
            "image_index": self._normalize_frame_identifier(
                self._safe_image_call(image, "GetImageIndex")
            ),
        }

    def _normalize_frame_identifier(self, value):
        return value if value not in (None, "", 0) else None

    def _safe_image_call(self, image, method_name: str):
        method = getattr(image, method_name, None)
        if method is None:
            return None
        try:
            return method()
        except Exception:
            return None

    def _safe_call(self, func, default=None):
        try:
            return func()
        except Exception:
            return default

    def _is_timeout_exception(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "timeout" in message or "timed out" in message

    def _log_timeout(self):
        now = time.monotonic()
        if now - self._last_timeout_log_at >= 10:
            self._last_timeout_log_at = now
            self._log("camera timeout - no trigger")

    def _set_state(self, state: str):
        self._state = state
        if self.on_status_changed is not None:
            self.on_status_changed(state)

    def _log(self, message: str):
        LOGGER.info(message)
        if self.on_log is not None:
            self.on_log(message)
