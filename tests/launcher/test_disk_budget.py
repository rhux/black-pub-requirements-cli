from __future__ import annotations

from pathlib import Path

import pytest
from bootstrap.disk_budget import preflight_disk_space


class _Usage:
    def __init__(self, total: int, used: int, free: int) -> None:
        self.total, self.used, self.free = total, used, free


def test_active_and_rollback_reserve_is_enforced(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("bootstrap.disk_budget.shutil.disk_usage", lambda p: _Usage(0, 0, 100))

    with pytest.raises(RuntimeError, match="free=100.*required=500|required=500.*free=100"):
        preflight_disk_space(tmp_path, required_bytes=500)

    monkeypatch.setattr("bootstrap.disk_budget.shutil.disk_usage", lambda p: _Usage(0, 0, 1000))
    preflight_disk_space(tmp_path, required_bytes=500)  # must not raise
