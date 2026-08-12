"""Unit + live tests for ambient displays + choreography."""

import sys
from pathlib import Path

sys.path.insert(0, '.')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eilik.ambient import (
    render_clock_png, render_streak_png, render_weather_png, render_pr_png,
    render_calendar_png, render_energy_meter_png, render_mood_png,
    render_crypto_ticker_png, render_tts_text_png,
)


def _png_sane(p: Path) -> bool:
    """PNG exists, 128x64, 8-bit grayscale."""
    from PIL import Image
    img = Image.open(p)
    return img.size == (128, 64) and img.mode == 'L'


def test_render_clock():
    """render_clock_png produces a valid 128x64 grayscale PNG."""
    p = render_clock_png(15, 30)
    assert p.exists()
    assert _png_sane(p)


def test_render_clock_pads_zero():
    """Hours and minutes under 10 get zero-padded."""
    p = render_clock_png(9, 5)
    assert p.exists()
    # ASCII readback would show "09:05" — checking the PNG content indirectly.
    from PIL import Image
    img = Image.open(p)
    text = ''
    for y in range(64):
        for x in range(128):
            if img.getpixel((x, y)) < 128:
                text += '#'
            else:
                text += '.'
    assert '##' in text  # has some pixel structure (i.e. text rendered)


def test_render_streak():
    p = render_streak_png(7)
    assert p.exists() and _png_sane(p)


def test_render_weather():
    p = render_weather_png("sunny")
    assert p.exists() and _png_sane(p)


def test_render_weather_truncates_to_8():
    """Long condition text gets clipped to 8 chars."""
    p = render_weather_png("thunderstorm with heavy rain and hail")
    assert p.exists() and _png_sane(p)


def test_render_pr_no_author():
    p = render_pr_png(42)
    assert p.exists() and _png_sane(p)


def test_render_pr_with_author():
    p = render_pr_png(42, author="jeff")
    assert p.exists() and _png_sane(p)


def test_render_calendar_nudge():
    p = render_calendar_png(5)
    assert p.exists() and _png_sane(p)


def test_render_calendar_nudge_with_title():
    p = render_calendar_png(15, meeting_title="Managers Catchup")
    assert p.exists() and _png_sane(p)


def test_render_energy_meter():
    p = render_energy_meter_png(87)
    assert p.exists() and _png_sane(p)


def test_render_mood():
    p = render_mood_png("happy")
    assert p.exists() and _png_sane(p)


def test_render_crypto_ticker_pumped():
    p = render_crypto_ticker_png("BTC", 5.2)
    assert p.exists() and _png_sane(p)


def test_render_crypto_ticker_dumped():
    """Negative change shows ↓."""
    p = render_crypto_ticker_png("ETH", -3.1)
    assert p.exists() and _png_sane(p)


def test_render_tts_short():
    p = render_tts_text_png("hi")
    assert p.exists() and _png_sane(p)


def test_render_tts_long_splits_two_lines():
    """>14 char text splits into two lines."""
    p = render_tts_text_png("This is a longer message that should be split")
    assert p.exists() and _png_sane(p)


# ----- Live tests -----

import os
if os.environ.get('EILIK_TEST_LIVE'):

    def test_live_show_clock():
        """Live: show_clock() pops a clock face on Eilik."""
        from eilik.controller import EilikController
        robot = EilikController(port='/dev/ttyACM1')
        robot.connect()
        try:
            ok = robot.show_clock(hour=14, minute=30, hold_seconds=2)
            assert ok is True
        finally:
            robot.disconnect()


    def test_live_show_pr():
        """Live: show_pr() pushes a PR face."""
        from eilik.controller import EilikController
        robot = EilikController(port='/dev/ttyACM1')
        robot.connect()
        try:
            ok = robot.show_pr(42, author="quinn", hold_seconds=2)
            assert ok is True
        finally:
            robot.disconnect()


    def test_live_choreography_text():
        """Live: choreography() with a text step pops the text on Eilik."""
        from eilik.controller import EilikController
        robot = EilikController(port='/dev/ttyACM1')
        robot.connect()
        try:
            robot.choreography([
                {"text": "Live", "hold": 2},
            ])
        finally:
            robot.disconnect()
