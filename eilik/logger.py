"""Logging helpers for serial packet traces."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

DEFAULT_LOG_PATH = Path("logs/eilik.log")
DEFAULT_MAX_BYTES = 1_000_000
DEFAULT_BACKUP_COUNT = 5


def setup_logger(
    log_path: str | Path = DEFAULT_LOG_PATH,
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> logging.Logger:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    max_bytes = max_bytes if max_bytes is not None else int(
        os.getenv("EILIK_LOG_MAX_BYTES", str(DEFAULT_MAX_BYTES))
    )
    backup_count = backup_count if backup_count is not None else int(
        os.getenv("EILIK_LOG_BACKUP_COUNT", str(DEFAULT_BACKUP_COUNT))
    )

    logger = logging.getLogger("eilik")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    resolved = str(path.resolve())
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == resolved:
            return logger

    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    return logger


def hex_bytes(data: bytes) -> str:
    return data.hex(" ")
