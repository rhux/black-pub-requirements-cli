from __future__ import annotations

from pathlib import Path

from scoutmb.config import UiSettings


def test_sizes_and_explicit_deletion_contract(tmp_path: Path) -> None:
    settings = UiSettings(data_root=tmp_path / "data")
    settings.ensure_dirs()
    settings.scouts_csv.write_bytes(b"x" * 100)
    (settings.runs_dir / "run-1").mkdir()
    (settings.runs_dir / "run-1" / "summary.json").write_bytes(b"y" * 250)

    sizes = settings.category_sizes()
    assert sizes == {"scouts_csv": 100, "pdf_uploads": 0, "runs": 250}

    settings.delete_category("runs")
    assert settings.runs_dir.is_dir()
    assert list(settings.runs_dir.iterdir()) == []

    settings.delete_category("runs")  # already empty -- must not raise
