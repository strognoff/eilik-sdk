"""FastAPI service for Eilik control."""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Callable, TypeVar

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .controller import EilikController
from .logger import setup_logger
from .motions import MOTIONS
from .protocol import (
    MAX_POSITION,
    MIN_POSITION,
    MOTOR_HEAD,
    MOTOR_LEFT_ARM,
    MOTOR_RIGHT_ARM,
    MOTOR_TORSO,
    REST_POSITION,
    validate_motor_id,
)

SERVICE_PORT = os.getenv("EILIK_PORT") or None
LOG_PATH = os.getenv("EILIK_LOG_PATH", "logs/eilik.log")
SERVICE_LOGGER = setup_logger(LOG_PATH)
app = FastAPI(title="Eilik Controller Service", version="0.1.0")
T = TypeVar("T")

MOTOR_NAMES = {
    "right_arm": MOTOR_RIGHT_ARM,
    "left_arm": MOTOR_LEFT_ARM,
    "torso": MOTOR_TORSO,
    "head": MOTOR_HEAD,
}


class OnDemandController:
    """Open Eilik only while handling one API command, then release USB serial."""

    @property
    def connected(self) -> bool:
        return False

    @property
    def protocol_variant(self) -> None:
        return None

    @property
    def port(self) -> str | None:
        if SERVICE_PORT:
            return SERVICE_PORT
        try:
            return EilikController.detect_port()
        except Exception:
            return None

    def __getattr__(self, name: str):
        def call(*args, **kwargs):
            return self.run(name, lambda robot: getattr(robot, name)(*args, **kwargs))

        return call

    def run(self, operation: str, fn: Callable[[EilikController], T]) -> T:
        request_id = uuid.uuid4().hex[:12]
        started = time.monotonic()
        SERVICE_LOGGER.info("API_START id=%s operation=%s", request_id, operation)
        robot = EilikController(
            port=SERVICE_PORT,
            log_path=LOG_PATH,
            enable_keepalive=False,
        )
        try:
            robot.connect()
            result = fn(robot)
            SERVICE_LOGGER.info(
                "API_END id=%s operation=%s status=ok duration_ms=%s",
                request_id,
                operation,
                round((time.monotonic() - started) * 1000),
            )
            return result
        except Exception as exc:
            SERVICE_LOGGER.exception(
                "API_END id=%s operation=%s status=error duration_ms=%s error=%s",
                request_id,
                operation,
                round((time.monotonic() - started) * 1000),
                exc,
            )
            raise
        finally:
            robot.disconnect()


controller = OnDemandController()


def _bool(payload: dict, name: str, default: bool = False) -> bool:
    return bool(payload.get(name, default))


def _float(payload: dict, name: str, default: float) -> float:
    return float(payload.get(name, default))


def _int(payload: dict, name: str, default: int) -> int:
    return int(payload.get(name, default))


def _motor_id(value: object) -> int:
    if isinstance(value, str) and value in MOTOR_NAMES:
        return MOTOR_NAMES[value]
    try:
        motor_id = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="motor must be one of right_arm, left_arm, torso, head, or 1..4") from exc
    try:
        validate_motor_id(motor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return motor_id


def _position(value: object) -> int:
    try:
        position = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="position must be an integer 0..3000") from exc
    if not MIN_POSITION <= position <= MAX_POSITION:
        raise HTTPException(status_code=400, detail=f"position must be between {MIN_POSITION} and {MAX_POSITION}")
    return position


def _tail(path: Path, line_count: int) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return [line.rstrip("\n") for line in deque(fh, maxlen=line_count)]


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "eilik", "status": "ok"}


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "service": "ok",
        "mode": "on-demand",
        "connected": controller.connected,
        "port": controller.port,
        "protocol": controller.protocol_variant,
    }


@app.get("/status")
def status() -> dict[str, object]:
    return health()


@app.get("/logs/recent")
def recent_logs(lines: int = 120) -> dict[str, object]:
    """Return recent bounded API/packet log lines for inspection."""
    line_count = max(1, min(int(lines), 1000))
    path = Path(LOG_PATH)
    rotated = sorted(path.parent.glob(path.name + ".*")) if path.parent.exists() else []
    return {
        "path": str(path),
        "max_bytes": int(os.getenv("EILIK_LOG_MAX_BYTES", "1000000")),
        "backup_count": int(os.getenv("EILIK_LOG_BACKUP_COUNT", "5")),
        "rotated_files": [str(p) for p in rotated],
        "line_count": line_count,
        "lines": _tail(path, line_count),
    }


