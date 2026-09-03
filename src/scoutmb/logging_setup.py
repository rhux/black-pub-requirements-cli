"""Structured, rotating, redacted logging for src/scoutmb (D5) -- mirrors
bootstrap/main.py::_setup_logging's rotation + redaction exactly, for the same reason: QR URLs
and attendee IDs act as bearer access tokens for real scouts' data (CLAUDE.md's privacy notes).

User-facing progress output stays as print() (this task does not touch those sites); this
logger is for diagnostic-only messages -- unexpected errors, warnings -- that belong in a log
file rather than the console.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path

_URL_PATTERN = re.compile(r"https?://\S+")


def _redact_sensitive_values(record: logging.LogRecord) -> bool:
    record.msg = _URL_PATTERN.sub("[redacted-url]", str(record.msg))
    return True


def configure_logging(data_root: Path) -> logging.Logger:
    logger = logging.getLogger("scoutmb")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logs_dir = data_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            logs_dir / "scoutmb.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        handler.addFilter(_redact_sensitive_values)
        logger.addHandler(handler)
    return logger
