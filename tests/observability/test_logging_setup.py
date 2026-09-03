from __future__ import annotations

from pathlib import Path

from scoutmb.logging_setup import configure_logging


def test_scoutmb_log_rotates_past_the_size_threshold(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path)
    try:
        big_message = "x" * 2000
        for _ in range(2000):
            logger.info(big_message)

        rotated = list((tmp_path / "logs").glob("scoutmb.log.*"))
        assert rotated, "expected at least one rotated backup file"
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


def test_scoutmb_log_redacts_urls_from_messages(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path)
    try:
        logger.info("fetched https://scoutingevent.com/mobile/secret-attendee-id-12345")

        log_text = (tmp_path / "logs" / "scoutmb.log").read_text(encoding="utf-8")
        assert "scoutingevent.com" not in log_text
        assert "[redacted-url]" in log_text
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