@app.get("/diagnostic/snapshot")
def diagnostic_snapshot(include_display: bool = False) -> dict[str, object]:
    """Read live state back from Eilik for debugging."""
    return controller.diagnostic_snapshot(include_display=include_display)


@app.post("/diagnostic/motion")
def diagnostic_motion(payload: dict | None = None) -> dict[str, object]:
    """Move one motor, verify readback changed, then restore rest."""
    payload = payload or {}
    motor_id = int(payload.get("motor_id", 1))
    test_position = int(payload.get("test_position", 500))
    rest_position = int(payload.get("rest_position", 1500))
    return controller.diagnose_motion(
        motor_id=motor_id,
        test_position=test_position,
        rest_position=rest_position,
    )


@app.post("/wave")
def wave() -> dict[str, str]:
    controller.wave()
    return {"status": "ok", "action": "wave"}


@app.post("/nod")
def nod() -> dict[str, str]:
    controller.nod()
    return {"status": "ok", "action": "nod"}


@app.post("/shake_head")
def shake_head() -> dict[str, str]:
    controller.shake_head()
    return {"status": "ok", "action": "shake_head"}


@app.post("/look_left")
def look_left() -> dict[str, str]:
    controller.look_left()
    return {"status": "ok", "action": "look_left"}


@app.post("/look_right")
def look_right() -> dict[str, str]:
    controller.look_right()
    return {"status": "ok", "action": "look_right"}


@app.post("/left_arm_up")
def left_arm_up() -> dict[str, str]:
    controller.left_arm_up()
    return {"status": "ok", "action": "left_arm_up"}


@app.post("/left_arm_down")
def left_arm_down() -> dict[str, str]:
    controller.left_arm_down()
    return {"status": "ok", "action": "left_arm_down"}


@app.post("/right_arm_up")
def right_arm_up() -> dict[str, str]:
    controller.right_arm_up()
    return {"status": "ok", "action": "right_arm_up"}


@app.post("/right_arm_down")
def right_arm_down() -> dict[str, str]:
    controller.right_arm_down()
    return {"status": "ok", "action": "right_arm_down"}


@app.post("/reset")
def reset() -> dict[str, str]:
    controller.reset_pose()
    return {"status": "ok", "action": "reset"}


@app.get("/motions")
def list_motions() -> dict[str, object]:
    return {
        "count": len(MOTIONS),
        "motions": sorted(MOTIONS.keys()),
        "motors": MOTOR_NAMES,
        "position_range": {"min": MIN_POSITION, "rest": REST_POSITION, "max": MAX_POSITION},
    }


@app.post("/motion/{name}")
def run_motion(name: str) -> dict[str, str]:
    if name not in MOTIONS:
        raise HTTPException(status_code=404, detail=f"unknown motion: {name}")
    controller.run(f"motion.{name}", lambda robot: robot._run_motion(name))
    return {"status": "ok", "action": name}


@app.post("/servo/move")
def servo_move(payload: dict) -> dict[str, object]:
    """Move one motor directly.

    Body: {"motor": "right_arm" | 1, "position": 500}
    """
    motor_id = _motor_id(payload.get("motor", payload.get("motor_id")))
    position = _position(payload.get("position"))
    controller.move_motor(motor_id, position)
    return {"status": "ok", "motor_id": motor_id, "position": position}


@app.post("/display/release")
def display_release() -> dict[str, str]:
    """Release user-display mode so Eilik's firmware can resume its own face loop."""
    controller.release_display_lock()
    return {"status": "ok", "action": "display_release"}


@app.post("/display/idle")
def display_idle() -> dict[str, str]:
    """Restore the known calm idle face."""
    ok = controller.restore_idle_face()
    return {"status": "ok" if ok else "error", "action": "display_idle"}


