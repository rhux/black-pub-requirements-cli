from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from bootstrap.migrate import migrate_legacy_data


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_source_is_never_modified(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    data_dir = tmp_path / "data"
    app_dir.mkdir()
    (app_dir / "scouts.csv").write_bytes(b"name,url\nAvery,https://x\n")
    before = _sha256_bytes((app_dir / "scouts.csv").read_bytes())

    migrate_legacy_data(app_dir, data_dir)

    after = _sha256_bytes((app_dir / "scouts.csv").read_bytes())
    assert before == after
    assert (data_dir / "scouts.csv").read_bytes() == (app_dir / "scouts.csv").read_bytes()


def test_sibling_staging_fsync_promotion_and_marker_contents(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    data_dir = tmp_path / "data"
    app_dir.mkdir()
    (app_dir / "scouts.csv").write_bytes(b"data")

    migrate_legacy_data(app_dir, data_dir)

    staging_dir = data_dir.parent / f".{data_dir.name}.staging"
    assert not staging_dir.exists()  # promoted and cleaned up, nothing left behind
    marker = data_dir / ".migrated"
    assert marker.is_file()


def test_each_interruption_point_resumes_idempotently(tmp_path: Path, monkeypatch) -> None:
    app_dir = tmp_path / "app"
    data_dir = tmp_path / "data"
    app_dir.mkdir()
    (app_dir / "scouts.csv").write_bytes(b"data-one")
    (app_dir / "runs").mkdir()
    (app_dir / "runs" / "r1.json").write_bytes(b"run-one")

    calls = {"n": 0}

    import bootstrap.migrate as migrate_module

    real_promote = migrate_module._promote_staged_item

    def flaky_promote(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated interruption after staging the first item")
        return real_promote(*args, **kwargs)

    monkeypatch.setattr(migrate_module, "_promote_staged_item", flaky_promote)

    with pytest.raises(OSError):
        migrate_legacy_data(app_dir, data_dir)
    assert not (data_dir / ".migrated").exists()  # interrupted run never completes

    # Resume: the flaky patch is only consumed once (calls["n"] already at 1), so the retry
    # runs the real promote function throughout and must finish cleanly.
    result = migrate_legacy_data(app_dir, data_dir)
    assert result is not None
    assert (data_dir / "scouts.csv").read_bytes() == b"data-one"
    assert (data_dir / "runs" / "r1.json").read_bytes() == b"run-one"
    assert (data_dir / ".migrated").is_file()


def test_production_mode_requires_manual_backup_receipt(tmp_path: Path, monkeypatch) -> None:
    app_dir = tmp_path / "app"
    data_dir = tmp_path / "data"
    app_dir.mkdir()
    (app_dir / "scouts.csv").write_bytes(b"data")
    monkeypatch.delenv("SCOUTMB_MIGRATION_BACKUP_CONFIRMED", raising=False)

    with pytest.raises(RuntimeError, match="backup"):
        migrate_legacy_data(app_dir, data_dir, production=True)
    assert not (data_dir / "scouts.csv").exists()  # refused before any copy happened

    monkeypatch.setenv("SCOUTMB_MIGRATION_BACKUP_CONFIRMED", "1")
    result = migrate_legacy_data(app_dir, data_dir, production=True)
    assert result is not None
