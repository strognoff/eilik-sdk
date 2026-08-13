"""FastAPI service for Eilik control."""

from __future__ import annotations

import os
import tempfile

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .controller import EilikController

SERVICE_PORT = os.getenv("EILIK_PORT") or None
LOG_PATH = os.getenv("EILIK_LOG_PATH", "logs/eilik.log")
app = FastAPI(title="Eilik Controller Service", version="0.1.0")


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
            robot = EilikController(
                port=SERVICE_PORT,
                log_path=LOG_PATH,
                enable_keepalive=False,
            )
            try:
                robot.connect()
                return getattr(robot, name)(*args, **kwargs)
            finally:
                robot.disconnect()

        return call


controller = OnDemandController()


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


@app.post("/look_left")
def look_left() -> dict[str, str]:
    controller.look_left()
    return {"status": "ok", "action": "look_left"}


@app.post("/look_right")
def look_right() -> dict[str, str]:
    controller.look_right()
    return {"status": "ok", "action": "look_right"}


@app.post("/reset")
def reset() -> dict[str, str]:
    controller.reset_pose()
    return {"status": "ok", "action": "reset"}


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

    Body: {"png_b64": "...", "invert": false, "threshold": 128, "hold_seconds": 2.0, "auto_idle": true}
    """
    import base64
    from pathlib import Path
    png_b64 = payload.get("png_b64")
    if not png_b64:
        return {"status": "error", "message": "png_b64 required"}
    invert = bool(payload.get("invert", False))
    threshold = int(payload.get("threshold", 128))
    hold_seconds = float(payload.get("hold_seconds", 2.0))
    auto_idle = bool(payload.get("auto_idle", True))
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

    Body: {"text": "Hello", "font_size": 16, "hold_seconds": 2.0, "auto_idle": true}
    """
    text = payload.get("text", "")
    font_size = int(payload.get("font_size", 16))
    invert = bool(payload.get("invert", True))
    hold_seconds = float(payload.get("hold_seconds", 2.0))
    auto_idle = bool(payload.get("auto_idle", True))
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
