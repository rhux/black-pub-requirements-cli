"""Typed matrix execution of the bootstrap characterization catalog (Task 21, final slice):
``bootstrap/paths.py``'s ``resolve_root``, ``bootstrap/marker.py``'s ``is_environment_valid``,
and ``bootstrap/source_sync.py``'s ``sync_app_source``/``_source_root``.

Every path used at runtime is built entirely under pytest's ``tmp_path`` -- no test in this
module ever touches the real user's actual application-data directory, writes outside
``tmp_path``, sleeps, or reaches a non-loopback host.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from tests.matrix.cases.bootstrap_cases import (
    BOOTSTRAP_MARKER_CASES,
    BOOTSTRAP_PATH_CASES,
    BOOTSTRAP_SYNC_CASES,
    BootstrapMarkerCase,
    BootstrapPathCase,
    BootstrapSyncCase,
)
from tests.matrix.pytest_support import assert_platform_domain_registry_valid, execution_params


# ==================================================================================================
# BOOT-PATH -- resolve_root's override-vs-default fallback.
# ==================================================================================================
@pytest.mark.parametrize(("case", "context_id"), execution_params(BOOTSTRAP_PATH_CASES))
def test_boot_path_execution(
    case: BootstrapPathCase, context_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del context_id
    from bootstrap.config import APP_NAME
    from bootstrap.paths import resolve_root

    localappdata_path = tmp_path / case.localappdata_leaf
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata_path))

    if case.override_leaf is not None:
        override_path = tmp_path / case.override_leaf
        monkeypatch.setenv("SCOUTMB_BOOTSTRAP_ROOT", str(override_path))
        expected = override_path
    else:
        monkeypatch.delenv("SCOUTMB_BOOTSTRAP_ROOT", raising=False)
        expected = localappdata_path / APP_NAME

    result = resolve_root()

    assert result == expected


# ==================================================================================================
# BOOT-MARK -- is_environment_valid's real sequential validation chain. bootstrap.marker.smoke_test
# is patched in every case; its own real subprocess/exe-existence logic is out of this catalog's
# scope (it is exercised by other suites), and patching it here isolates the marker-field
# comparisons under test as the only thing that can vary the outcome.
# ==================================================================================================
def _build_app_paths(root: Path) -> object:
    from bootstrap.paths import AppPaths

    state_dir = root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
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


@pytest.mark.parametrize(("case", "context_id"), execution_params(BOOTSTRAP_MARKER_CASES))
def test_boot_marker_execution(
    case: BootstrapMarkerCase, context_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del context_id
    from bootstrap import marker as marker_module
    from bootstrap.config import MARKER_SCHEMA_VERSION, PYTHON_VERSION

    paths = _build_app_paths(tmp_path / "app-root")

    requirements_path = tmp_path / "requirements.txt"
    requirements_bytes = b"fastapi==0.100.0\nuvicorn==0.23.0\nplaywright==1.40.0\n"
    requirements_path.write_bytes(requirements_bytes)
    real_hash = hashlib.sha256(requirements_bytes).hexdigest()

    if case.write_marker:
        if case.corrupt_marker_text is not None:
            paths.marker_path.write_text(case.corrupt_marker_text, encoding="utf-8")
        else:
            payload = {
                "schema_version": (
                    case.schema_version_override
                    if case.schema_version_override is not None
                    else MARKER_SCHEMA_VERSION
                ),
                "python_version": (
                    case.python_version_override
                    if case.python_version_override is not None
                    else PYTHON_VERSION
                ),
                "requirements_hash": (
                    case.requirements_hash_override
                    if case.requirements_hash_override is not None
                    else real_hash
                ),
                "browser_channel": "msedge",
                "completed_at_utc": "2026-01-01T00:00:00Z",
            }
            paths.marker_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # else: case.write_marker is False -- leave no marker file on disk at all.

    monkeypatch.setattr(marker_module, "smoke_test", lambda p, imports: case.smoke_test_result)

    result = marker_module.is_environment_valid(paths, requirements_path)

    assert result == case.expected_valid


# ==================================================================================================
# BOOT-SYNC -- sync_app_source's real _FILES/_DIRS allowlist copy and _source_root's
# frozen-vs-unfrozen resolution. Every synthetic source tree mirrors the REAL _FILES/_DIRS
# entries read from bootstrap/source_sync.py (imported here, in the runner, never guessed).
# ==================================================================================================
def _write_synthetic_source_tree(root: Path, files: tuple[str, ...], dirs: tuple[str, ...]) -> None:
    for relative in files:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"synthetic content: {relative}\n".encode())
    for relative in dirs:
        base = root / relative
        base.mkdir(parents=True, exist_ok=True)
        (base / "top-level.txt").write_bytes(b"synthetic dir file: top-level\n")
        (base / "nested").mkdir(parents=True, exist_ok=True)
        (base / "nested" / "leaf.txt").write_bytes(b"synthetic dir file: nested/leaf\n")


@pytest.mark.parametrize(("case", "context_id"), execution_params(BOOTSTRAP_SYNC_CASES))
def test_boot_sync_execution(
    case: BootstrapSyncCase, context_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del context_id
    from bootstrap import source_sync as source_sync_module
    from bootstrap.paths import AppPaths

    files = tuple(source_sync_module._FILES)
    dirs = tuple(source_sync_module._DIRS)

    dest_paths = AppPaths(
        root=tmp_path / "dest-root",
        python_dir=tmp_path / "dest-root" / "python",
        app_dir=tmp_path / "dest-root" / "app",
        state_dir=tmp_path / "dest-root" / "state",
        logs_dir=tmp_path / "dest-root" / "logs",
        marker_path=tmp_path / "dest-root" / "state" / "bootstrap_marker.json",
        lock_path=tmp_path / "dest-root" / "state" / "bootstrap.lock",
        browser_channel_path=tmp_path / "dest-root" / "state" / "browser_channel.json",
        data_dir=tmp_path / "dest-root" / "data",
    )

    if case.scenario in ("single-file", "whole-directory", "missing-source-raises"):
        fake_repo = tmp_path / "fake-repo"
        fake_source_sync_file = fake_repo / "bootstrap" / "source_sync.py"
        monkeypatch.setattr(source_sync_module, "__file__", str(fake_source_sync_file))

        skip_relative = files[0] if case.scenario == "missing-source-raises" else None
        build_files = tuple(f for f in files if f != skip_relative)
        _write_synthetic_source_tree(fake_repo, build_files, dirs)
        # The probe_msedge.py support file is always required unconditionally too.
        probe_source = fake_repo / "bootstrap" / "probe_msedge.py"
        probe_source.parent.mkdir(parents=True, exist_ok=True)
        probe_source.write_bytes(b"synthetic content: probe_msedge.py\n")

        if case.scenario == "missing-source-raises":
            with pytest.raises(FileNotFoundError):
                source_sync_module.sync_app_source(dest_paths)
            return

        source_sync_module.sync_app_source(dest_paths)

        if case.scenario == "single-file":
            relative = files[0]
            expected_bytes = (fake_repo / relative).read_bytes()
            actual_bytes = (dest_paths.app_dir / relative).read_bytes()
            assert actual_bytes == expected_bytes
        else:
            assert case.scenario == "whole-directory"
            if not dirs:
                # B10.3/B10.4 interim state: _DIRS is temporarily empty (the flat ui/static
                # entry retired with ui/server.py, and B11.1 hasn't repopulated it with
                # src/scoutmb yet). This case is data-driven off the real _DIRS, so it
                # re-activates automatically the moment B11.1 lands -- no further change needed
                # here.
                pytest.skip("_DIRS is temporarily empty between B10.3 and B11.1")
            relative_dir = dirs[0]
            for leaf in ("top-level.txt", "nested/leaf.txt"):
                expected_bytes = (fake_repo / relative_dir / leaf).read_bytes()
                actual_bytes = (dest_paths.app_dir / relative_dir / leaf).read_bytes()
                assert actual_bytes == expected_bytes
    else:
        assert case.scenario == "frozen-vs-unfrozen"

        # --- Unfrozen run: _source_root() == Path(__file__).resolve().parent.parent ---
        unfrozen_repo = tmp_path / "unfrozen-repo"
        monkeypatch.setattr(
            source_sync_module, "__file__", str(unfrozen_repo / "bootstrap" / "source_sync.py")
        )
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        _write_synthetic_source_tree(unfrozen_repo, files, dirs)
        (unfrozen_repo / "bootstrap").mkdir(parents=True, exist_ok=True)
        (unfrozen_repo / "bootstrap" / "probe_msedge.py").write_bytes(
            b"synthetic content: unfrozen probe_msedge.py\n"
        )

        assert source_sync_module._source_root() == unfrozen_repo
        unfrozen_dest = AppPaths(
            root=tmp_path / "unfrozen-dest",
            python_dir=tmp_path / "unfrozen-dest" / "python",
            app_dir=tmp_path / "unfrozen-dest" / "app",
            state_dir=tmp_path / "unfrozen-dest" / "state",
            logs_dir=tmp_path / "unfrozen-dest" / "logs",
            marker_path=tmp_path / "unfrozen-dest" / "state" / "bootstrap_marker.json",
            lock_path=tmp_path / "unfrozen-dest" / "state" / "bootstrap.lock",
            browser_channel_path=tmp_path / "unfrozen-dest" / "state" / "browser_channel.json",
            data_dir=tmp_path / "unfrozen-dest" / "data",
        )
        source_sync_module.sync_app_source(unfrozen_dest)
        assert (unfrozen_dest.app_dir / files[0]).read_bytes() == (
            unfrozen_repo / files[0]
        ).read_bytes()
        # _DIRS is temporarily empty between B10.3 and B11.1 -- see the "whole-directory" skip
        # above for why this is data-driven and self-reactivating, not hardcoded.
        if dirs:
            assert (unfrozen_dest.app_dir / dirs[0] / "top-level.txt").exists()

        # --- Frozen run: _source_root() == Path(sys._MEIPASS) / "app_src" ---
        frozen_meipass = tmp_path / "frozen-meipass"
        frozen_app_src = frozen_meipass / "app_src"
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(frozen_meipass), raising=False)
        _write_synthetic_source_tree(frozen_app_src, files, dirs)
        (frozen_app_src / "_bootstrap_support").mkdir(parents=True, exist_ok=True)
        (frozen_app_src / "_bootstrap_support" / "probe_msedge.py").write_bytes(
            b"synthetic content: frozen probe_msedge.py\n"
        )

        assert source_sync_module._source_root() == frozen_app_src
        frozen_dest = AppPaths(
            root=tmp_path / "frozen-dest",
            python_dir=tmp_path / "frozen-dest" / "python",
            app_dir=tmp_path / "frozen-dest" / "app",
            state_dir=tmp_path / "frozen-dest" / "state",
            logs_dir=tmp_path / "frozen-dest" / "logs",
            marker_path=tmp_path / "frozen-dest" / "state" / "bootstrap_marker.json",
            lock_path=tmp_path / "frozen-dest" / "state" / "bootstrap.lock",
            browser_channel_path=tmp_path / "frozen-dest" / "state" / "browser_channel.json",
            data_dir=tmp_path / "frozen-dest" / "data",
        )
        source_sync_module.sync_app_source(frozen_dest)
        assert (frozen_dest.app_dir / files[0]).read_bytes() == (
            frozen_app_src / files[0]
        ).read_bytes()
        if dirs:
            assert (frozen_dest.app_dir / dirs[0] / "top-level.txt").exists()


def test_bootstrap_registry_is_structurally_valid() -> None:
    # See tests/matrix/pytest_support.py's assert_platform_domain_registry_valid docstring:
    # this shared body is byte-for-byte identical to the equivalent test in
    # test_platform_matrix.py/test_desktop_matrix.py, kept as a thin per-file wrapper here so
    # this catalog stays covered even if one of the other two files is ever deleted.
    assert_platform_domain_registry_valid()


# =================================================================================================
# Migrated from tests/characterization/test_phase_a_gap_closure.py (retired in Slice 2b B10.4):
# bootstrap.paths.ensure_dirs/get_paths and bootstrap.marker.write_marker, never directly called
# by the resolve_root-only BOOT-PATH catalog or the is_environment_valid-only BOOT-MARK catalog
# above.
# =================================================================================================


def test_bootstrap_paths_ensure_dirs_creates_expected_directories(tmp_path: Path) -> None:
    from bootstrap.paths import AppPaths

    root = tmp_path / "app-root"
    paths = AppPaths(
        root=root,
        python_dir=root / "python",
        app_dir=root / "app",
        state_dir=root / "state",
        logs_dir=root / "logs",
        marker_path=root / "state" / "marker.json",
        lock_path=root / "state" / "lock",
        browser_channel_path=root / "state" / "channel.json",
        data_dir=root / "data",
    )
    paths.ensure_dirs()
    assert paths.root.is_dir()
    assert paths.python_dir.is_dir()
    assert paths.app_dir.is_dir()
    assert paths.state_dir.is_dir()
    assert paths.logs_dir.is_dir()


def test_bootstrap_paths_get_paths_builds_from_resolve_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bootstrap.paths import get_paths

    monkeypatch.setenv("SCOUTMB_BOOTSTRAP_ROOT", str(tmp_path / "app-root"))
    paths = get_paths()
    assert paths.root == tmp_path / "app-root"
    assert paths.state_dir == paths.root / "state"
    assert paths.marker_path == paths.state_dir / "bootstrap_marker.json"


def test_bootstrap_marker_write_marker_writes_a_valid_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bootstrap.marker import read_marker, write_marker
    from bootstrap.paths import get_paths

    monkeypatch.setenv("SCOUTMB_BOOTSTRAP_ROOT", str(tmp_path / "app-root"))
    paths = get_paths()
    paths.ensure_dirs()
    write_marker(paths, requirements_hash="abc123", browser_channel="chrome")
    marker = read_marker(paths)
    assert marker is not None
    assert marker["requirements_hash"] == "abc123"
    assert marker["browser_channel"] == "chrome"
