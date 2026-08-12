"""High-level Eilik motions built from the known servo protocol."""

from __future__ import annotations

from .protocol import (
    MOTOR_HEAD,
    MOTOR_LEFT_ARM,
    MOTOR_RIGHT_ARM,
    MOTOR_TORSO,
    REST_POSITION,
    ServoCommand,
)

RIGHT_ARM_UP = 500
RIGHT_ARM_DOWN = 2500
LEFT_ARM_UP = 2500
LEFT_ARM_DOWN = 500
HEAD_LEFT = 500
HEAD_RIGHT = 2500
TORSO_LEFT = 2500
TORSO_RIGHT = 500

RESET_POSE = (
    ServoCommand(MOTOR_RIGHT_ARM, REST_POSITION, 0.03),
    ServoCommand(MOTOR_LEFT_ARM, REST_POSITION, 0.03),
    ServoCommand(MOTOR_TORSO, REST_POSITION, 0.03),
    ServoCommand(MOTOR_HEAD, REST_POSITION, 0.08),
)

MOTIONS: dict[str, tuple[ServoCommand, ...]] = {
    "reset_pose": RESET_POSE,
    "look_left": (
        ServoCommand(MOTOR_HEAD, HEAD_LEFT, 0.12),
        ServoCommand(MOTOR_HEAD, REST_POSITION, 0.05),
    ),
    "look_right": (
        ServoCommand(MOTOR_HEAD, HEAD_RIGHT, 0.12),
        ServoCommand(MOTOR_HEAD, REST_POSITION, 0.05),
    ),
    "left_arm_up": (ServoCommand(MOTOR_LEFT_ARM, LEFT_ARM_UP, 0.08),),
    "left_arm_down": (ServoCommand(MOTOR_LEFT_ARM, LEFT_ARM_DOWN, 0.08),),
    "right_arm_up": (ServoCommand(MOTOR_RIGHT_ARM, RIGHT_ARM_UP, 0.08),),
    "right_arm_down": (ServoCommand(MOTOR_RIGHT_ARM, RIGHT_ARM_DOWN, 0.08),),
    "wave": (
        ServoCommand(MOTOR_RIGHT_ARM, RIGHT_ARM_UP, 0.12),
        ServoCommand(MOTOR_HEAD, HEAD_LEFT, 0.10),
        ServoCommand(MOTOR_HEAD, HEAD_RIGHT, 0.10),
        ServoCommand(MOTOR_HEAD, HEAD_LEFT, 0.10),
        ServoCommand(MOTOR_HEAD, REST_POSITION, 0.08),
        ServoCommand(MOTOR_RIGHT_ARM, REST_POSITION, 0.08),
    ),
    "shake_head": (
        ServoCommand(MOTOR_HEAD, HEAD_LEFT, 0.10),
        ServoCommand(MOTOR_HEAD, HEAD_RIGHT, 0.10),
        ServoCommand(MOTOR_HEAD, HEAD_LEFT, 0.10),
        ServoCommand(MOTOR_HEAD, REST_POSITION, 0.08),
    ),
    # The known public protocol exposes horizontal head/torso axes, not a
    # vertical neck servo, so nod is an expressive small body/head gesture.
    "nod": (
        ServoCommand(MOTOR_TORSO, TORSO_LEFT, 0.08),
        ServoCommand(MOTOR_TORSO, TORSO_RIGHT, 0.08),
        ServoCommand(MOTOR_TORSO, REST_POSITION, 0.06),
        ServoCommand(MOTOR_HEAD, REST_POSITION, 0.04),
    ),
}
