from __future__ import annotations

from pathlib import Path

from scoutmb.config import UiSettings


def test_resolution_is_platform_and_code_location_independent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SCOUTMB_DATA_DIR", raising=False)
    other_cwd = tmp_path / "somewhere-else"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    settings = UiSettings.resolve()

    # Never inside the source tree, and stable across two calls from different cwds.
    assert "src" not in settings.data_root.parts
    assert "scoutmb" not in [p for p in settings.data_root.parts if p != "ScoutingMeritBadges"]
    second_cwd = tmp_path / "elsewhere"
    second_cwd.mkdir()
    monkeypatch.chdir(second_cwd)
    assert UiSettings.resolve().data_root == settings.data_root
