"""FastAPI service for Eilik control."""

from __future__ import annotations

import os

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
    return {"connected": controller.connected, "port": controller.port}


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
