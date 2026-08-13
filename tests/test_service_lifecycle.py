from __future__ import annotations

import pytest

from eilik import service


class FakeEilikController:
    instances: list["FakeEilikController"] = []

    def __init__(self, port=None, log_path=None, enable_keepalive=True):
        self.port = port
        self.log_path = log_path
        self.enable_keepalive = enable_keepalive
        self.events: list[str] = []
        FakeEilikController.instances.append(self)

    @staticmethod
    def detect_port() -> str:
        return "/dev/fake-eilik"

    def connect(self) -> None:
        self.events.append("connect")

    def disconnect(self) -> None:
        self.events.append("disconnect")

    def wave(self) -> None:
        self.events.append("wave")

    def fail(self) -> None:
        self.events.append("fail")
        raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def fake_controller(monkeypatch):
    FakeEilikController.instances = []
    monkeypatch.setattr(service, "SERVICE_PORT", "/dev/fake-eilik")
    monkeypatch.setattr(service, "LOG_PATH", "logs/test-eilik.log")
    monkeypatch.setattr(service, "EilikController", FakeEilikController)


def test_health_does_not_open_serial_session() -> None:
    result = service.health()

    assert result["service"] == "ok"
    assert result["mode"] == "on-demand"
    assert result["connected"] is False
    assert result["protocol"] is None
    assert result["port"] == "/dev/fake-eilik"
    assert FakeEilikController.instances == []


def test_command_opens_without_keepalive_and_disconnects() -> None:
    result = service.wave()

    assert result == {"status": "ok", "action": "wave"}
    assert len(FakeEilikController.instances) == 1
    robot = FakeEilikController.instances[0]
    assert robot.enable_keepalive is False
    assert robot.events == ["connect", "wave", "disconnect"]


def test_command_disconnects_after_failure() -> None:
    with pytest.raises(RuntimeError):
        service.controller.fail()

    assert len(FakeEilikController.instances) == 1
    robot = FakeEilikController.instances[0]
    assert robot.enable_keepalive is False
    assert robot.events == ["connect", "fail", "disconnect"]
