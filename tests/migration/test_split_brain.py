from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bootstrap.migrate import migrate_legacy_data


def test_manifest_records_source_hashes(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    data_dir = tmp_path / "data"
    app_dir.mkdir()
    (app_dir / "scouts.csv").write_bytes(b"name,url\nAvery,https://x\n")
    (app_dir / "runs").mkdir()
    (app_dir / "runs" / "r1.json").write_bytes(b"{}")

    migrate_legacy_data(app_dir, data_dir)

    manifest = json.loads((data_dir / "migration_manifest.json").read_text(encoding="utf-8"))
    entries = {entry["path"]: entry for entry in manifest["files"]}
    assert entries["scouts.csv"]["sha256"] == hashlib.sha256(
        b"name,url\nAvery,https://x\n"
    ).hexdigest()
    assert entries["scouts.csv"]["size"] == len(b"name,url\nAvery,https://x\n")
    assert "runs/r1.json" in entries


def test_old_root_receives_explanatory_marker(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    data_dir = tmp_path / "data"
    app_dir.mkdir()
    (app_dir / "scouts.csv").write_bytes(b"data")

    migrate_legacy_data(app_dir, data_dir)

    marker_text = (app_dir / "MOVED-README.txt").read_text(encoding="utf-8")
    assert "copied" in marker_text.lower()
    assert "do not run" in marker_text.lower()
