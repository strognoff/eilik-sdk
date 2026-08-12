"""Ambient displays — show contextual data on Eilik's face.

These methods render dynamic content onto the face (clock, weather, streaks,
PR numbers, etc.) rather than just static faces. Each method accepts input
data and produces the right face tag dynamically.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def _draw_centered(img: Image.Image, draw: ImageDraw.ImageDraw, text: str,
                   size: int = 22, y: int | None = None) -> None:
    font = _font(size)
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (128 - w) // 2 - bbox[0]
    if y is None:
        y = (64 - h) // 2 - bbox[1]
    draw.text((x, y), text, fill=0, font=font)


def render_clock_png(hour: int, minute: int, out: Path | str = "/tmp/clock.png") -> Path:
    """Render a 'HH:MM' clock face."""
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    text = f"{hour:02d}:{minute:02d}"
    _draw_centered(img, draw, text, size=22)
    img.save(out)
    return Path(out)


def render_streak_png(days: int, out: Path | str = "/tmp/streak.png") -> Path:
    """Render 'Day N' streak face."""
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    text = f"Day {days}"
    _draw_centered(img, draw, text, size=22)
    img.save(out)
    return Path(out)


def render_weather_png(condition: str, out: Path | str = "/tmp/weather.png") -> Path:
    """Render a weather face based on a condition string."""
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    text = condition.upper()[:8]
    _draw_centered(img, draw, text, size=24)
    img.save(out)
    return Path(out)


def render_pr_png(pr_number: int, author: str | None = None,
                  out: Path | str = "/tmp/pr.png") -> Path:
    """Render 'PR#N' or 'PR#N by X' face."""
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    if author:
        text = f"PR#{pr_number}"
        _draw_centered(img, draw, text, size=22, y=8)
        text2 = author[:8]
        _draw_centered(img, draw, text2, size=18, y=36)
    else:
        text = f"PR#{pr_number}"
        _draw_centered(img, draw, text, size=22)
    img.save(out)
    return Path(out)


def render_calendar_png(minutes_until: int, meeting_title: str | None = None,
                        out: Path | str = "/tmp/cal.png") -> Path:
    """Render '@Nmin' or '@Nmin TIT' calendar nudge face."""
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    text = f"@{minutes_until}min"
    _draw_centered(img, draw, text, size=22, y=8)
    if meeting_title:
        title = meeting_title[:10]
        _draw_centered(img, draw, title, size=18, y=38)
    img.save(out)
    return Path(out)


def render_energy_meter_png(soi_percent: int, out: Path | str = "/tmp/energy.png") -> Path:
    """Render an 'SoI: NN%' face."""
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    text = f"SoI: {soi_percent}%"
    _draw_centered(img, draw, text, size=20)
    img.save(out)
    return Path(out)


def render_mood_png(mood: str, out: Path | str = "/tmp/mood.png") -> Path:
    """Render a mood face with emoji or word."""
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    mood = mood.upper()[:6]
    _draw_centered(img, draw, mood, size=22)
    img.save(out)
    return Path(out)


def render_crypto_ticker_png(ticker: str, change_pct: float,
                              out: Path | str = "/tmp/ticker.png") -> Path:
    """Render 'TICKER +5%↑' or 'TICKER -3%↓'."""
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    arrow = "↑" if change_pct >= 0 else "↓"
    text = f"{ticker[:4].upper()} {change_pct:+.0f}%{arrow}"
    _draw_centered(img, draw, text, size=20)
    img.save(out)
    return Path(out)


def render_tts_text_png(text: str, out: Path | str = "/tmp/tts.png") -> Path:
    """Render longer text for TTS-style display."""
    img = Image.new('L', (128, 64), 255)
    draw = ImageDraw.Draw(img)
    # Speaker icon at top
    draw.text((4, 4), "[ ]", fill=0, font=_font(12))
    # Body text — split into 2 lines if needed
    if len(text) > 14:
        mid = len(text) // 2
        for i in range(mid - 3, mid + 3):
            if text[i] == ' ':
                break
        line1 = text[:i]
        line2 = text[i+1:]
        _draw_centered(img, draw, line1, size=14, y=20)
        _draw_centered(img, draw, line2, size=14, y=42)
    else:
        _draw_centered(img, draw, text, size=18, y=22)
    img.save(out)
    return Path(out)
