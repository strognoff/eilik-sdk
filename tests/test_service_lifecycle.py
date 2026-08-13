from __future__ import annotations

import logging

import pytest

from eilik import service


class FakeEilikController:
    instances: list["FakeEilikController"] = []

    def __init__(self, port=None, log_path=None, enable_keepalive=True):
        self.port = port
        self.log_path = log_path
        self.enable_keepalive = enable_keepalive
        self.events: list[str] = []
        self.logger = logging.getLogger("test-eilik")
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

    def _run_motion(self, name: str) -> None:
        self.events.append(f"motion:{name}")

    def move_motor(self, motor_id: int, position: int) -> None:
        self.events.append(f"move:{motor_id}:{position}")

    def reset_pose(self) -> None:
        self.events.append("reset_pose")

    def restore_idle_face(self, auto_rotate=True) -> bool:
        self.events.append(f"restore_idle_face:{auto_rotate}")
        return True

    def display_image(self, path, invert=False, threshold=128, hold_seconds=10.0, auto_idle=True):
        self.events.append(f"display_image:{hold_seconds}:{auto_idle}")
        return True

    def fail(self) -> None:
        self.events.append("fail")
        raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def fake_controller(monkeypatch):
    FakeEilikController.instances = []
    monkeypatch.setattr(service, "SERVICE_PORT", "/dev/fake-eilik")
    monkeypatch.setattr(service, "LOG_PATH", "logs/test-eilik.log")
    monkeypatch.setattr(service, "SERVICE_LOGGER", logging.getLogger("test-eilik-service"))
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


def test_generic_motion_endpoint_uses_one_on_demand_session() -> None:
    result = service.run_motion("wave")

    assert result == {"status": "ok", "action": "wave"}
    assert len(FakeEilikController.instances) == 1
    robot = FakeEilikController.instances[0]
    assert robot.enable_keepalive is False
    assert robot.events == ["connect", "motion:wave", "disconnect"]


def test_servo_move_endpoint_accepts_motor_names() -> None:
    result = service.servo_move({"motor": "right_arm", "position": 500})

    assert result == {"status": "ok", "motor_id": 1, "position": 500}
    robot = FakeEilikController.instances[0]
    assert robot.events == ["connect", "move:1:500", "disconnect"]


def test_display_text_defaults_to_no_auto_idle_cleanup() -> None:
    result = service.display_text({"text": "Hello", "hold_seconds": 5})

    assert result["status"] == "ok"
    robot = FakeEilikController.instances[0]
    assert robot.events == ["connect", "display_image:5.0:False", "disconnect"]


def test_display_text_arms_routine_is_one_session(monkeypatch) -> None:
    now = {"value": 0.0}

    def fake_monotonic():
        now["value"] += 0.25
        return now["value"]

    monkeypatch.setattr(service.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(service.time, "sleep", lambda _seconds: None)

    result = service.routine_display_text_arms(
        {
            "text": "Hello Alice!!",
            "duration_seconds": 0.5,
            "cleanup": "arms_down",
        }
    )

    assert result["status"] == "ok"
    assert result["cleanup"] == "arms_down"
    assert len(FakeEilikController.instances) == 1
    robot = FakeEilikController.instances[0]
    assert robot.events[0] == "connect"
    assert robot.events[1] == "display_image:0:False"
    assert "move:1:500" in robot.events
    assert "move:2:2500" in robot.events
    assert robot.events[-3:] == ["move:1:2500", "move:2:500", "disconnect"]
