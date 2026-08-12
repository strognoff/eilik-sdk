"""FastAPI service for Eilik control."""

from __future__ import annotations

import os
import tempfile

from fastapi import FastAPI

from .controller import EilikController

controller = EilikController(
    port=os.getenv("EILIK_PORT") or None,
    log_path=os.getenv("EILIK_LOG_PATH", "logs/eilik.log"),
)
app = FastAPI(title="Eilik Controller Service", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    controller.connect()


@app.on_event("shutdown")
def shutdown() -> None:
    controller.disconnect()


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "eilik", "status": "ok"}


@app.get("/health")
def health() -> dict[str, object]:
    return {"connected": controller.connected, "port": controller.port, "protocol": controller.protocol_variant}


@app.get("/status")
def status() -> dict[str, object]:
    return health()


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


@app.post("/display/image")
def display_image(payload: dict) -> dict[str, str]:
    """Push a PNG (base64-encoded) to Eilik's screen.

    Body: {"png_b64": "...", "invert": false, "threshold": 128}
    """
    import base64
    from pathlib import Path
    png_b64 = payload.get("png_b64")
    if not png_b64:
        return {"status": "error", "message": "png_b64 required"}
    invert = bool(payload.get("invert", False))
    threshold = int(payload.get("threshold", 128))
    data = base64.b64decode(png_b64)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(data)
        tmp = Path(f.name)
    try:
        ok = controller.display_image(tmp, invert=invert, threshold=threshold)
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

    Body: {"text": "Hello", "font_size": 16, "auto_reset": true}
    """
    text = payload.get("text", "")
    font_size = int(payload.get("font_size", 16))
    invert = bool(payload.get("invert", True))
    auto_reset = bool(payload.get("auto_reset", True))
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
        ok = controller.display_image(tmp, invert=False, auto_reset=auto_reset)
    finally:
        tmp.unlink(missing_ok=True)
    return {"status": "ok" if ok else "error", "acked": "true" if ok else "false", "text": text}


@app.get("/servo/angles")
def servo_angles() -> dict[str, object]:
    angles = controller.read_servo_angles()
    return {"angles": angles, "count": len(angles)}
