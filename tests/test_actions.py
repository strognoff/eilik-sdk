"""Unit + live tests for the Stage 2 actions library."""

from pathlib import Path
import sys

sys.path.insert(0, '.')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eilik.actions import ACTIONS, FACE_TAGS, resolve_face, get_action
from eilik.motions import MOTIONS


def test_every_action_has_required_fields():
    """Every action must have motion, face, hold keys."""
    for name, spec in ACTIONS.items():
        assert 'motion' in spec, f"{name}: missing motion field"
        assert 'face' in spec, f"{name}: missing face field"
        assert 'hold' in spec, f"{name}: missing hold field"
        assert isinstance(spec['hold'], (int, float)), f"{name}: hold must be numeric"


def test_every_motion_exists():
    """If an action names a motion, that motion must be in MOTIONS."""
    for name, spec in ACTIONS.items():
        motion = spec.get('motion')
        if motion:
            assert motion in MOTIONS, f"{name}: motion {motion!r} not in MOTIONS"


def test_every_face_png_exists():
    """If an action names a face, that face PNG must exist."""
    for name, spec in ACTIONS.items():
        face = spec.get('face')
        if face:
            assert face in FACE_TAGS, f"{name}: face {face!r} not in FACE_TAGS"


def test_get_action_known():
    """get_action() returns the spec for known actions."""
    spec = get_action('message')
    assert spec['motion'] == 'wave'
    assert spec['face'] == 'comms_message'


def test_get_action_unknown_raises():
    """get_action() raises for unknown actions."""
    import pytest
    with pytest.raises(ValueError):
        get_action('definitely_not_a_real_action')


def test_resolve_face_known():
    """resolve_face() returns a Path for known tags."""
    p = resolve_face('mood_happy')
    assert p.exists()


def test_resolve_face_none():
    """resolve_face(None) returns None."""
    assert resolve_face(None) is None


def test_action_count():
    """At least 50 actions defined."""
    assert len(ACTIONS) >= 50, f"only {len(ACTIONS)} actions; target 50+"


# ----- Live tests -----

import os
if os.environ.get('EILIK_TEST_LIVE'):

    def test_live_action_message():
        """Live: action('message') shows Message!! + wave."""
        from eilik.controller import EilikController
        robot = EilikController(port='/dev/ttyACM1')
        robot.connect()
        try:
            ok = robot.action('message')
            assert ok is True
        finally:
            robot.disconnect()


    def test_live_action_thinking():
        """Live: action('thinking') shows ... face + peek."""
        from eilik.controller import EilikController
        robot = EilikController(port='/dev/ttyACM1')
        robot.connect()
        try:
            ok = robot.action('thinking')
            assert ok is True
        finally:
            robot.disconnect()


    def test_live_action_shrug():
        """Live: action('shrug') runs shrug motion + face."""
        from eilik.controller import EilikController
        robot = EilikController(port='/dev/ttyACM1')
        robot.connect()
        try:
            ok = robot.action('shrug')
            assert ok is True
        finally:
            robot.disconnect()
