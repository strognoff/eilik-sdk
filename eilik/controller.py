"""High-level serial controller for Eilik."""

from __future__ import annotations

import glob
import os
import threading
import time
from pathlib import Path
from typing import Iterable, List, Optional

from .logger import DEFAULT_LOG_PATH, hex_bytes, setup_logger
from .motions import MOTIONS
from .pack import (
    FrameBuffer as _FrameBuffer,
    read_display as _read_display,
    read_running_number as _read_running_number,
    read_servo_angles as _read_servo_angles,
    write_display as _write_display,
    write_running_number as _write_running_number,
    write_servo as _write_servo_packet,
)
from .protocol import (
    BAUD_RATE,
    HB1,
    OFFICIAL_STATUS_REQUEST,
    REST_POSITION,
    SERIAL_TIMEOUT_SECONDS,
    ServoCommand,
    build_servo_frame,
    extract_session_token,
    has_command_reply,
)

EILIK_USB_VID = 0x28E9
EILIK_USB_PID = 0x018A

# Running number that puts the firmware in "user-display mode" — must be set
# before every cmd=0xA4 write or the firmware's idle animation will overwrite
# the user's framebuffer within ~50ms. Empirically determined: index 100.
USER_DISPLAY_RUNNING_NUMBER = 100

# Running number that RELEASES the firmware's user-display lock, allowing the
# firmware's idle animation loop to take over. Set after auto_idle pushes the
# firmware idle face. Empirically: index 0.
RELEASE_DISPLAY_RUNNING_NUMBER = 0


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
        self._protocol_variant: str | None = None
        self._keepalive_stop = threading.Event()
        self._keepalive_thread: threading.Thread | None = None
        self._lock = threading.RLock()

    @property
    def connected(self) -> bool:
        return bool(self._serial and getattr(self._serial, "is_open", False) and self._protocol_variant)

    @property
    def session_token(self) -> bytes | None:
        return self._session_token

    @property
    def protocol_variant(self) -> str | None:
        return self._protocol_variant

    @staticmethod
    def detect_port(preferred: str = "/dev/ttyACM0") -> str:
        """Detect Eilik's Linux serial device.

        Order of preference:
        1. `preferred` if it exists (default `/dev/ttyACM0`)
        2. any `/dev/ttyACM*` whose underlying USB device matches VID:PID `28e9:018a`
        3. any `/dev/ttyACM*` (sorted, since ACM0 may be busy with another device)
        """

        if Path(preferred).exists():
            return preferred

        # Prefer VID:PID match across all /dev/ttyACM* nodes
        acm_ports = sorted(glob.glob("/dev/ttyACM*"))
        for port in acm_ports:
            try:
                # Walk /sys/class/tty/<name>/device to find the USB idVendor
                sys_path = Path("/sys/class/tty") / Path(port).name / "device"
                # resolve symlinks
                while sys_path.is_symlink():
                    sys_path = Path(os.readlink(sys_path))
                    if not sys_path.is_absolute():
                        sys_path = sys_path.resolve()
                id_vendor = (sys_path / "idVendor").read_text().strip()
                id_product = (sys_path / "idProduct").read_text().strip()
                if (
                    int(id_vendor, 16) == EILIK_USB_VID
                    and int(id_product, 16) == EILIK_USB_PID
                ):
                    return port
            except (OSError, ValueError):
                continue

        if acm_ports:
            return acm_ports[0]

        raise EilikConnectionError(
            "Could not find Eilik serial device; expected /dev/ttyACM0 or VID:PID 28e9:018a"
        )

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
            self._handshake()
            if self._session_token:
                self._start_keepalive()
            self.logger.info(
                "CONNECTED protocol=%s token=%s",
                self._protocol_variant,
                hex_bytes(self._session_token) if self._session_token else "none",
            )

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
            self._protocol_variant = None

    def move_motor(self, motor_id: int, position: int) -> None:
        """Move a single servo using the canonical pack-format `cmd=0xA2`.

        Works without a session token because it uses `format_data()` from
        the official `PackAnalyData` wrapper (decoded from EnergizeLab.exe).
        `position` is a 16-bit value (typical range 0..3000).
        """
        self._ensure_connected()
        assert self._serial is not None
        frame = _write_servo_packet([(motor_id, position)])
        with self._lock:
            self._write_raw(frame, f"TX_SERVO_DIRECT motor={motor_id} pos={position}")
            time.sleep(0.1)
            # drain any ACK
            buf = b''
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                n = self._serial.in_waiting
                if n:
                    buf += self._serial.read(n)
                else:
                    time.sleep(0.02)
        if buf:
            self.logger.info("RX_SERVO_DIRECT %s", hex_bytes(buf))

    def read_servo_angles(self) -> List[int]:
        """Send `cmd=0xA1` and decode the 4 servo angles (positions 0..3000)."""
        return self._send_cmd_and_parse(_read_servo_angles(), 0xA1, 4, "read_servo_angles")

    def read_running_number(self) -> int:
        """Send `cmd=0xA5` and decode the running animation index."""
        raw = self._send_cmd_and_parse(_read_running_number(), 0xA5, 1, "read_running_number")
        return raw[0] if raw else 0

    def write_running_number(self, index: int) -> None:
        """Send `cmd=0xA6` with a 1-byte animation index."""
        self._send_simple(_write_running_number(index), f"TX_RUNNING idx={index}")

    def read_display(self) -> Optional[bytes]:
        """Send `cmd=0xA3` and return the 1024-byte framebuffer image.

        Page-mode SSD1306-style: 128 columns × 64 rows = 1024 bytes.
        Return None if the robot did not reply within ~1 second.
        """
        self._ensure_connected()
        assert self._serial is not None
        with self._lock:
            self._serial.reset_input_buffer()
            self._write_raw(_read_display(), "TX_READ_DISPLAY")
            time.sleep(0.3)
            buf = b""
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                n = self._serial.in_waiting
                if n:
                    buf += self._serial.read(n)
                else:
                    time.sleep(0.02)
        self.logger.info("RX_READ_DISPLAY %d bytes", len(buf))
        frames = _FrameBuffer().feed(buf)
        if not frames:
            return None
        f = frames[0]
        # frame layout: magic(3) | length u16 LE(2) | cmd echo(1) | status(1) |
        #               1024 image bytes | checksum(1)
        if len(f) < 1032:
            self.logger.warning("RX_READ_DISPLAY short frame (%d bytes)", len(f))
            return None
        return bytes(f[7:1031])

    def write_display(self, image_1024b: bytes) -> bool:
        """Send `cmd=0xA4` with a 1024-byte framebuffer.

        Returns True if the firmware ACKed (status byte 0x01).

        **Important**: before every display write, this method also sends
        `cmd=0xA6` with `running_number=USER_DISPLAY_RUNNING_NUMBER` to put the
        firmware in "user-display mode". Without this, the firmware's idle
        animation overwrites the custom framebuffer within ~50ms and the
        user's display content is lost.
        """
        if len(image_1024b) != 1024:
            raise ValueError(f"display payload must be 1024 bytes (got {len(image_1024b)})")
        self._ensure_connected()
        assert self._serial is not None
        with self._lock:
            self._serial.reset_input_buffer()
            # Lock the firmware into user-display mode so it doesn't override us
            self._write_raw(_write_running_number(USER_DISPLAY_RUNNING_NUMBER),
                            f"TX_WRITE_RUNNING idx={USER_DISPLAY_RUNNING_NUMBER}")
            time.sleep(0.05)
            self._write_raw(_write_display(image_1024b), "TX_WRITE_DISPLAY 1024B")
            time.sleep(0.3)
            buf = b""
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                n = self._serial.in_waiting
                if n:
                    buf += self._serial.read(n)
                else:
                    time.sleep(0.02)
        self.logger.info("RX_WRITE_DISPLAY %s", hex_bytes(buf))
        frames = _FrameBuffer().feed(buf)
        if not frames:
            return False
        # frame layout: magic(3) | length u16 LE(2) | cmd echo(1) | status(1) | checksum(1)
        f = frames[0]
        if len(f) < 7:
            return False
        status = f[6]
        self.logger.info("WRITE_DISPLAY status=0x%02x", status)
        return status == 0x01

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

    def display_image(self, png_path: str | Path, threshold: int = 128,
                      invert: bool = False, hold_seconds: float = 0.0,
                      auto_idle: bool = True, auto_rotate: bool = True) -> bool:
        """Convert a PNG (any size; auto-resized to 128x64) to a 1024-byte
        framebuffer and push it via `cmd=0xA4`.

        Use `invert=True` if the source PNG is white-on-black (Eilik's OLED
        is black-on-white, so most PNGs need inversion).

        With `hold_seconds=N`, the face stays for N seconds before reverting.
        With `auto_idle=True` (default), the firmware's default idle face is
        restored after the hold. This puts the robot back to its true idle
        state instead of a blank/cleared screen, so the firmware's idle
        animation loop resumes naturally.

        With `auto_rotate=True` (default), the framebuffer is rotated 180°
        before sending because Eilik's OLED panel (or firmware) renders
        framebuffers rotated 180° from what the SDK reads back. If you set
        this False, the image will appear upside-down on the physical screen
        (or right-side-up if you pre-rotated it yourself).

        Both the user face and the idle-face push use `cmd=0xA6` running_number
        first to lock the firmware in user-display mode (otherwise the idle
        animation overwrites the framebuffer within ~50ms).
        """
        ok = self._display_image_raw(png_path, threshold=threshold, invert=invert,
                                     auto_rotate=auto_rotate)
        if ok and (hold_seconds > 0 or auto_idle):
            try:
                if hold_seconds > 0:
                    time.sleep(hold_seconds)
                if auto_idle:
                    idle_path = Path(__file__).resolve().parent.parent / "captures" / "eilik-display-cmd-A3.png"
                    if idle_path.exists():
                        self._display_image_raw(idle_path, threshold=128, invert=False,
                                                auto_rotate=auto_rotate)
                    # After restoring the firmware idle framebuffer, release
                    # the user-display lock so the firmware's idle animation
                    # can resume (otherwise it stays stuck on the captured frame).
                    with self._lock:
                        if self._serial is not None:
                            self._write_raw(
                                _write_running_number(RELEASE_DISPLAY_RUNNING_NUMBER),
                                f"TX_WRITE_RUNNING idx={RELEASE_DISPLAY_RUNNING_NUMBER} (release)"
                            )
            except Exception as exc:
                self.logger.warning("AUTO_IDLE_FAILED %s", exc)
        return ok

    def _display_image_raw(self, png_path: str | Path, threshold: int = 128,
                           invert: bool = False, auto_rotate: bool = True) -> bool:
        from pathlib import Path as _Path
        png_path = _Path(png_path)
        try:
            from tools.png_to_framebuffer import (
                decode_png, to_grayscale, resize_nearest, to_framebuffer,
                rotate_180,
            )
        except ImportError:
            import sys as _sys, os as _os
            sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
            from tools.png_to_framebuffer import (
                decode_png, to_grayscale, resize_nearest, to_framebuffer,
                rotate_180,
            )
        width, height, pixels = decode_png(png_path)
        actual = len(pixels)
        expected = width * height
        if actual == expected:
            chans = 1
        elif actual == expected * 3:
            chans = 3
        elif actual == expected * 4:
            chans = 4
        else:
            raise ValueError(f"unsupported PNG pixel layout: {actual} bytes for {width}x{height}")
        gray = to_grayscale(pixels, width, height, chans)
        if invert:
            gray = [255 - g for g in gray]
        gray = resize_nearest(gray, width, height, 128, 64)
        fb = to_framebuffer(gray, threshold=threshold)
        # Eilik's OLED panel (or firmware) renders the framebuffer rotated 180°
        # from what the SDK reads back. Rotate before sending so the user's
        # image appears right-side-up on the physical display.
        if auto_rotate:
            fb = rotate_180(fb)
        return self.write_display(fb)

    def _safe_auto_reset(self) -> None:
        """Try to return the robot to rest pose without raising on failure."""
        try:
            self._run_motion("reset_pose")
        except Exception as exc:
            self.logger.warning("AUTO_RESET_FAILED %s", exc)

    def action(self, name: str, hold_seconds: float | None = None,
               async_motion: bool = True, auto_idle: bool = True) -> bool:
        """Run a high-level action from `eilik/actions.py`.

        Each action combines an optional face flash + optional motion + a hold
        time. Use `async_motion=True` (default) to run the motion in parallel
        with the face flash so the gestures actually overlap the face.

        `hold_seconds=None` falls back to the action's default.

        Returns True if the face was successfully flashed (or skipped cleanly).
        """
        from .actions import get_action, resolve_face
        spec = get_action(name)
        motion_name = spec.get("motion")
        face_tag = spec.get("face")
        action_hold = spec.get("hold", 0)
        if hold_seconds is None:
            hold_seconds = action_hold

        ok = True
        # Show face first (lock firmware in user-display mode)
        if face_tag:
            face_path = resolve_face(face_tag)
            try:
                ok = self.display_image(face_path, auto_idle=False)
            except Exception as exc:
                self.logger.warning("ACTION_FACE_FAILED %s tag=%s %s", name, face_tag, exc)
                ok = False

        # Run motion (parallel if face shown)
        if motion_name:
            try:
                if async_motion and face_tag:
                    import threading
                    t = threading.Thread(target=self._safe_run_motion, args=(motion_name,),
                                         daemon=True)
                    t.start()
                else:
                    self._run_motion(motion_name)
            except Exception as exc:
                self.logger.warning("ACTION_MOTION_FAILED %s motion=%s %s", name, motion_name, exc)

        # Hold face visible for the action duration
        if hold_seconds and hold_seconds > 0:
            time.sleep(hold_seconds)

        # Restore firmware idle (release user-display lock)
        if auto_idle:
            idle_path = Path(__file__).resolve().parent.parent / "captures" / "eilik-display-cmd-A3.png"
            if idle_path.exists() and ok:
                try:
                    self._display_image_raw(idle_path, threshold=128, invert=False, auto_rotate=True)
                    with self._lock:
                        if self._serial is not None:
                            self._write_raw(
                                _write_running_number(RELEASE_DISPLAY_RUNNING_NUMBER),
                                f"TX_WRITE_RUNNING idx={RELEASE_DISPLAY_RUNNING_NUMBER} (release)"
                            )
                except Exception as exc:
                    self.logger.warning("ACTION_AUTO_IDLE_FAILED %s", exc)

        return ok

    def _safe_run_motion(self, name: str) -> None:
        """Run a motion without raising."""
        try:
            self._run_motion(name)
        except Exception as exc:
            self.logger.warning("MOTION_FAILED %s %s", name, exc)

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

    def _handshake(self) -> None:
        assert self._serial is not None
        self._write_raw(HB1, "TX_HANDSHAKE")
        time.sleep(0.3)
        reply = self._read_available()
        if reply:
            try:
                self._session_token = extract_session_token(reply)
                self._protocol_variant = "legacy-token"
                return
            except ValueError:
                self.logger.info("LEGACY_HANDSHAKE_UNPARSED %s", hex_bytes(reply))

        self.logger.info("LEGACY_HANDSHAKE_NO_TOKEN trying captured official status handshake")
        self._serial.reset_input_buffer()
        self._write_raw(OFFICIAL_STATUS_REQUEST, "TX_OFFICIAL_STATUS")
        time.sleep(0.3)
        reply = self._read_available()
        if not reply:
            raise EilikConnectionError("No handshake reply from Eilik using legacy HB1 or official status request")
        if not has_command_reply(reply, 0x01):
            raise EilikConnectionError(f"Could not parse official Eilik status reply from {hex_bytes(reply)}")
        self._session_token = None
        self._protocol_variant = "official-status"

    def _send_servo(self, motor_id: int, position: int) -> None:
        self._ensure_connected()
        if not self._session_token:
            raise EilikConnectionError(
                "This robot answered the captured official status protocol, but no servo/motion "
                "command was present in the capture. Capture a RobotStudio/app movement to map motion commands."
            )
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

    def _send_simple(self, frame: bytes, label: str) -> None:
        """Send a packet and wait briefly for an ACK. No parsing."""
        self._ensure_connected()
        with self._lock:
            self._serial.reset_input_buffer() if self._serial else None
            self._write_raw(frame, label)
            time.sleep(0.3)
            buf = b""
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                n = self._serial.in_waiting if self._serial else 0
                if n:
                    buf += self._serial.read(n)
                else:
                    time.sleep(0.02)
        self.logger.info("RX_%s %s", label, hex_bytes(buf))

    def _send_cmd_and_parse(self, frame: bytes, expected_cmd: int,
                            payload_words: int, label: str) -> List[int]:
        """Send a read packet, parse the response, return payload words as ints.

        `payload_words` controls how many 16-bit little-endian values to extract
        AFTER the status byte (which is always body[0]).
        """
        self._ensure_connected()
        assert self._serial is not None
        with self._lock:
            self._serial.reset_input_buffer()
            self._write_raw(frame, f"TX_{label}")
            time.sleep(0.3)
            buf = b""
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                n = self._serial.in_waiting
                if n:
                    buf += self._serial.read(n)
                else:
                    time.sleep(0.02)
        self.logger.info("RX_%s %d bytes", label, len(buf))
        frames = _FrameBuffer().feed(buf)
        if not frames:
            return []
        f = frames[0]
        # frame layout: magic(3) | length u16 LE(2) | cmd echo(1) | status(1) | payload | checksum(1)
        if len(f) < 7:
            return []
        payload = f[7:-1]
        if payload_words == 1:
            return [payload[0]] if payload else []
        # decode `payload_words` u16 little-endian
        import struct as _struct
        out = []
        for i in range(payload_words):
            off = i * 2
            if off + 2 > len(payload):
                break
            out.append(_struct.unpack_from('<H', payload, off)[0])
        return out

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
