"""Protocol helpers compatible with uDamocles/EilikSerialController."""

from __future__ import annotations

from dataclasses import dataclass

BAUD_RATE = 125000
SERIAL_TIMEOUT_SECONDS = 1.0

HEADER = bytes.fromhex("aa aa aa")
HANDSHAKE_SIGNATURE = bytes.fromhex("aa aa aa 0a 00 61")
HB1 = bytes.fromhex("aa aa aa 0a 00 61 e4 c6 f1 ca 83 ff ad")

SESSION_TOKEN_LENGTH = 5

MOTOR_RIGHT_ARM = 1
MOTOR_LEFT_ARM = 2
MOTOR_TORSO = 3
MOTOR_HEAD = 4

MIN_POSITION = 0
REST_POSITION = 1500
MAX_POSITION = 3000


@dataclass(frozen=True)
class ServoCommand:
    """A single motor target position."""

    motor_id: int
    position: int
    delay_after: float = 0.08


def calculate_checksum(payload: bytes) -> int:
    """Return the one-byte checksum used by the original implementation."""

    return 255 - (sum(payload) % 256)


def clamp_position(position: int) -> int:
    return max(MIN_POSITION, min(MAX_POSITION, int(position)))


def validate_motor_id(motor_id: int) -> None:
    if motor_id not in {MOTOR_RIGHT_ARM, MOTOR_LEFT_ARM, MOTOR_TORSO, MOTOR_HEAD}:
        raise ValueError(f"Unknown Eilik motor id: {motor_id}")


def extract_session_token(reply: bytes) -> bytes:
    """Extract the 5-byte anti-replay token from a handshake reply.

    The reference script slices bytes 6:11 after sending HB1. This keeps that
    behavior but first searches for the documented handshake signature so it can
    tolerate leading noise in the serial buffer.
    """

    idx = reply.find(HANDSHAKE_SIGNATURE)
    if idx == -1:
        if len(reply) >= len(HANDSHAKE_SIGNATURE) + SESSION_TOKEN_LENGTH:
            idx = 0
        else:
            raise ValueError("Handshake reply is too short to contain a session token")

    start = idx + len(HANDSHAKE_SIGNATURE)
    end = start + SESSION_TOKEN_LENGTH
    token = reply[start:end]
    if len(token) != SESSION_TOKEN_LENGTH:
        raise ValueError("Handshake reply ended before the session token was complete")
    return token


def build_servo_payload(session_token: bytes, motor_id: int, position: int) -> bytes:
    """Build the command payload, excluding the leading aa aa aa header."""

    if len(session_token) != SESSION_TOKEN_LENGTH:
        raise ValueError("Eilik session token must be exactly 5 bytes")
    validate_motor_id(motor_id)
    pos_bytes = clamp_position(position).to_bytes(2, byteorder="little")
    return (
        bytes.fromhex("14 00 61")
        + session_token
        + bytes.fromhex("03 01")
        + bytes([motor_id])
        + bytes.fromhex("01")
        + pos_bytes
        + bytes.fromhex("00 00 00 00 00")
    )


def build_servo_frame(session_token: bytes, motor_id: int, position: int) -> bytes:
    """Build a complete Eilik motor command frame.

    Frame shape preserved from the reference project:
    aa aa aa + 14 00 61 + token + 03 01 + motor + 01 + posLE + padding + checksum
    """

    payload = build_servo_payload(session_token, motor_id, position)
    return HEADER + payload + bytes([calculate_checksum(payload)])
