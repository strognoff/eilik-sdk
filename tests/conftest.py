"""Guard rails: the test suite must never actuate the physical Eilik.

The SDK's tests are unit tests. They use fake serial objects, but the log
file they shared with the running bridge made that hard to PROVE: a
`TX_SERVO_DIRECT motor=1 pos=500` line appeared in `logs/eilik.log` during
a pytest run, and it took a device reply (`RX_SERVO_DIRECT`) to tell that
the write went to a fake serial rather than the robot.

There is also a genuine landmine: `EILIK_TEST_LIVE=1` enables live tests
that connect to `/dev/ttyACM1` and physically move the robot.

Three protections live here:

1. The test suite writes to `logs/test-eilik.log`, never the device log.
   The device log is the only record of what actually moved the robot.
2. `EILIK_TEST_LIVE=1` now requires `EILIK_ALLOW_LIVE=1` as well. One key
   is too easy to set by accident; two keys means a human meant it.
3. An autouse fixture blocks any attempt to open a real serial device, so
   a future test cannot quietly start actuating the robot.

Set `EILIK_ALLOW_LIVE=1` (with `EILIK_TEST_LIVE=1`) to run the live tests
against real hardware.
"""

from __future__ import annotations

import os

import pytest
import serial

#: Prefixes of real serial devices. Opening any of these moves real hardware.
REAL_DEVICE_PREFIXES = ("/dev/ttyACM", "/dev/ttyUSB", "/dev/ttyAMA")

#: The device log records what actually moved the robot. Tests must not
#: write into it -- a test servo write there is indistinguishable from a
#: real movement unless you check for the device's reply.
os.environ.setdefault("EILIK_LOG_PATH", "logs/test-eilik.log")

#: Keep the service module from auto-detecting the real device on import.
os.environ.setdefault("EILIK_PORT", "/dev/eilik-test-device")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Refuse to run the live tests without an explicit second opt-in."""
    if os.environ.get("EILIK_TEST_LIVE") == "1" and os.environ.get("EILIK_ALLOW_LIVE") != "1":
        raise pytest.UsageError(
            "EILIK_TEST_LIVE=1 would move the physical Eilik. Re-run with "
            "EILIK_ALLOW_LIVE=1 to confirm you really mean it."
        )


@pytest.fixture(autouse=True)
def _block_real_hardware(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    """Fail loudly if a test tries to open the physical device."""
    if os.environ.get("EILIK_ALLOW_LIVE") == "1":
        yield
        return

    attempts: list[str] = []
    real_serial = serial.Serial

    class GuardSerial:
        """Stands in for `serial.Serial` and refuses real device paths."""

        def __init__(self, port=None, *args, **kwargs):
            if isinstance(port, str) and port.startswith(REAL_DEVICE_PREFIXES):
                attempts.append(port)
                raise AssertionError(
                    f"the test suite tried to open the real device {port}; "
                    "patch serial.Serial or use a fake port instead"
                )
            self._inner = real_serial(port, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def __enter__(self):
            self._inner.__enter__()
            return self

        def __exit__(self, *exc):
            return self._inner.__exit__(*exc)

        def close(self):
            return self._inner.close()

    monkeypatch.setattr(serial, "Serial", GuardSerial)
    yield
    # The controller swallows open-time exceptions and re-raises them as
    # EilikConnectionError, so the AssertionError above may not surface.
    # Assert here so the attempt is still reported.
    if request.node.get_closest_marker("expects_real_device_attempt"):
        return
    assert not attempts, (
        f"the test suite opened real device(s) {attempts}; "
        "the physical Eilik must never be actuated by the test suite"
    )
