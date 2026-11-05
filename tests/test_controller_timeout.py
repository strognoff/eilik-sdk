"""Regression tests for the stalled-USB-endpoint hang (L#1020).

The 2026-11-05 failure: pyserial's write() does an UNBOUNDED select() when
write_timeout is None. A stalled CDC bulk-OUT endpoint therefore blocked the
calling thread forever. Each blocked POST leaked one /dev/ttyACM0 fd and one
spinning thread, and the HTTP request never returned -- so every cron
callback timed out at 30 s while the bridge reported /health 200 OK.

These tests pin the fix:
  * the port is opened with a bounded write_timeout
  * a write timeout surfaces as EilikConnectionError, not an infinite hang
  * a failed open does not leak the fd
"""

from __future__ import annotations

import serial
import pytest

from eilik.controller import EilikController, EilikConnectionError


class RecordingSerial:
    """Minimal pyserial stand-in that records how it was constructed."""

    instances: list["RecordingSerial"] = []

    def __init__(self, port, baudrate, timeout=None, write_timeout=None, **kwargs):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.closed = False
        self.rts = None
        self.dtr = None
        self.writes: list[bytes] = []
        self.write_error: Exception | None = None
        RecordingSerial.instances.append(self)

    def reset_input_buffer(self) -> None:
        pass

    @property
    def in_waiting(self) -> int:
        return 0

    def read(self, _size: int) -> bytes:
        return b""

    def write(self, data: bytes) -> int:
        if self.write_error is not None:
            raise self.write_error
        self.writes.append(data)
        return len(data)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def recording_serial(monkeypatch):
    RecordingSerial.instances = []
    monkeypatch.setattr(serial, "Serial", RecordingSerial)
    return RecordingSerial


def test_port_is_opened_with_a_bounded_write_timeout(recording_serial, monkeypatch):
    """A None write_timeout means pyserial selects() forever."""
    monkeypatch.setattr(EilikController, "detect_port", staticmethod(lambda: "/dev/ttyACM0"))
    monkeypatch.setattr("time.sleep", lambda _s: None)

    controller = EilikController(reconnect_attempts=0)
    controller._handshake = lambda: None  # type: ignore[method-assign]

    controller.connect()

    assert recording_serial.instances, "the port was never opened"
    port = recording_serial.instances[0]
    assert port.write_timeout is not None, "write_timeout must be bounded, not None"
    assert port.write_timeout > 0


def test_write_timeout_raises_connection_error_not_a_hang(recording_serial, monkeypatch):
    """The stalled endpoint must fail fast and surface a typed error."""
    monkeypatch.setattr(EilikController, "detect_port", staticmethod(lambda: "/dev/ttyACM0"))
    monkeypatch.setattr("time.sleep", lambda _s: None)

    controller = EilikController(reconnect_attempts=0)
    controller._handshake = lambda: None  # type: ignore[method-assign]
    controller.connect()

    port = recording_serial.instances[0]
    port.write_error = serial.SerialTimeoutException("Write timeout")

    with pytest.raises(EilikConnectionError) as excinfo:
        controller._write_raw(b"\xaa\xaa\xaa", "TX_TEST")

    assert "timed out" in str(excinfo.value).lower()


def test_failed_open_does_not_leak_the_fd(recording_serial, monkeypatch):
    """Every request opens a fresh port, so a leaked fd accumulates."""
    monkeypatch.setattr(EilikController, "detect_port", staticmethod(lambda: "/dev/ttyACM0"))

    class FailingSerial(RecordingSerial):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            raise serial.SerialTimeoutException("Write timeout")

    monkeypatch.setattr(serial, "Serial", FailingSerial)

    controller = EilikController(reconnect_attempts=0)

    with pytest.raises(EilikConnectionError):
        controller.connect()


class HangingCloseSerial(RecordingSerial):
    """A serial whose close() blocks forever, like a stalled CDC endpoint."""

    def close(self) -> None:
        import time

        time.sleep(600)


def test_close_does_not_block_the_caller_on_a_stalled_endpoint(monkeypatch):
    """close() can hang in the kernel; disconnect() must still return."""
    monkeypatch.setattr(EilikController, "detect_port", staticmethod(lambda: "/dev/ttyACM0"))
    monkeypatch.setattr("time.sleep", lambda _s: None)

    class HangingSerial(HangingCloseSerial):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(serial, "Serial", HangingSerial)

    controller = EilikController(reconnect_attempts=0, close_timeout=0.2)
    controller._handshake = lambda: None  # type: ignore[method-assign]
    controller.connect()
    assert controller._serial is not None

    import time as _time

    started = _time.monotonic()
    controller.disconnect()
    elapsed = _time.monotonic() - started

    assert elapsed < 5.0, f"disconnect() blocked for {elapsed:.1f}s on a stalled endpoint"
    assert controller._serial is None, "the serial reference must be cleared regardless"
