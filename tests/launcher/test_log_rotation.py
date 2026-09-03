from __future__ import annotations

from pathlib import Path

from bootstrap.main import _setup_logging
from bootstrap.paths import AppPaths


def _paths(tmp_path: Path) -> AppPaths:
    root = tmp_path / "root"
    state_dir = root / "state"
    return AppPaths(
        root=root,
        python_dir=root / "python",
        app_dir=root / "app",
        state_dir=state_dir,
        logs_dir=root / "logs",
        marker_path=state_dir / "bootstrap_marker.json",
        lock_path=state_dir / "bootstrap.lock",
        browser_channel_path=state_dir / "browser_channel.json",
        data_dir=root / "data",
    )


def test_bootstrap_log_rotates_past_the_size_threshold(tmp_path):
    paths = _paths(tmp_path)
    logger = _setup_logging(paths)
    try:
        big_message = "x" * 2000
        for _ in range(2000):  # well past a 1MB rotation threshold
            logger.info(big_message)

        rotated = list(paths.logs_dir.glob("bootstrap.log.*"))
        assert rotated, "expected at least one rotated backup file"
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


def test_bootstrap_log_redacts_urls_from_messages(tmp_path):
    paths = _paths(tmp_path)
    logger = _setup_logging(paths)
    try:
        logger.info("fetched https://scoutingevent.com/mobile/secret-attendee-id-12345")

        log_text = (paths.logs_dir / "bootstrap.log").read_text(encoding="utf-8")
        assert "scoutingevent.com" not in log_text
        assert "[redacted-url]" in log_text
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
