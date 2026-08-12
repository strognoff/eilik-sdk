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
    # ----- Bucket A: new emotes -----
    # Thumbs up: both arms up briefly. No real "thumb", just arms up.
    "thumbs_up": (
        ServoCommand(MOTOR_RIGHT_ARM, RIGHT_ARM_UP, 0.10),
        ServoCommand(MOTOR_LEFT_ARM, LEFT_ARM_UP, 0.10),
        ServoCommand(MOTOR_RIGHT_ARM, REST_POSITION, 0.08),
        ServoCommand(MOTOR_LEFT_ARM, REST_POSITION, 0.08),
    ),
    # High five: right arm straight up.
    "high_five": (
        ServoCommand(MOTOR_RIGHT_ARM, RIGHT_ARM_UP, 0.10),
        ServoCommand(MOTOR_RIGHT_ARM, REST_POSITION, 0.10),
    ),
    # Fist bump: right arm horizontal (mid-position) forward tap.
    "fist_bump": (
        ServoCommand(MOTOR_RIGHT_ARM, 1500, 0.10),
        ServoCommand(MOTOR_RIGHT_ARM, 1300, 0.06),
        ServoCommand(MOTOR_RIGHT_ARM, 1500, 0.06),
        ServoCommand(MOTOR_RIGHT_ARM, REST_POSITION, 0.08),
    ),
    # Shrug: both arms up, head turn left then right.
    "shrug": (
        ServoCommand(MOTOR_RIGHT_ARM, RIGHT_ARM_UP, 0.10),
        ServoCommand(MOTOR_LEFT_ARM, LEFT_ARM_UP, 0.10),
        ServoCommand(MOTOR_HEAD, HEAD_LEFT, 0.10),
        ServoCommand(MOTOR_HEAD, HEAD_RIGHT, 0.10),
        ServoCommand(MOTOR_HEAD, REST_POSITION, 0.06),
        ServoCommand(MOTOR_RIGHT_ARM, REST_POSITION, 0.06),
        ServoCommand(MOTOR_LEFT_ARM, REST_POSITION, 0.06),
    ),
    # Bow: head/torso dip down (using torso forward + arms sweep out).
    "bow": (
        ServoCommand(MOTOR_RIGHT_ARM, 1000, 0.08),
        ServoCommand(MOTOR_LEFT_ARM, 2000, 0.08),
        ServoCommand(MOTOR_HEAD, HEAD_LEFT, 0.06),
        ServoCommand(MOTOR_HEAD, REST_POSITION, 0.08),
        ServoCommand(MOTOR_RIGHT_ARM, REST_POSITION, 0.08),
        ServoCommand(MOTOR_LEFT_ARM, REST_POSITION, 0.08),
    ),
    # Wiggle (dance): torso wiggle left-right, arms mildly up.
    "wiggle": (
        ServoCommand(MOTOR_TORSO, TORSO_LEFT, 0.06),
        ServoCommand(MOTOR_TORSO, TORSO_RIGHT, 0.06),
        ServoCommand(MOTOR_TORSO, TORSO_LEFT, 0.06),
        ServoCommand(MOTOR_TORSO, TORSO_RIGHT, 0.06),
        ServoCommand(MOTOR_TORSO, REST_POSITION, 0.04),
    ),
    # Peek: head left slow, back to center, head right slow.
    "peek": (
        ServoCommand(MOTOR_HEAD, HEAD_LEFT, 0.18),
        ServoCommand(MOTOR_HEAD, REST_POSITION, 0.10),
        ServoCommand(MOTOR_HEAD, HEAD_RIGHT, 0.18),
        ServoCommand(MOTOR_HEAD, REST_POSITION, 0.10),
    ),
    # Spin: torso full rotation left to right (limited by safe range).
    "spin": (
        ServoCommand(MOTOR_TORSO, TORSO_LEFT, 0.18),
        ServoCommand(MOTOR_TORSO, TORSO_RIGHT, 0.18),
        ServoCommand(MOTOR_TORSO, REST_POSITION, 0.10),
    ),
    # Nod emphatic (three quick yeses).
    "nod_emphatic": (
        ServoCommand(MOTOR_TORSO, TORSO_LEFT, 0.05),
        ServoCommand(MOTOR_TORSO, REST_POSITION, 0.04),
        ServoCommand(MOTOR_TORSO, TORSO_LEFT, 0.05),
        ServoCommand(MOTOR_TORSO, REST_POSITION, 0.04),
        ServoCommand(MOTOR_TORSO, TORSO_LEFT, 0.05),
        ServoCommand(MOTOR_TORSO, REST_POSITION, 0.05),
    ),
    # Shake head emphatic (three quick no's).
    "shake_head_emphatic": (
        ServoCommand(MOTOR_HEAD, HEAD_LEFT, 0.05),
        ServoCommand(MOTOR_HEAD, HEAD_RIGHT, 0.05),
        ServoCommand(MOTOR_HEAD, HEAD_LEFT, 0.05),
        ServoCommand(MOTOR_HEAD, HEAD_RIGHT, 0.05),
        ServoCommand(MOTOR_HEAD, HEAD_LEFT, 0.05),
        ServoCommand(MOTOR_HEAD, REST_POSITION, 0.05),
    ),
    # Heart hands: both arms up forming a heart shape (arms angled inward).
    "heart_hands": (
        ServoCommand(MOTOR_RIGHT_ARM, 1500, 0.10),
        ServoCommand(MOTOR_LEFT_ARM, 1500, 0.10),
        ServoCommand(MOTOR_HEAD, HEAD_LEFT, 0.06),
        ServoCommand(MOTOR_HEAD, REST_POSITION, 0.08),
        ServoCommand(MOTOR_RIGHT_ARM, REST_POSITION, 0.08),
        ServoCommand(MOTOR_LEFT_ARM, REST_POSITION, 0.08),
    ),
    # Surprise jump-back: torso left quick, arms up.
    "surprise": (
        ServoCommand(MOTOR_TORSO, TORSO_LEFT, 0.04),
        ServoCommand(MOTOR_RIGHT_ARM, RIGHT_ARM_UP, 0.05),
        ServoCommand(MOTOR_LEFT_ARM, LEFT_ARM_UP, 0.05),
        ServoCommand(MOTOR_TORSO, REST_POSITION, 0.10),
        ServoCommand(MOTOR_RIGHT_ARM, REST_POSITION, 0.08),
        ServoCommand(MOTOR_LEFT_ARM, REST_POSITION, 0.08),
    ),
}
