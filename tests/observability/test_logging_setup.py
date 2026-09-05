from __future__ import annotations

import logging
from pathlib import Path

import pytest

from scoutmb.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def _reset_scoutmb_logger():
    """The "scoutmb" logger is a process-wide singleton, and configure_logging is
    idempotent-by-design (`if not logger.handlers`) for real production use -- so any other
    test in the same pytest process that exercises production code calling configure_logging
    (e.g. tests/integration/test_desktop_app.py's real app.main() dispatch) leaves a stale
    handler pointing at an already-cleaned-up directory, silently no-opping every later call in
    this file. Clear handlers before AND after each test here so this file never depends on
    what ran before it, and never leaks its own real filesystem state into whatever runs next."""
    logger = logging.getLogger("scoutmb")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    yield
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_scoutmb_log_rotates_past_the_size_threshold(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path)
    big_message = "x" * 2000
    for _ in range(2000):
        logger.info(big_message)

    rotated = list((tmp_path / "logs").glob("scoutmb.log.*"))
    assert rotated, "expected at least one rotated backup file"


def test_scoutmb_log_redacts_urls_from_messages(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path)
    logger.info("fetched https://scoutingevent.com/mobile/secret-attendee-id-12345")

    log_text = (tmp_path / "logs" / "scoutmb.log").read_text(encoding="utf-8")
    assert "scoutingevent.com" not in log_text
    assert "[redacted-url]" in log_text
