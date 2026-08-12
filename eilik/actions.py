"""High-level Eilik actions combining motions + faces.

Every action is a callable method that drives Eilik as a body for Nova.
Each action combines:
- An optional face PNG (from `eilik/assets/faces/`)
- An optional motion (from `eilik/motions.py`)
- Per-action timing and coordination

The default behavior is: face + motion + return to neutral.
"""

from __future__ import annotations

import time
from pathlib import Path

from .assets.face_factory import FACES_DIR
from .motions import MOTIONS

# The face filenames live under eilik/assets/faces/. These names are stable.
FACE_TAGS = {p.stem for p in FACES_DIR.glob('*.png')}


def face_path(tag: str) -> Path:
    if tag not in FACE_TAGS:
        raise ValueError(f"Unknown face tag: {tag}. Known: {sorted(FACE_TAGS)}")
    return FACES_DIR / f"{tag}.png"


# Behaviors: each is `("emotion_type", motion_name_or_None, face_tag_or_None, hold_sec, comment)`.
# The SDK caller (controller.py) exposes each as a method that does:
#   1. Show face (auto_idle=False)
#   2. Run motion if any
#   3. Hold for `hold_sec`
#   4. Restore firmware idle (auto_idle=True)

ACTIONS = {
    # === ONBOARDING / GREETINGS ===
    "hi_jeff":        {"motion": "wave",  "face": "greeting_hi_jeff",     "hold": 1.5},
    "good_morning":   {"motion": "wave",  "face": "greeting_good_morning","hold": 1.5},
    "good_night":     {"motion": "wave",  "face": "greeting_good_night",  "hold": 1.5},
    "welcome_back":   {"motion": "bow",   "face": "greeting_welcome_back","hold": 2.0},
    "hi_nova":        {"motion": "wave",  "face": "greeting_hi_nova",     "hold": 1.5},
    "bye":            {"motion": "wave",  "face": "greeting_bye",         "hold": 1.5},

    # === MESSAGE RECEIVED ===
    "message":        {"motion": "wave",  "face": "comms_message",        "hold": 1.5},
    "got_it":         {"motion": "nod",   "face": "comms_got_it",         "hold": 1.5},
    "thanks":         {"motion": "wave",  "face": "comms_thanks",         "hold": 1.5},
    "done":           {"motion": "thumbs_up", "face": "comms_done",       "hold": 1.5},
    "ok":             {"motion": "nod",   "face": "comms_ok",             "hold": 1.0},

    # === MOOD / EMOTIONS ===
    "thinking":       {"motion": "peek",  "face": "mood_thinking",        "hold": 1.0},
    "working":        {"motion": "nod_emphatic", "face": "mood_working", "hold": 1.0},
    "frustrated":     {"motion": "shrug", "face": "mood_frustrated",      "hold": 1.0},
    "excited":        {"motion": "surprise", "face": "mood_excited",     "hold": 1.5},
    "surprised":      {"motion": "surprise", "face": "mood_surprised",   "hold": 1.0},
    "confused":       {"motion": "shake_head_emphatic", "face": "mood_confused", "hold": 1.0},
    "happy":          {"motion": "wiggle", "face": "mood_happy",         "hold": 1.5},
    "heart_eyes":     {"motion": "heart_hands", "face": "mood_heart_eyes", "hold": 2.0},
    "cool":           {"motion": "fist_bump", "face": "mood_cool",        "hold": 1.5},
    "cry":            {"motion": None,    "face": "mood_cry",             "hold": 1.5},
    "laugh":          {"motion": "wiggle", "face": "mood_laugh",         "hold": 1.5},
    "angry":          {"motion": "shake_head_emphatic", "face": "mood_angry", "hold": 1.0},
    "sleepy":         {"motion": None,    "face": "mood_sleepy",          "hold": 2.0},
    "proud":          {"motion": "thumbs_up", "face": "mood_proud",       "hold": 1.5},

    # === MOTION-ONLY EMOTES (no face flash) ===
    "thumbs_up":      {"motion": "thumbs_up",   "face": None, "hold": 1.0},
    "high_five":      {"motion": "high_five",   "face": None, "hold": 1.0},
    "fist_bump":      {"motion": "fist_bump",   "face": None, "hold": 1.0},
    "shrug":          {"motion": "shrug",       "face": "mood_frustrated", "hold": 1.0},
    "bow":            {"motion": "bow",         "face": None, "hold": 1.5},
    "wiggle":         {"motion": "wiggle",      "face": None, "hold": 1.5},
    "peek":           {"motion": "peek",        "face": None, "hold": 1.0},
    "spin":           {"motion": "spin",        "face": None, "hold": 1.5},
    "nod_emphatic":   {"motion": "nod_emphatic","face": None, "hold": 1.0},
    "shake_head_emphatic": {"motion": "shake_head_emphatic", "face": None, "hold": 1.0},
    "heart_hands":    {"motion": "heart_hands", "face": "mood_heart_eyes", "hold": 2.0},

    # === STATUS / RESPONSE CODES ===
    "status_ok":      {"motion": "nod",     "face": "status_ok",     "hold": 1.0},
    "status_done":    {"motion": "thumbs_up","face": "status_done",   "hold": 1.5},
    "status_error":   {"motion": "shake_head_emphatic", "face": "status_error", "hold": 2.0},
    "status_fail":    {"motion": "shake_head_emphatic", "face": "status_fail",  "hold": 2.0},
    "status_warning": {"motion": "shrug",   "face": "status_warning","hold": 1.5},
    "status_loading": {"motion": "peek",    "face": "status_loading","hold": 1.0},

    # === CONTEXTUAL DISPLAYS ===
    "time_15_30":     {"motion": None, "face": "clock_face_15_30", "hold": 2.0},
    "time_22_58":     {"motion": None, "face": "clock_face_22_58", "hold": 2.0},
    "weather_sun":    {"motion": "wave", "face": "weather_sun",   "hold": 2.0},
    "weather_rain":   {"motion": "nod",  "face": "weather_rain",  "hold": 2.0},
    "weather_cloud":  {"motion": "peek", "face": "weather_cloud", "hold": 2.0},
    "habit_streak_5": {"motion": None, "face": "habit_streak_5",  "hold": 2.0},
    "habit_streak_7": {"motion": "thumbs_up", "face": "habit_streak_7", "hold": 2.0},
    "habit_streak_30":{"motion": "wiggle", "face": "habit_streak_30", "hold": 3.0},

    # === LIVE EVENT BRIDGES ===
    "calendar_nudge": {"motion": "shrug", "face": "calendar_nudge","hold": 1.0},
    "email_new":      {"motion": "peek",  "face": "email_new",     "hold": 1.0},
    "pr_alert":       {"motion": "nod",   "face": "pr_alert",      "hold": 1.5},
    "quinn_comms":    {"motion": "wave",  "face": "quinn_comms",   "hold": 1.5},
    "crypto_pumped":  {"motion": "wiggle", "face": "comms_crypto_pumped", "hold": 2.0},

    # === GAMES / INTERACTIVE ===
    "trivia_question":{"motion": "peek",  "face": "trivia_question","hold": 0},
    "trivia_correct": {"motion": "thumbs_up", "face": "trivia_correct", "hold": 2.0},
    "trivia_wrong":   {"motion": "shake_head_emphatic", "face": "trivia_wrong", "hold": 1.5},
}


def get_action(name: str) -> dict:
    """Lookup the action spec."""
    if name not in ACTIONS:
        raise ValueError(f"Unknown action: {name}")
    return ACTIONS[name]


def resolve_face(face_tag: str | None) -> Path | None:
    if not face_tag:
        return None
    return face_path(face_tag)
