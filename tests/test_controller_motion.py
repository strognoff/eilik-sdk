from __future__ import annotations

from eilik.controller import EilikController
from eilik.pack import write_servo


class FakeSerial:
    is_open = True

    def __init__(self) -> None:
        self.writes: list[bytes] = []

    @property
    def in_waiting(self) -> int:
        return 0

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def read(self, _size: int) -> bytes:
        return b""


def connected_controller() -> tuple[EilikController, FakeSerial]:
    controller = EilikController(reconnect_attempts=0)
    serial = FakeSerial()
    controller._serial = serial
    controller._protocol_variant = "legacy-token"
    controller._session_token = bytes.fromhex("11 22 33 44 55")
    return controller, serial


def test_move_motor_uses_canonical_direct_servo_packet() -> None:
    controller, serial = connected_controller()

    controller.move_motor(1, 500)

    assert serial.writes == [write_servo([(1, 500)])]
    assert serial.writes[0][5] == 0xA2


def test_motion_engine_uses_canonical_direct_servo_packets() -> None:
    controller, serial = connected_controller()

    controller._run_motion("right_arm_up")

    assert serial.writes == [write_servo([(1, 500)])]
    assert serial.writes[0][5] == 0xA2
    assert b"\x61\x11\x22\x33\x44\x55" not in serial.writes[0]