@app.post("/display/image")
def display_image(payload: dict) -> dict[str, str]:
    """Push a PNG (base64-encoded) to Eilik's screen.

    Body: {"png_b64": "...", "invert": false, "threshold": 128, "hold_seconds": 2.0, "auto_idle": false}
    """
    import base64
    from pathlib import Path
    png_b64 = payload.get("png_b64")
    if not png_b64:
        return {"status": "error", "message": "png_b64 required"}
    invert = bool(payload.get("invert", False))
    threshold = int(payload.get("threshold", 128))
    hold_seconds = float(payload.get("hold_seconds", 2.0))
    auto_idle = bool(payload.get("auto_idle", False))
    data = base64.b64decode(png_b64)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(data)
        tmp = Path(f.name)
    try:
        ok = controller.display_image(tmp, invert=invert, threshold=threshold,
                                       hold_seconds=hold_seconds, auto_idle=auto_idle)
    finally:
        tmp.unlink(missing_ok=True)
    return {"status": "ok" if ok else "error", "acked": "true" if ok else "false"}


@app.post("/display/raw")
def display_raw(payload: dict) -> dict[str, str]:
    """Push a raw 1024-byte framebuffer to Eilik's screen.

    Body: {"framebuffer_hex": "00ff..."} (2048 hex chars)
    """
    hex_str = payload.get("framebuffer_hex")
    if not hex_str or len(hex_str) != 2048:
        return {"status": "error", "message": "framebuffer_hex must be 2048 hex chars"}
    data = bytes.fromhex(hex_str)
    ok = controller.write_display(data)
    return {"status": "ok" if ok else "error", "acked": "true" if ok else "false"}


@app.post("/display/text")
def display_text(payload: dict) -> dict[str, str]:
    """Render text to a 128x64 framebuffer and push it. Uses PIL.

    Body: {"text": "Hello", "font_size": 16, "hold_seconds": 2.0, "auto_idle": false}
    """
    text = payload.get("text", "")
    font_size = int(payload.get("font_size", 16))
    invert = bool(payload.get("invert", True))
    hold_seconds = float(payload.get("hold_seconds", 2.0))
    auto_idle = bool(payload.get("auto_idle", False))
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return {"status": "error", "message": "Pillow not installed"}
    img = Image.new("L", (128, 64), 255 if invert else 0)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except (OSError, IOError):
        font = ImageFont.load_default()
    draw.text((2, 2), text, fill=(0 if invert else 255), font=font)
    import io as _io
    buf = _io.BytesIO()
    img.save(buf, "PNG")
    from pathlib import Path
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(buf.getvalue())
        tmp = Path(f.name)
    try:
        ok = controller.display_image(tmp, invert=False,
                                       hold_seconds=hold_seconds, auto_idle=auto_idle)
    finally:
        tmp.unlink(missing_ok=True)
    return {"status": "ok" if ok else "error", "acked": "true" if ok else "false", "text": text}


