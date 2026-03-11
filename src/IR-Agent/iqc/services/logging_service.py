"""
Module: services/logging_service.py
Description: Central logging configuration for IQC Agent.
Author: IQC Team
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-30s | "
    "%(funcName)-28s | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_configured  = False


def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None:
    global _configured
    if _configured:
        return
    _configured = True

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / "iqc.log"

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root          = logging.getLogger()
    root.setLevel(numeric_level)
    formatter     = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    fh = logging.handlers.TimedRotatingFileHandler(
        str(log_file), when="midnight", backupCount=30, encoding="utf-8",
    )
    fh.setFormatter(formatter); fh.setLevel(numeric_level)
    root.addHandler(fh)

    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(formatter); ch.setLevel(numeric_level)
    root.addHandler(ch)

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


__all__ = ["setup_logging", "get_logger"]