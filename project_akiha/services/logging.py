"""Logging setup for Project Akiha."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(
    log_dir: Path,
    level: int = logging.INFO,
) -> Path:
    """Configure rotating file logs and return the active log path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    logger = logging.getLogger("project_akiha")
    logger.setLevel(level)
    logger.propagate = False

    if not _has_handler_for_path(logger, log_path):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)

    return log_path


def _has_handler_for_path(logger: logging.Logger, log_path: Path) -> bool:
    return any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename) == log_path
        for handler in logger.handlers
    )