def _display_text_arms(payload: dict) -> dict[str, object]:
    """Show text while moving both arms up/down in one on-demand session."""
    text = str(payload.get("text", "Hello Alice!!"))
    duration = max(0.1, min(_float(payload, "duration_seconds", 5.0), 30.0))
    font_size = _int(payload, "font_size", 16)
    invert = _bool(payload, "invert", True)
    threshold = _int(payload, "threshold", 128)
    cleanup = str(payload.get("cleanup", "disconnect_only"))
    pause = max(0.0, min(_float(payload, "step_pause_seconds", 0.05), 1.0))
    allowed_cleanup = {"disconnect_only", "arms_down", "arms_rest", "reset_pose", "idle_face"}
    if cleanup not in allowed_cleanup:
        raise HTTPException(status_code=400, detail=f"cleanup must be one of {sorted(allowed_cleanup)}")

    def run(robot: EilikController) -> dict[str, object]:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as exc:
            raise HTTPException(status_code=500, detail="Pillow not installed") from exc

        img = Image.new("L", (128, 64), 255 if invert else 0)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = max(0, (128 - tw) // 2 - bbox[0])
        y = max(0, (64 - th) // 2 - bbox[1])
        draw.text((x, y), text, fill=(0 if invert else 255), font=font)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = Path(f.name)
            img.save(f, "PNG")

        started = time.monotonic()
        arm_steps = 0
        try:
            robot.logger.info(
                "ROUTINE_DISPLAY_TEXT_ARMS_START text=%r duration=%s cleanup=%s",
                text,
                duration,
                cleanup,
            )
            ok = robot.display_image(
                tmp,
                invert=False,
                threshold=threshold,
                hold_seconds=0,
                auto_idle=False,
            )
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                robot.move_motor(MOTOR_RIGHT_ARM, 500)
                robot.move_motor(MOTOR_LEFT_ARM, 2500)
                arm_steps += 2
                if pause:
                    time.sleep(pause)
                if time.monotonic() >= deadline:
                    break
                robot.move_motor(MOTOR_RIGHT_ARM, 2500)
                robot.move_motor(MOTOR_LEFT_ARM, 500)
                arm_steps += 2
                if pause:
                    time.sleep(pause)

            if cleanup == "arms_down":
                robot.move_motor(MOTOR_RIGHT_ARM, 2500)
                robot.move_motor(MOTOR_LEFT_ARM, 500)
            elif cleanup == "arms_rest":
                robot.move_motor(MOTOR_RIGHT_ARM, REST_POSITION)
                robot.move_motor(MOTOR_LEFT_ARM, REST_POSITION)
            elif cleanup == "reset_pose":
                robot.reset_pose()
            elif cleanup == "idle_face":
                robot.restore_idle_face(auto_rotate=True)

            elapsed = round(time.monotonic() - started, 3)
            robot.logger.info(
                "ROUTINE_DISPLAY_TEXT_ARMS_END text=%r ok=%s arm_steps=%s elapsed=%s cleanup=%s",
                text,
                ok,
                arm_steps,
                elapsed,
                cleanup,
            )
            return {
                "status": "ok" if ok else "error",
                "text": text,
                "duration_seconds": duration,
                "elapsed_seconds": elapsed,
                "arm_steps": arm_steps,
                "cleanup": cleanup,
            }
        finally:
            tmp.unlink(missing_ok=True)

    return controller.run("routine.display_text_arms", run)


@app.post("/routine/display_text_arms")
def routine_display_text_arms(payload: dict) -> dict[str, object]:
    """Show text while moving both arms up/down in one on-demand serial session.

    Body: {
      "text": "Hello Alice!!",
      "duration_seconds": 5,
      "cleanup": "disconnect_only" | "arms_down" | "arms_rest" | "reset_pose" | "idle_face"
    }
    """
    return _display_text_arms(payload)


@app.post("/test/display-text-arms")
def test_display_text_arms(payload: dict) -> dict[str, object]:
    """Backward-friendly alias for curl tests."""
    return _display_text_arms(payload)


@app.post("/action")
def action(payload: dict):
    """Run a high-level action from the actions library.

    Body: {"name": "message", "hold_seconds": null, "auto_idle": true}
    """
    name = payload.get("name")
    if not name:
        return {"status": "error", "message": "name required"}
    from .actions import get_action
    try:
        spec = get_action(name)
    except ValueError:
        return {"status": "error", "message": f"unknown action: {name}"}
    hold_seconds = payload.get("hold_seconds")  # None => use action default
    auto_idle = bool(payload.get("auto_idle", True))
    ok = controller.action(name, hold_seconds=hold_seconds, auto_idle=auto_idle)
    return JSONResponse(content={"status": "ok" if ok else "error", "action": name, "spec": dict(spec)})


@app.get("/actions")
def list_actions() -> dict[str, object]:
    """List all known high-level actions."""
    from .actions import ACTIONS
    return {"count": len(ACTIONS), "actions": {k: v for k, v in ACTIONS.items()}}


@app.post("/ambient/clock")
def ambient_clock(payload: dict) -> dict[str, object]:
    """Show a clock face.

    Body: {"hour": null, "minute": null, "hold_seconds": 3.0, "auto_idle": true}
    """
    hour = payload.get("hour")
    minute = payload.get("minute")
    hold = float(payload.get("hold_seconds", 3.0))
    auto_idle = bool(payload.get("auto_idle", True))
    from datetime import datetime
    if hour is None or minute is None:
        now = datetime.now()
        hour = hour or now.hour
        minute = minute or now.minute
    ok = controller.show_clock(hour=int(hour), minute=int(minute),
                                hold_seconds=hold, auto_idle=auto_idle)
    return {"status": "ok" if ok else "error", "hour": hour, "minute": minute}


@app.post("/ambient/streak")
def ambient_streak(payload: dict) -> dict[str, object]:
    """Show a habit-streak face.

    Body: {"days": 7, "hold_seconds": 3.0, "auto_idle": true}
    """
    days = int(payload.get("days", 0))
    hold = float(payload.get("hold_seconds", 3.0))
    auto_idle = bool(payload.get("auto_idle", True))
    ok = controller.show_streak(days, hold_seconds=hold, auto_idle=auto_idle)
    return {"status": "ok" if ok else "error", "days": days}


@app.post("/ambient/weather")
def ambient_weather(payload: dict) -> dict[str, object]:
    """Show a weather face.

    Body: {"condition": "sun", "hold_seconds": 3.0, "auto_idle": true}
    """
    condition = str(payload.get("condition", ""))
    hold = float(payload.get("hold_seconds", 3.0))
    auto_idle = bool(payload.get("auto_idle", True))
    ok = controller.show_weather(condition, hold_seconds=hold, auto_idle=auto_idle)
    return {"status": "ok" if ok else "error", "condition": condition}


@app.post("/ambient/pr")
def ambient_pr(payload: dict) -> dict[str, object]:
    """Show a PR notification face.

    Body: {"pr_number": 42, "author": "jeff", "hold_seconds": 3.0, "auto_idle": true}
    """
    pr = int(payload.get("pr_number", 0))
    author = payload.get("author")
    hold = float(payload.get("hold_seconds", 3.0))
    auto_idle = bool(payload.get("auto_idle", True))
    ok = controller.show_pr(pr, author=author, hold_seconds=hold, auto_idle=auto_idle)
    return {"status": "ok" if ok else "error", "pr": pr, "author": author}


@app.post("/ambient/calendar")
def ambient_calendar(payload: dict) -> dict[str, object]:
    """Show a calendar-nudge face.

    Body: {"minutes_until": 5, "meeting_title": "Catchup", "hold_seconds": 3.0, "auto_idle": true}
    """
    minutes = int(payload.get("minutes_until", 5))
    title = payload.get("meeting_title")
    hold = float(payload.get("hold_seconds", 3.0))
    auto_idle = bool(payload.get("auto_idle", True))
    ok = controller.show_calendar_nudge(minutes, meeting_title=title,
                                         hold_seconds=hold, auto_idle=auto_idle)
    return {"status": "ok" if ok else "error", "minutes": minutes}


@app.post("/ambient/energy")
def ambient_energy(payload: dict) -> dict[str, object]:
    """Show an energy-meter face.

    Body: {"soi_percent": 87, "hold_seconds": 3.0, "auto_idle": true}
    """
    pct = int(payload.get("soi_percent", 0))
    hold = float(payload.get("hold_seconds", 3.0))
    auto_idle = bool(payload.get("auto_idle", True))
    ok = controller.show_energy_meter(pct, hold_seconds=hold, auto_idle=auto_idle)
    return {"status": "ok" if ok else "error", "soi_percent": pct}


@app.post("/ambient/crypto")
def ambient_crypto(payload: dict) -> dict[str, object]:
    """Show a crypto ticker face.

    Body: {"ticker": "BTC", "change_pct": 5.2, "hold_seconds": 3.0, "auto_idle": true}
    """
    ticker = str(payload.get("ticker", "?"))
    pct = float(payload.get("change_pct", 0))
    hold = float(payload.get("hold_seconds", 3.0))
    auto_idle = bool(payload.get("auto_idle", True))
    ok = controller.show_crypto_ticker(ticker, pct, hold_seconds=hold, auto_idle=auto_idle)
    return {"status": "ok" if ok else "error", "ticker": ticker, "change_pct": pct}


@app.post("/ambient/tts")
def ambient_tts(payload: dict) -> dict[str, object]:
    """Show a TTS-style longer text face.

    Body: {"text": "hello world", "hold_seconds": 4.0, "auto_idle": true}
    """
    text = str(payload.get("text", ""))
    hold = float(payload.get("hold_seconds", 4.0))
    auto_idle = bool(payload.get("auto_idle", True))
    ok = controller.show_tts_text(text, hold_seconds=hold, auto_idle=auto_idle)
    return {"status": "ok" if ok else "error", "text": text}


@app.post("/ambient/mood")
def ambient_mood(payload: dict) -> dict[str, object]:
    """Show a mood face.

    Body: {"mood": "happy", "hold_seconds": 3.0, "auto_idle": true}
    """
    mood = str(payload.get("mood", ""))
    hold = float(payload.get("hold_seconds", 3.0))
    auto_idle = bool(payload.get("auto_idle", True))
    ok = controller.show_mood(mood, hold_seconds=hold, auto_idle=auto_idle)
    return {"status": "ok" if ok else "error", "mood": mood}


# Compound actions / event bridges
_MORNING_PAYLOAD = {}

@app.post("/morning")
def morning_routine() -> dict[str, str]:
    controller.morning_routine()
    return {"status": "ok"}


@app.post("/welcome")
def welcome_back() -> dict[str, str]:
    controller.welcome_back()
    return {"status": "ok"}


@app.post("/event/cron_done")
def event_cron_done(payload: dict) -> dict[str, str]:
    name = str(payload.get("name", ""))
    controller.cron_tick_done(name)
    return {"status": "ok", "name": name}


@app.post("/event/error")
def event_error(payload: dict) -> dict[str, str]:
    msg = str(payload.get("message", ""))
    controller.error_flash(msg)
    return {"status": "ok", "message": msg}


@app.post("/event/subagent_returned")
def event_subagent_done(payload: dict) -> dict[str, str]:
    name = str(payload.get("name", ""))
    controller.subagent_returned(name)
    return {"status": "ok", "name": name}


@app.post("/event/email")
def event_email(payload: dict) -> dict[str, str]:
    sender = str(payload.get("sender", ""))
    controller.email_arrived(sender)
    return {"status": "ok", "sender": sender}


@app.post("/event/quinn")
def event_quinn() -> dict[str, str]:
    controller.quinn_comms()
    return {"status": "ok"}


@app.post("/event/crypto_pumped")
def event_crypto(payload: dict) -> JSONResponse:
    ticker = str(payload.get("ticker", "BTC"))
    pct = float(payload.get("pct", 0))
    controller.crypto_pumped(ticker, pct)
    return JSONResponse(content={"status": "ok", "ticker": ticker, "pct": pct})


@app.post("/event/pr_alert")
def event_pr_alert(payload: dict) -> dict[str, str]:
    """A new PR opened — heart hands + PR! face for 10s."""
    pr_number = int(payload.get("pr_number", 0))
    author = str(payload.get("author", ""))
    controller.pr_alert(pr_number, author)
    return {"status": "ok", "pr_number": str(pr_number), "author": author}


@app.post("/event/welcome_back")
def event_welcome_back() -> dict[str, str]:
    """Jeff opened chat after >2h silence."""
    controller.welcome_back()
    return {"status": "ok"}


@app.post("/celebrate")
def celebrate(payload: dict) -> dict[str, str]:
    """Celebrate a win: wiggle + heart hands + bright face for 10s.

    Body: {"label": "PR#104"} (optional text shown with the celebration).
    """
    label = str(payload.get("label", ""))
    controller.celebrate(label)
    return {"status": "ok", "label": label}


@app.post("/apology")
def apology(payload: dict) -> dict[str, str]:
    """Apologize for a failure: shake head + shrug + sad face for 10s.

    Body: {"reason": "timeout"} (optional reason shown with the apology).
    """
    reason = str(payload.get("reason", ""))
    controller.apology(reason)
    return {"status": "ok", "reason": reason}


@app.post("/choreo")
def choreography(payload: dict) -> dict[str, str]:
    """Run a sequence of actions. Body: {"steps": [{"action": "hi_jeff"}, {"wait": 1}]}"""
    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        return {"status": "error", "message": "steps must be a list"}
    controller.choreography(steps)
    return {"status": "ok", "step_count": str(len(steps))}


@app.get("/servo/angles")
def servo_angles() -> dict[str, object]:
    angles = controller.read_servo_angles()
    return {"angles": angles, "count": len(angles)}
