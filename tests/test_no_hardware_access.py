"""Regression tests for the no-hardware guard in tests/conftest.py.

The physical Eilik sits on Jeff's desk. A unit test that opens
`/dev/ttyACM0` can move it, and the resulting servo write is logged into the
same file the running bridge uses, so it is indistinguishable from a real
movement unless you check for the device's reply.

Guard contract:
  * opening a real device path raises
  * the service module never auto-detects the real device
  * the test suite logs to its own file, never the device log
  * `EILIK_TEST_LIVE=1` alone is refused; it needs `EILIK_ALLOW_LIVE=1` too
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import serial

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.expects_real_device_attempt
def test_opening_a_real_device_path_is_blocked() -> None:
    with pytest.raises(AssertionError) as excinfo:
        serial.Serial("/dev/ttyACM0", 125000)
    assert "real device" in str(excinfo.value)


def test_a_fake_port_still_opens() -> None:
    """The guard must not break the tests that use a fake device path."""
    try:
        port = serial.Serial("/dev/eilik-test-device", 125000)
    except Exception as exc:
        # pyserial raises for a non-existent path; that is fine, the point
        # is that the guard let it through instead of blocking it.
        assert "real device" not in str(exc)
        return
    port.close()


def test_service_does_not_point_at_the_real_device() -> None:
    from eilik import service

    port = service.SERVICE_PORT
    assert port != "/dev/ttyACM0", "the service must not target the real device in tests"
    if port is not None:
        assert not port.startswith("/dev/ttyACM"), port


def test_tests_log_to_their_own_file_not_the_device_log() -> None:
    """The device log is the record of what moved the robot."""
    from eilik import controller

    assert controller.DEFAULT_LOG_PATH != Path("logs/test-eilik.log")
    assert os.getenv("EILIK_LOG_PATH") == "logs/test-eilik.log"


def test_live_tests_require_a_second_explicit_opt_in() -> None:
    """`EILIK_TEST_LIVE=1` must not be enough to move the robot."""
    env = dict(os.environ)
    env["EILIK_TEST_LIVE"] = "1"
    env.pop("EILIK_ALLOW_LIVE", None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/test_actions.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, combined
    assert "EILIK_ALLOW_LIVE" in combined, combined
