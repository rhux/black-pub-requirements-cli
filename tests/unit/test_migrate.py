from __future__ import annotations

from bootstrap.migrate import MIGRATION_MARKER, migrate_legacy_data


def _legacy(root):
    app = root / "app"
    data = root / "data"
    (app / "pdf-uploads").mkdir(parents=True)
    (app / "runs" / "2026-07-19_2139").mkdir(parents=True)
    (app / "scouts.csv").write_text("Attendee Name,QR Code Contents\n", encoding="utf-8")
    (app / "runs" / "2026-07-19_2139" / "summary.json").write_text("{}", encoding="utf-8")
    return app, data


def test_copies_all(tmp_path):
    app, data = _legacy(tmp_path)
    migrate_legacy_data(app, data)
    assert (data / "scouts.csv").is_file() and (
        data / "runs" / "2026-07-19_2139" / "summary.json"
    ).is_file()


def test_originals_retained(tmp_path):
    app, data = _legacy(tmp_path)
    migrate_legacy_data(app, data)
    assert (app / "scouts.csv").is_file()


def test_idempotent(tmp_path):
    app, data = _legacy(tmp_path)
    migrate_legacy_data(app, data)
    (data / "scouts.csv").write_text("edited", encoding="utf-8")
    migrate_legacy_data(app, data)
    assert (data / "scouts.csv").read_text(encoding="utf-8") == "edited"
    assert (data / MIGRATION_MARKER).is_file()


def test_collision_writes_alongside(tmp_path):
    app, data = _legacy(tmp_path)
    data.mkdir(parents=True, exist_ok=True)
    (data / "scouts.csv").write_text("pre", encoding="utf-8")
    migrate_legacy_data(app, data)
    assert (data / "scouts.csv").read_text(encoding="utf-8") == "pre"
    assert (data / "scouts.csv.legacy").read_text(encoding="utf-8").startswith("Attendee Name")


def test_double_collision_never_deletes_existing_legacy(tmp_path):
    """A second migration (marker removed) must not delete the first .legacy."""
    app, data = _legacy(tmp_path)
    data.mkdir(parents=True, exist_ok=True)
    (data / "scouts.csv").write_text("pre", encoding="utf-8")
    migrate_legacy_data(app, data)  # -> scouts.csv.legacy
    (data / MIGRATION_MARKER).unlink()  # simulate a re-run
    migrate_legacy_data(app, data)  # -> scouts.csv.legacy-2
    assert (data / "scouts.csv.legacy").exists()  # first preserved copy survives
    assert (data / "scouts.csv.legacy-2").exists()  # second collision preserved separately


def test_no_legacy_is_noop(tmp_path):
    data = tmp_path / "data"
    migrate_legacy_data(tmp_path / "app", data)
    assert not data.exists() or not any(data.iterdir())


def test_copies_are_hash_verified_and_recorded(tmp_path):
    import hashlib
    import json

    app, data = _legacy(tmp_path)
    report = migrate_legacy_data(app, data)
    assert report["verification"] == "sha256"
    src = (app / "scouts.csv").read_bytes()
    dst = (data / "scouts.csv").read_bytes()
    assert hashlib.sha256(src).hexdigest() == hashlib.sha256(dst).hexdigest()
    assert json.loads((data / MIGRATION_MARKER).read_text())["verification"] == "sha256"


def test_old_root_gets_an_explanatory_marker(tmp_path):
    app, data = _legacy(tmp_path)
    migrate_legacy_data(app, data)
    assert (app / "MOVED-README.txt").is_file()


def test_launcher_exports_data_dir_env(monkeypatch, tmp_path):
    """_launch_app must put SCOUTMB_DATA_DIR in the child env so the app resolves data/."""
    # bootstrap.main -> bootstrap.webview2 -> `import winreg`, which only exists on Windows.
    # Run this on the Windows target; skip elsewhere (the winreg fix that lets bootstrap
    # import cross-platform is Slice 4).
    import pytest

    pytest.importorskip("winreg")
    monkeypatch.setenv("SCOUTMB_BOOTSTRAP_ROOT", str(tmp_path))
    import bootstrap.main as bmain

    captured = {}

    class _Popen:
        def __init__(self, *a, env=None, **k):
            captured["env"] = env or {}

    monkeypatch.setattr(bmain.subprocess, "Popen", _Popen)
    monkeypatch.setattr(bmain.time, "sleep", lambda *_: None)
    paths = bmain.get_paths()
    bmain._launch_app(paths, channel=None)
    assert captured["env"].get("SCOUTMB_DATA_DIR") == str(paths.data_dir)
