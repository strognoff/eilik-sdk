"""Logging helpers for serial packet traces."""

from __future__ import annotations

import logging
from pathlib import Path

DEFAULT_LOG_PATH = Path("logs/eilik.log")


def setup_logger(log_path: str | Path = DEFAULT_LOG_PATH) -> logging.Logger:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("eilik")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    resolved = str(path.resolve())
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == resolved:
            return logger

    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    return logger


def hex_bytes(data: bytes) -> str:
    return data.hex(" ")
