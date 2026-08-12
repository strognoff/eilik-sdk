"""Generate all standard face expressions as PNGs.

Faces are 128x64 monochrome. We generate them with PIL using a centered text
and (optional) emoji fallback. Each face becomes a separate .png under
`eilik/assets/faces/`. The SDK then loads them on demand.

This module also exposes `FACE_LIBRARY` (dict name -> PNG path) and
`DEFAULT_FACE` (path) for the idle face.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FACES_DIR = HERE / "faces"
FACES_DIR.mkdir(parents=True, exist_ok=True)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Each face is (filename, lines [(text, size, y-offset-or-center)], extra-draw-callback)
# extra-draw-callback draws after the text (e.g. underline, dots, smileys).

def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.truetype(FONT_BOLD, size)

def _save(img: Image.Image, name: str) -> Path:
    out = FACES_DIR / f"{name}.png"
    img.save(out)
    return out

def _draw_centered(img: Image.Image, draw: ImageDraw.ImageDraw, text: str,
                   size: int, dy: int = 0) -> None:
    font = _font(size)
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (128 - w) // 2 - bbox[0]
    y = (64 - h) // 2 - bbox[1] + dy
    draw.text((x, y), text, fill=0, font=font)


def _face_smiley(text: str, name: str, size: int = 22, dy: int = -6) -> Path:
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    _draw_centered(img, draw, text, size, dy=dy)
    # :) underneath
    f2 = _font(18)
    bbox2 = draw.textbbox((0, 0), ":)", font=f2)
    w2 = bbox2[2] - bbox2[0]
    x2 = (128 - w2) // 2 - bbox2[0]
    draw.text((x2, 44), ":)", fill=0, font=f2)
    return _save(img, name)


def _face_text(text: str, name: str, size: int = 18, dy: int = 0) -> Path:
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    _draw_centered(img, draw, text, size, dy=dy)
    return _save(img, name)


def _face_two_lines(line1: str, line2: str, name: str, size: int = 18) -> Path:
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    f1 = _font(size)
    f2 = _font(size)
    for line, y, font in [(line1, 12, f1), (line2, 38, f2)]:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (128 - w) // 2 - bbox[0]
        draw.text((x, y), line, fill=0, font=font)
    return _save(img, name)


def _face_dots(name: str, n: int = 3, dy: int = 0) -> Path:
    """Thinking / working / typing face: '...' with optional emoji."""
    text = "." * n
    return _face_text(text, name, size=36, dy=dy)


def _face_inline(parts: list[tuple[str, int]], name: str, dy: int = 0) -> Path:
    """Multi-segment face: list of (text, size)."""
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    total_w = 0
    rendered = []
    for text, size in parts:
        font = _font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        total_w += bbox[2] - bbox[0]
        rendered.append((text, size, bbox))
    x_cursor = (128 - total_w) // 2
    max_h = max(bbox[3] - bbox[1] for _, _, bbox in rendered)
    y = (64 - max_h) // 2 + dy
    for text, size, bbox in rendered:
        x_cursor += -bbox[0]
        draw.text((x_cursor, y), text, fill=0, font=_font(size))
        x_cursor += bbox[2] - bbox[0]
    return _save(img, name)


# --- FACE DEFINITIONS ---

def build_all_faces() -> dict[str, Path]:
    """Generate every face PNG and return {name: path}."""
    faces = {}

    # --- Reusable / onboarding ---
    faces["greeting_hi_jeff"] = _face_smiley("Hi Jeff!", "greeting_hi_jeff", size=18, dy=-4)
    faces["greeting_good_morning"] = _face_smiley("Morning!", "greeting_good_morning", size=18, dy=-4)
    faces["greeting_good_night"] = _face_smiley("Night!", "greeting_good_night", size=22, dy=-4)
    faces["greeting_welcome_back"] = _face_text("Welcome!", "greeting_welcome_back", size=20)
    faces["greeting_hi_nova"] = _face_smiley("Hi Nova!", "greeting_hi_nova", size=20, dy=-4)
    faces["greeting_bye"] = _face_smiley("Bye!", "greeting_bye", size=22, dy=-4)

    # --- Message / comms ---
    faces["comms_message"] = _face_two_lines("Message!!", ":)", "comms_message", size=18)
    faces["comms_got_it"] = _face_smiley("Got it", "comms_got_it", size=22, dy=-4)
    faces["comms_thanks"] = _face_smiley("Thanks!", "comms_thanks", size=22, dy=-4)
    faces["comms_done"] = _face_text("Done!", "comms_done", size=24)
    faces["comms_ok"] = _face_text("OK", "comms_ok", size=32)
    faces["comms_crypto_pumped"] = _face_text("+5% ↑", "comms_crypto_pumped", size=26)

    # --- Moods / emotions ---
    faces["mood_thinking"] = _face_dots("mood_thinking", 3, dy=0)  # "..."
    faces["mood_working"] = _face_dots("mood_working", 4, dy=0)  # "...."
    faces["mood_frustrated"] = _face_text(">:-(", "mood_frustrated", size=26)
    faces["mood_excited"] = _face_text("!!!", "mood_excited", size=36)
    faces["mood_surprised"] = _face_text("!?", "mood_surprised", size=36)
    faces["mood_confused"] = _face_text("?", "mood_confused", size=42)
    faces["mood_happy"] = _face_text("^o^", "mood_happy", size=28)
    faces["mood_heart_eyes"] = _face_text("♥_♥", "mood_heart_eyes", size=26)
    faces["mood_cool"] = _face_text("-_-/", "mood_cool", size=26)
    faces["mood_cry"] = _face_text("T_T", "mood_cry", size=28)
    faces["mood_laugh"] = _face_text("哈哈", "mood_laugh", size=26)
    faces["mood_angry"] = _face_text(">:(", "mood_angry", size=30)
    faces["mood_sleepy"] = _face_text("ZZZ", "mood_sleepy", size=28)
    faces["mood_proud"] = _face_text("★", "mood_proud", size=40)

    # --- Status / data ---
    faces["status_ok"] = _face_text("OK ✓", "status_ok", size=26)
    faces["status_done"] = _face_text("DONE", "status_done", size=26)
    faces["status_error"] = _face_text("X", "status_error", size=42)
    faces["status_fail"] = _face_text("FAIL", "status_fail", size=24)
    faces["status_warning"] = _face_text("!", "status_warning", size=42)
    faces["status_loading"] = _face_text("...", "status_loading", size=36)

    # --- Time / clock ---
    faces["clock_face_15_30"] = _face_text("15:30", "clock_face_15_30", size=22)
    faces["clock_face_22_58"] = _face_text("22:58", "clock_face_22_58", size=22)

    # --- Habit / streak ---
    faces["habit_streak_5"] = _face_text("Day 5", "habit_streak_5", size=22)
    faces["habit_streak_7"] = _face_text("Day 7", "habit_streak_7", size=22)
    faces["habit_streak_30"] = _face_text("Day 30", "habit_streak_30", size=20)

    # --- Weather ---
    faces["weather_sun"] = _face_text("SUN", "weather_sun", size=24)
    faces["weather_rain"] = _face_text("RAIN", "weather_rain", size=22)
    faces["weather_cloud"] = _face_text("CLOUD", "weather_cloud", size=20)

    # --- Special ---
    faces["calendar_nudge"] = _face_text("@5min", "calendar_nudge", size=24)
    faces["email_new"] = _face_text("@", "email_new", size=42)
    faces["pr_alert"] = _face_text("PR#42", "pr_alert", size=22)
    faces["quinn_comms"] = _face_text("Quinn!", "quinn_comms", size=22)
    faces["trivia_question"] = _face_text("?", "trivia_question", size=42)
    faces["trivia_correct"] = _face_text("YES!", "trivia_correct", size=26)
    faces["trivia_wrong"] = _face_text("NOPE", "trivia_wrong", size=26)

    return faces


if __name__ == "__main__":
    paths = build_all_faces()
    print(f"Generated {len(paths)} faces in {FACES_DIR}")
    for name in sorted(paths):
        print(f"  {name}: {paths[name].name}")
