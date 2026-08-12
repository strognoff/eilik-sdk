"""Eilik USB serial SDK."""

from .controller import EilikController
from .protocol import (
    BAUD_RATE,
    HB1,
    MOTOR_HEAD,
    MOTOR_LEFT_ARM,
    MOTOR_RIGHT_ARM,
    MOTOR_TORSO,
    OFFICIAL_SESSION_ACK,
    OFFICIAL_SESSION_START,
    OFFICIAL_STATUS_REQUEST,
    build_servo_frame,
    build_command_frame,
    calculate_checksum,
    extract_session_token,
)

__all__ = [
    "BAUD_RATE",
    "EilikController",
    "HB1",
    "MOTOR_HEAD",
    "MOTOR_LEFT_ARM",
    "MOTOR_RIGHT_ARM",
    "MOTOR_TORSO",
    "OFFICIAL_SESSION_ACK",
    "OFFICIAL_SESSION_START",
    "OFFICIAL_STATUS_REQUEST",
    "build_servo_frame",
    "build_command_frame",
    "calculate_checksum",
    "extract_session_token",
]
