from __future__ import annotations

from pathlib import Path

from bootstrap import python_env
from bootstrap import release as release_module
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


def test_patch_pth_file_points_at_active_release_dir(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.ensure_dirs()
    source = _fake_source_root(tmp_path, "0.1.0")
    manifest = release_module.stage_release(paths, source, source / "requirements.txt")
    release_module.activate(paths, manifest, state_generation=1)

    pth_path = paths.python_dir / python_env.PTH_FILENAME
    pth_path.write_text("#import site\n", encoding="utf-8")

    python_env._patch_pth_file(paths, log=None)

    text = pth_path.read_text(encoding="utf-8")
    expected = str(release_module.active_app_dir(paths))
    assert expected in text
    # Proves this is actually exercising the versioned release dir, not the
    # static, now-unpopulated app_dir.
    assert str(paths.app_dir) not in text
