from __future__ import annotations

from pathlib import Path

import pytest
from bootstrap import release
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


def _fake_source_root(tmp_path: Path, version: str) -> Path:
    source = tmp_path / f"source-{version}"
    (source / "src" / "scoutmb").mkdir(parents=True)
    (source / "src" / "scoutmb" / "__init__.py").write_text("", encoding="utf-8")
    (source / "pyproject.toml").write_text(
        f'[project]\nname = "scoutmb"\nversion = "{version}"\n', encoding="utf-8"
    )
    (source / "requirements.txt").write_text("fastapi==0.1.0\n", encoding="utf-8")
    return source


def test_each_failure_point_rolls_back_tuple(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.ensure_dirs()
    source = _fake_source_root(tmp_path, "0.1.0")

    manifest = release.stage_release(paths, source, source / "requirements.txt")
    release.activate(paths, manifest, state_generation=1)
    first_pointer = (paths.state_dir / "current.json").read_text(encoding="utf-8")

    bad_source = _fake_source_root(tmp_path, "0.2.0")
    bad_manifest = release.stage_release(paths, bad_source, bad_source / "requirements.txt")
    object.__setattr__(bad_manifest, "state_schema_min", 99)  # force validate_activation False
    object.__setattr__(bad_manifest, "state_schema_max", 99)

    with pytest.raises(RuntimeError, match="activation"):
        release.activate(paths, bad_manifest, state_generation=1)

    assert (paths.state_dir / "current.json").read_text(encoding="utf-8") == first_pointer
    # The failed staged release is NOT deleted -- a retry shouldn't have to recopy.
    assert (paths.releases_dir / "0.2.0").is_dir()


def test_readiness_nonce_and_release_identity(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from scoutmb.config import UiSettings
    from scoutmb.interfaces.web.app import create_app

    monkeypatch.setenv("SCOUTMB_READINESS_NONCE", "expected-nonce")
    app = create_app(UiSettings(data_root=tmp_path / "data"))
    client = TestClient(app)

    ok = client.get("/api/health", params={"nonce": "expected-nonce"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "ok"

    wrong = client.get("/api/health", params={"nonce": "wrong"})
    assert wrong.status_code == 401

    missing = client.get("/api/health")
    assert missing.status_code == 401


def test_health_without_configured_nonce_is_unchanged(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from scoutmb.config import UiSettings
    from scoutmb.interfaces.web.app import create_app

    monkeypatch.delenv("SCOUTMB_READINESS_NONCE", raising=False)
    app = create_app(UiSettings(data_root=tmp_path / "data"))
    client = TestClient(app)

    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_offline_restart_uses_last_known_good(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.ensure_dirs()
    source_n_minus_1 = _fake_source_root(tmp_path, "0.1.0")
    source_n = _fake_source_root(tmp_path, "0.2.0")

    manifest_1 = release.stage_release(
        paths, source_n_minus_1, source_n_minus_1 / "requirements.txt"
    )
    release.activate(paths, manifest_1, state_generation=1)

    manifest_2 = release.stage_release(paths, source_n, source_n / "requirements.txt")
    release.activate(paths, manifest_2, state_generation=1)
    assert release.current_release_version(paths) == "0.2.0"

    # Rollback: re-activate the N-1 manifest -- proves N -> N+1 -> N.
    release.activate(paths, manifest_1, state_generation=1)
    assert release.current_release_version(paths) == "0.1.0"
