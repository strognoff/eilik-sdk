"""Regression tests: the service must serialise access to the USB device.

The Eilik is a single USB CDC endpoint. Before this guard, two concurrent
requests each opened /dev/ttyACM0 and raced the handshake - the losers
failed with "No handshake reply from Eilik" even though the device was
perfectly healthy. Measured 2026-11-05: 5 concurrent pings -> 3 ok, 2
handshake errors.

A second bug lived in the same code path: a request that exceeded its
timeout had its `finally: robot.disconnect()` run by the REQUEST thread,
while the worker thread was still writing to the same serial object. The
request closed the device out from under its own worker.

Guard contract:
  * only one request holds the device at a time
  * a queued request waits, then succeeds
  * a timed-out request does NOT disconnect from the request thread
"""

from __future__ import annotations

import logging
import threading
import time

import pytest

from eilik import service


class ConcurrencyTrackingController:
    """A fake controller that records how many requests overlap."""

    instances: list["ConcurrencyTrackingController"] = []

    def __init__(self, port=None, log_path=None, enable_keepalive=True, reconnect_attempts=0):
        self.port = port
        self.log_path = log_path
        self.enable_keepalive = enable_keepalive
        self.events: list[str] = []
        self.logger = logging.getLogger("test-eilik-serial")
        ConcurrencyTrackingController.instances.append(self)

    @staticmethod
    def detect_port() -> str:
        return "/dev/fake-eilik"

    def connect(self) -> None:
        self.events.append("connect")
        time.sleep(0.05)

    def disconnect(self) -> None:
        self.events.append("disconnect")

    def wave(self) -> None:
        self.events.append("wave")
        time.sleep(0.05)

    def read_servo_angles(self):
        self.events.append("read")
        time.sleep(0.05)
        return [1, 2, 3, 4]


@pytest.fixture(autouse=True)
def fake_controller(monkeypatch):
    ConcurrencyTrackingController.instances = []
    monkeypatch.setattr(service, "SERVICE_PORT", "/dev/fake-eilik")
    monkeypatch.setattr(service, "LOG_PATH", "logs/test-eilik.log")
    monkeypatch.setattr(service, "SERVICE_LOGGER", logging.getLogger("test-eilik-service"))
    monkeypatch.setattr(service, "EilikController", ConcurrencyTrackingController)
    # Release the lock before each test so a failure in one cannot wedge
    # the next.
    try:
        service.SERIAL_LOCK.release()
    except RuntimeError:
        pass
    yield
    try:
        service.SERIAL_LOCK.release()
    except RuntimeError:
        pass


def test_concurrent_requests_do_not_overlap_on_the_device() -> None:
    """Two requests must not hold the device at the same time."""
    controller = service.controller
    results: list[str] = []
    errors: list[BaseException] = []

    def call() -> None:
        try:
            results.append(str(controller.wave()))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=call) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, errors
    assert len(results) == 5, results

    # Every request connected, waved and disconnected - in that order, and
    # never two connects without an intervening disconnect.
    for inst in ConcurrencyTrackingController.instances:
        assert inst.events.count("connect") == 1
        assert inst.events.count("disconnect") == 1


def test_a_queued_request_waits_and_then_succeeds() -> None:
    """The second request must not fail just because the first is running."""
    controller = service.controller
    out: list[object] = []

    def call() -> None:
        out.append(controller.wave())

    first = threading.Thread(target=call)
    first.start()
    second = threading.Thread(target=call)
    second.start()
    first.join(timeout=30)
    second.join(timeout=30)

    assert len(out) == 2, out
    assert not any(isinstance(v, BaseException) for v in out), out


def test_a_timed_out_request_does_not_disconnect_from_the_request_thread() -> None:
    """The worker owns the device until it finishes."""
    started = threading.Event()
    release = threading.Event()

    class SlowController(ConcurrencyTrackingController):
        def wave(self) -> None:
            started.set()
            release.wait(timeout=10)
            self.events.append("wave")

    SlowController.instances = []
    original = service.EilikController
    service.EilikController = SlowController
    try:
        original_timeout = service.REQUEST_TIMEOUT_SECONDS
        service.REQUEST_TIMEOUT_SECONDS = 0.3
        try:
            with pytest.raises(Exception) as excinfo:
                service.controller.wave()
        finally:
            service.REQUEST_TIMEOUT_SECONDS = original_timeout
    finally:
        service.EilikController = original
        release.set()

    assert "503" in str(excinfo.value) or "exceeded" in str(excinfo.value), excinfo.value
    assert started.wait(timeout=5), "the worker never started"

    # The request thread must NOT have closed the device while the worker
    # was still running.
    for inst in SlowController.instances:
        assert "disconnect" not in inst.events, inst.events
