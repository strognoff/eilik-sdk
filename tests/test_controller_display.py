"""Tests for the controller's display + move_motor (canonical PackAnalyData format).

These run against the live robot if `EILIK_TEST_LIVE=1` and a real
`/dev/ttyACM0` is connected. Otherwise they're skipped.

Tests verify:
- write_display accepts a 1024-byte payload and returns True on ACK
- read_display returns a 1024-byte framebuffer
- display_image round-trips a small PNG
- move_motor (canonical cmd=0xA2) works without a session token
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LIVE = os.environ.get("EILIK_TEST_LIVE") == "1"


@unittest.skipUnless(LIVE, "set EILIK_TEST_LIVE=1 to run live tests")
class TestLiveDisplay(unittest.TestCase):
    def setUp(self) -> None:
        from eilik.controller import EilikController

        self.controller = EilikController()
        self.controller.connect()

    def tearDown(self) -> None:
        self.controller.disconnect()

    def test_write_display_accepts_1024_bytes(self) -> None:
        payload = bytes(1024)  # all off
        ok = self.controller.write_display(payload)
        self.assertTrue(ok, "firmware should ACK a valid 1024-byte framebuffer")

    def test_read_display_returns_1024_bytes(self) -> None:
        img = self.controller.read_display()
        self.assertIsNotNone(img)
        self.assertEqual(len(img), 1024)

    def test_display_image_with_png(self) -> None:
        from PIL import Image, ImageDraw

        img = Image.new("L", (128, 64), 255)
        draw = ImageDraw.Draw(img)
        # Two big eyes
        for cx, cy in [(35, 22), (93, 22)]:
            for x in range(-12, 13):
                for y in range(-12, 13):
                    if x * x + y * y <= 144:
                        img.putpixel((cx + x, cy + y), 0)
        png_path = Path("/tmp/_test_face.png")
        img.save(png_path)
        ok = self.controller.display_image(png_path, invert=False)
        self.assertTrue(ok)

    def test_move_motor_works_without_token(self) -> None:
        # canonical cmd=0xA2 doesn't require a session token
        self.controller.move_motor(1, 1500)
        self.controller.move_motor(1, 2500)

    def test_read_servo_angles_returns_4_values(self) -> None:
        angles = self.controller.read_servo_angles()
        # The exact servo-id-to-byte-offset mapping isn't pinned down yet,
        # but the firmware returns at least 4 u16 values
        self.assertGreaterEqual(len(angles), 4)


class TestDetectPort(unittest.TestCase):
    """Static-method unit tests for the port detection logic.

    These run without any hardware — they just verify that `detect_port`
    returns a `/dev/ttyACM*` path on this host when one exists.
    """

    def test_detect_returns_acm_path(self) -> None:
        import glob as _glob
        from eilik.controller import EilikController

        acm_paths = sorted(_glob.glob("/dev/ttyACM*"))
        if not acm_paths:
            self.skipTest("no /dev/ttyACM* on this host")
        result = EilikController.detect_port()
        self.assertTrue(result.startswith("/dev/ttyACM"))


if __name__ == "__main__":
    unittest.main()