"""High-level serial controller for Eilik."""

from __future__ import annotations

import glob
import threading
import time
from pathlib import Path
from typing import Iterable

from .logger import DEFAULT_LOG_PATH, hex_bytes, setup_logger
from .motions import MOTIONS
from .protocol import (
    BAUD_RATE,
    HB1,
    REST_POSITION,
    SERIAL_TIMEOUT_SECONDS,
    ServoCommand,
    build_servo_frame,
    extract_session_token,
)

EILIK_USB_VID = 0x28E9
EILIK_USB_PID = 0x018A


class EilikConnectionError(RuntimeError):
    """Raised when the Eilik serial connection cannot be established."""


class EilikController:
    """Reusable SDK controller for an Eilik robot over USB CDC ACM serial."""

    def __init__(
        self,
        port: str | None = None,
        baud_rate: int = BAUD_RATE,
        timeout: float = SERIAL_TIMEOUT_SECONDS,
        log_path: str | Path = DEFAULT_LOG_PATH,
        reconnect_attempts: int = 3,
        keepalive_interval: float = 2.0,
    ) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.reconnect_attempts = reconnect_attempts
        self.keepalive_interval = keepalive_interval
        self.logger = setup_logger(log_path)

        self._serial = None
        self._session_token: bytes | None = None
        self._keepalive_stop = threading.Event()
        self._keepalive_thread: threading.Thread | None = None
        self._lock = threading.RLock()

    @property
    def connected(self) -> bool:
        return bool(self._serial and getattr(self._serial, "is_open", False) and self._session_token)

    @property
    def session_token(self) -> bytes | None:
        return self._session_token

    @staticmethod
    def detect_port(preferred: str = "/dev/ttyACM0") -> str:
        """Detect Eilik's Linux serial device, preferring /dev/ttyACM0."""

        if Path(preferred).exists():
            return preferred

        try:
            from serial.tools import list_ports
        except ImportError as exc:
            raise EilikConnectionError("pyserial is required for serial port discovery") from exc

        ports = list(list_ports.comports())
        for port in ports:
            if port.vid == EILIK_USB_VID and port.pid == EILIK_USB_PID:
                return port.device

        description_markers = ("gd32", "gdmicroelectronics", "eilik", "cdc acm")
        for port in ports:
            haystack = " ".join(
                str(value or "").lower()
                for value in (port.description, port.manufacturer, port.product, port.hwid)
            )
            if any(marker in haystack for marker in description_markers):
                return port.device

        acm_ports = sorted(glob.glob("/dev/ttyACM*"))
        if acm_ports:
            return acm_ports[0]

        raise EilikConnectionError("Could not find Eilik serial device; expected /dev/ttyACM0 or VID:PID 28e9:018a")

    def connect(self) -> None:
        """Open the serial device, perform handshake, and start keep-alive."""

        with self._lock:
            self.disconnect()
            port = self.port or self.detect_port()
            self.port = port
            self.logger.info("CONNECT port=%s baud=%s timeout=%s", port, self.baud_rate, self.timeout)

            try:
                import serial
            except ImportError as exc:
                raise EilikConnectionError("pyserial is required; install with `pip install pyserial`") from exc

            try:
                ser = serial.Serial(port, self.baud_rate, timeout=self.timeout)
                ser.rts = False
                ser.dtr = True
                time.sleep(1.0)
                ser.reset_input_buffer()
            except Exception as exc:
                raise EilikConnectionError(f"Could not open Eilik serial port {port}: {exc}") from exc

            self._serial = ser
            self._session_token = self._handshake()
            self._start_keepalive()
            self.logger.info("CONNECTED token=%s", hex_bytes(self._session_token))

    def disconnect(self) -> None:
        """Stop keep-alive and close the serial device."""

        with self._lock:
            self._keepalive_stop.set()
            if self._keepalive_thread and self._keepalive_thread.is_alive():
                self._keepalive_thread.join(timeout=1.0)
            self._keepalive_thread = None
            self._keepalive_stop.clear()

            if self._serial is not None:
                try:
                    self._serial.close()
                finally:
                    self.logger.info("DISCONNECT")
            self._serial = None
            self._session_token = None

    def move_motor(self, motor_id: int, position: int) -> None:
        self._send_servo(motor_id, position)

    def reset_pose(self) -> None:
        self._run_motion("reset_pose")

    def wave(self) -> None:
        self._run_motion("wave")

    def nod(self) -> None:
        self._run_motion("nod")

    def shake_head(self) -> None:
        self._run_motion("shake_head")

    def look_left(self) -> None:
        self._run_motion("look_left")

    def look_right(self) -> None:
        self._run_motion("look_right")

    def left_arm_up(self) -> None:
        self._run_motion("left_arm_up")

    def left_arm_down(self) -> None:
        self._run_motion("left_arm_down")

    def right_arm_up(self) -> None:
        self._run_motion("right_arm_up")

    def right_arm_down(self) -> None:
        self._run_motion("right_arm_down")

    def monitor(self, output_path: str | Path = "logs/eilik-monitor.log") -> None:
        """Continuously print and save incoming serial chunks as hex frames."""

        self._ensure_connected()
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        assert self._serial is not None

        self.logger.info("MONITOR_START file=%s", out)
        with out.open("a", encoding="utf-8") as fh:
            while True:
                try:
                    waiting = self._serial.in_waiting
                    data = self._serial.read(waiting or 1)
                except Exception as exc:
                    self.logger.exception("RX_ERROR monitor %s", exc)
                    self._reconnect()
                    continue
                if not data:
                    continue
                line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {hex_bytes(data)}"
                print(line, flush=True)
                fh.write(line + "\n")
                fh.flush()
                self.logger.info("RX %s", hex_bytes(data))

    def _run_motion(self, name: str) -> None:
        self._send_commands(MOTIONS[name])

    def _send_commands(self, commands: Iterable[ServoCommand]) -> None:
        for command in commands:
            self._send_servo(command.motor_id, command.position)
            if command.delay_after > 0:
                time.sleep(command.delay_after)

    def _handshake(self) -> bytes:
        assert self._serial is not None
        self._write_raw(HB1, "TX_HANDSHAKE")
        time.sleep(0.3)
        reply = self._read_available()
        if not reply:
            raise EilikConnectionError("No handshake reply from Eilik")
        try:
            return extract_session_token(reply)
        except ValueError as exc:
            raise EilikConnectionError(f"Could not parse Eilik session token from {hex_bytes(reply)}") from exc

    def _send_servo(self, motor_id: int, position: int) -> None:
        self._ensure_connected()
        assert self._session_token is not None
        frame = build_servo_frame(self._session_token, motor_id, position)
        for attempt in range(self.reconnect_attempts + 1):
            try:
                with self._lock:
                    self._write_raw(frame, f"TX_SERVO motor={motor_id} position={position}")
                return
            except Exception:
                self.logger.exception("TX_ERROR motor=%s position=%s attempt=%s", motor_id, position, attempt + 1)
                if attempt >= self.reconnect_attempts:
                    raise
                self._reconnect()

    def _write_raw(self, data: bytes, label: str = "TX") -> None:
        assert self._serial is not None
        self.logger.info("%s %s", label, hex_bytes(data))
        self._serial.write(data)

    def _read_available(self) -> bytes:
        assert self._serial is not None
        waiting = self._serial.in_waiting
        data = self._serial.read(waiting or 1)
        if data:
            self.logger.info("RX %s", hex_bytes(data))
        return data

    def _ensure_connected(self) -> None:
        if not self.connected:
            self.connect()

    def _reconnect(self) -> None:
        self.logger.warning("RECONNECT requested")
        time.sleep(0.5)
        self.connect()
        self.reset_pose()

    def _start_keepalive(self) -> None:
        self._keepalive_thread = threading.Thread(target=self._keepalive_loop, name="eilik-keepalive", daemon=True)
        self._keepalive_thread.start()

    def _keepalive_loop(self) -> None:
        while not self._keepalive_stop.wait(self.keepalive_interval):
            try:
                with self._lock:
                    if self._serial is not None and getattr(self._serial, "is_open", False):
                        self._write_raw(HB1, "TX_KEEPALIVE")
            except Exception:
                self.logger.exception("KEEPALIVE_ERROR")
