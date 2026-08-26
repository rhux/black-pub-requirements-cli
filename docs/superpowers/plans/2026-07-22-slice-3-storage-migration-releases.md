# Slice 3 — Storage, Migration Hardening & Transactional Releases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Finalization note (2026-08-25, post-Gate-2).** This plan replaces the PRELIMINARY draft
> carried forward from the original descoping round. Gate 2 passed the same day (912 tests,
> `--matrix-lane default` clean at `required=500 passed=500 failed=0 skipped=0 missing=0
> duplicated=0`, commit `647a0ca`). Finalizing against the actual post-Slice-2b codebase (not
> the anchors guessed at descope time) surfaced five corrections, all folded into the tasks
> below rather than left as separate follow-up work:
>
> 1. **`src/scoutmb/ports/storage.py` does not get created.** `src/scoutmb/ports/checkpoint_store.py`'s
>    own docstring states the Phase B spec "declines to create" a generic storage port — "a port
>    with one implementation and no test double is a smell, not a boundary"
>    (`docs/superpowers/specs/2026-07-24-phase-b-package-boundaries-design.md:126-131`). Task C1's
>    permissions/sizes/deletion work lands as plain functions on `src/scoutmb/config.py`'s
>    `UiSettings` plus a new `src/scoutmb/adapters/files/data_root.py`, matching the
>    `adapters/files/atomic.py` / `adapters/files/checkpoint.py` precedent — no Protocol.
> 2. **`src/scoutmb/ui/settings.py` doesn't exist.** `UiSettings` and `_platform_data_root` live in
>    `src/scoutmb/config.py` (moved there in Slice 2a, "a recognized layer in the Phase B spec's
>    dependency-edge table"). C1's anchors are corrected accordingly.
> 3. **`bootstrap/main.py`'s `_launch_app` is currently broken.** It runs
>    `paths.app_dir / "run_app.py"`, which Slice 2b's retirement-packaging sub-plan deleted
>    (`git log` shows `chore: retire scout_schedule_cli.py` era commits) — `source_sync.py` never
>    copied it either (`_FILES`/`_DIRS` only ever named `requirements.txt` and `src/scoutmb`). The
>    real entrypoint is now the console-script target `scoutmb.interfaces.desktop.app:main`
>    (`pyproject.toml:25`), but `src/scoutmb/__main__.py` is empty, so there is no `-m scoutmb`
>    dispatch either. Today, a bootstrapped install cannot launch the app at all. Task C2 fixes
>    this — it already touches `main.py`'s launch path and is a strict prerequisite for testing
>    anything else in this slice end-to-end.
> 4. **`bootstrap/config.py`'s `SMOKE_TEST_IMPORTS` never included `"scoutmb"` itself** — the
>    environment-validity smoke test proves `fastapi`/`playwright`/etc. import, but never proves
>    the synced app package itself imports. Folded into Task C1 (same "does this data root /
>    environment actually work" concern C1 is already testing).
> 5. **`bootstrap/paths.py:resolve_root()` does a bare `os.environ["LOCALAPPDATA"]`** — an
>    undiagnosable `KeyError` off Windows. The spec now names **macOS 14+ arm64** as a supported
>    platform (D34), so this is a live cross-platform correctness bug, not hygiene. Folded into
>    Task C1, which already owns "the app resolves a supported data root" as its top-line
>    contract.
>
> No other preliminary-plan anchor needed correction; `bootstrap/migrate.py`, `bootstrap/marker.py`,
> `bootstrap/downloader.py`, and `bootstrap/main.py`'s lock functions all still exist exactly where
> named, and none of Slice 2's package restructuring touched them.

**Goal:** Manage the installed data root safely (permissions, sizes, explicit delete), harden
the existing copy-only migration into a resumable, verified, split-brain-aware operation, give
durable state and releases a versioned compatibility contract, and replace the temporary
source-copy launcher bridge with a transactional, rollback-capable release installer — all
provable against a throwaway copy of the live layout, never the real install.

**Architecture:** `bootstrap/` stays stdlib-only and outside the package (unchanged Slice-1/2
constraint). Six of seven tasks extend existing `bootstrap/*.py` modules in place; the seventh
(C7) adds three new modules (`bootstrap/release.py`, `bootstrap/activation.py`,
`bootstrap/release_manifest.py`) that together replace `source_sync.sync_app_source`'s direct
in-place copy with a versioned-directory install + atomic pointer switch, modeled on the same
"write to `.tmp`, `os.replace` last" pattern `bootstrap/marker.py` already uses. The one seam
that crosses into the package is a small extension to `src/scoutmb/interfaces/web/app.py`'s
`/api/health` route, needed so bootstrap can confirm a staged release is genuinely serving
(not just that its process exists) before switching the pointer to it.

**Tech Stack:** Python 3.12 stdlib only in `bootstrap/` (`hashlib`, `json`, `shutil`, `os`,
`zipfile`, `urllib.request`, `tomllib`, `stat`) — no new dependency. The one package-side change
(`/api/health`) uses FastAPI, already a dependency. Tests use `pytest`, `tmp_path`, and
`monkeypatch.setenv("SCOUTMB_BOOTSTRAP_ROOT", ...)` (the existing override `bootstrap/paths.py`
already supports) to run entirely against throwaway directories — this slice never touches a
real installed root.

**Global Constraints:**
- **Never mutate the live install during a test.** Every test in this plan operates on a
  `tmp_path`-rooted fake layout; `Gate 3`'s own rehearsal (see end of this document) is the one
  place a throwaway *copy* of the live layout is used, and even that copy is discarded after.
- **Every atomic pointer/marker write is `.tmp` + `os.replace`**, matching `bootstrap/marker.py`'s
  existing `write_marker`. No task introduces a second atomicity idiom.
- **Migration and release-staging never delete or move a source file.** Copy-verify-promote only.
  A collision gets a deterministic `.legacy`/`.legacy-N` sibling name, never an overwrite.
- **`bootstrap/` imports no app code** (unchanged Slice-1 rule) — `bootstrap/release_manifest.py`
  reads `pyproject.toml` via `tomllib`, never `import scoutmb`.
- **OS-backed locking, per-launch split-brain monitoring, release-channel auto-update, and
  timed data retention are POSTPONED (vNext)** — carried forward verbatim from the preliminary
  plan's descope reminders; no task in this plan implements them.
- **Windows 11 x64 and macOS 14+ arm64 are both real targets for the code in this slice** (D34);
  every new function must not assume `os.name == "nt"` unless the preliminary plan or spec says
  so explicitly (only `bootstrap/webview2.py`/`browser_setup.py`'s Windows-only paths are
  exempt, and this plan does not touch them).

**User decisions (already made):**
- Package name `scoutmb`, console command `troop349` (spec, settled 2026-07-21).
- `requirements.txt` (not `pip install -e .`) stays the installer's pip input (spec Phase 8 /
  D15) — this plan's release-staging code copies it verbatim, same as `source_sync.py` does today.
- Gate 3's rehearsal never runs against the live installation — user-approved during the
  original brainstorming round and repeated verbatim in the preliminary plan; still binding.

---

## How this plan was finalized

1. Confirmed Gate 2 green (912 passed, `--matrix-lane default` clean, ruff/mypy clean, coverage
   floors green — see this session's own verification, commit `647a0ca`).
2. Read every anchor the preliminary plan named against the actual post-Slice-2b tree (see the
   five corrections above) rather than assuming they still applied.
3. Read `bootstrap/paths.py`, `bootstrap/main.py`, `bootstrap/migrate.py`, `bootstrap/marker.py`,
   `bootstrap/config.py`, `bootstrap/downloader.py`, `bootstrap/source_sync.py`,
   `bootstrap/python_env.py`, `src/scoutmb/config.py`, `src/scoutmb/interfaces/desktop/app.py`,
   and `src/scoutmb/interfaces/web/app.py` end to end to ground every task in real current
   code, not the pre-Slice-2 line numbers the original spec cites for legacy context.
4. Expanded each of the preliminary plan's seven tasks (C1–C7) to Slice-1 fidelity: symbol
   anchors, a RED test, real implementation code, an exact verify command, and a recovery path.

## Descope reminders (carried forward, still binding)
- **OS-backed ownership is POSTPONED.** Task C2 carries the existing mtime lock forward
  unchanged (behavior parity only).
- Data lifecycle is **permissions + explicit delete only.** Timed retention and
  backup/staged-restore are POSTPONED.
- Split-brain is a **migration-time hash manifest + old-root marker** (Task C4). Per-launch
  monitoring is POSTPONED.
- Transactional install keeps **A/B staging + versioned state + rollback + readiness** (Task C7).
  The release-channel + daily auto-check are POSTPONED.

---

## Task C1: Data root — platform-independent resolution, current-user permissions, category sizes, explicit deletion

**Goal:** `UiSettings` resolves a data root that is never derived from code location, applies
current-user-only permissions to it, reports per-category disk usage, and supports deleting one
category explicitly — and the two known-broken resolution paths (`bootstrap/paths.py`'s bare
`LOCALAPPDATA` lookup, and the environment smoke test's silent omission of `scoutmb` itself) are
fixed as part of the same "does this root actually work" contract.

**Files:**
- Modify: `src/scoutmb/config.py` (`UiSettings` gains `apply_private_permissions`,
  `category_sizes`, `delete_category`)
- Create: `src/scoutmb/adapters/files/data_root.py` (the actual `os`/`stat`/`shutil` work,
  called by `UiSettings` — not a Protocol port, see the finalization note above)
- Modify: `bootstrap/paths.py` (`resolve_root` raises a diagnosable error instead of a bare
  `KeyError`)
- Modify: `bootstrap/config.py` (`SMOKE_TEST_IMPORTS` gains `"scoutmb"`)
- Test: `tests/storage/test_data_roots.py`, `tests/storage/test_permissions.py`,
  `tests/storage/test_data_management.py`, `tests/launcher/test_paths.py`

**Acceptance Criteria:**
- [ ] `UiSettings.resolve()` with no `data_root` arg, no `SCOUTMB_DATA_DIR`, and `dev_mode=False`
      returns the same path regardless of the process's current working directory
- [ ] After `UiSettings.resolve(...).ensure_dirs()` + `.apply_private_permissions()`, the data
      root directory is readable/writable by the owner only on POSIX (mode `0o700`); on
      Windows the call is a documented no-op (ACLs are POSTPONED, not silently claimed)
- [ ] `UiSettings.category_sizes()` returns `{"scouts_csv": int, "pdf_uploads": int, "runs": int}`
      byte counts, `0` for a category that doesn't exist yet
- [ ] `UiSettings.delete_category("runs")` removes only `runs_dir` and recreates it empty;
      deleting a category that doesn't exist is a no-op, never an error
- [ ] `bootstrap.paths.resolve_root()` raises `RuntimeError` with the missing variable named,
      not `KeyError`, when `LOCALAPPDATA` is unset and `SCOUTMB_BOOTSTRAP_ROOT` is also unset
- [ ] `bootstrap.marker.is_environment_valid` fails (returns `False`) when `scoutmb` cannot be
      imported in the target environment, proven via `SMOKE_TEST_IMPORTS`

**Verify:** `uv run pytest -q tests/storage/ tests/launcher/test_paths.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/storage/test_data_roots.py
from __future__ import annotations

import os
from pathlib import Path

from scoutmb.config import UiSettings


def test_resolution_is_platform_and_code_location_independent(
    tmp_path: Path, monkeypatch
) -> None:
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
```

```python
# tests/storage/test_permissions.py
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest
from scoutmb.config import UiSettings


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits only")
def test_current_user_permissions_on_supported_platforms(tmp_path: Path) -> None:
    settings = UiSettings(data_root=tmp_path / "data")
    settings.ensure_dirs()

    settings.apply_private_permissions()

    mode = stat.S_IMODE(settings.data_root.stat().st_mode)
    assert mode == 0o700


@pytest.mark.skipif(sys.platform != "win32", reason="documents the Windows no-op")
def test_windows_apply_private_permissions_is_a_documented_noop(tmp_path: Path) -> None:
    settings = UiSettings(data_root=tmp_path / "data")
    settings.ensure_dirs()

    settings.apply_private_permissions()  # must not raise; ACLs are POSTPONED
```

```python
# tests/storage/test_data_management.py
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
```

```python
# tests/launcher/test_paths.py
from __future__ import annotations

import pytest
from bootstrap import paths


def test_resolve_root_raises_diagnosable_error_without_override_or_localappdata(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SCOUTMB_BOOTSTRAP_ROOT", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    with pytest.raises(RuntimeError, match="LOCALAPPDATA"):
        paths.resolve_root()
```

```python
# tests/launcher/test_smoke_test_imports.py
from __future__ import annotations

from bootstrap.config import SMOKE_TEST_IMPORTS


def test_smoke_test_imports_includes_the_app_package_itself() -> None:
    assert "scoutmb" in SMOKE_TEST_IMPORTS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/storage/ tests/launcher/test_paths.py tests/launcher/test_smoke_test_imports.py`
Expected: `ModuleNotFoundError: No module named 'tests.storage'` (dir doesn't exist yet), then
after adding `__init__.py` placeholders, `AttributeError`/`AssertionError` on the missing
methods and the still-bare `KeyError`.

- [ ] **Step 3: Implement `src/scoutmb/adapters/files/data_root.py`**

```python
"""Filesystem-permission and disk-usage helpers for one data root. Plain functions, not a
Protocol/port -- src/scoutmb/ports/checkpoint_store.py's own docstring records that the Phase B
spec declines to create a generic storage port (one implementation, no test double, not a real
boundary). UiSettings (src/scoutmb/config.py) is the only caller."""

from __future__ import annotations

import shutil
import stat
import sys
from pathlib import Path

_PRIVATE_DIR_MODE = 0o700


def apply_private_permissions(root: Path) -> None:
    """Best-effort current-user-only permissions. POSIX: chmod 0700. Windows: a documented
    no-op -- ACL-based restriction is POSTPONED (vNext), not silently claimed here."""
    if sys.platform == "win32":
        return
    root.chmod(_PRIVATE_DIR_MODE)


def directory_size(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def file_size(path: Path) -> int:
    return path.stat().st_size if path.is_file() else 0


def delete_directory_contents(root: Path) -> None:
    """Removes root itself if present, then recreates it empty -- callers never see a missing
    directory, only an empty one, so downstream code that assumes the dir exists keeps working."""
    if root.is_dir():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Extend `UiSettings` in `src/scoutmb/config.py`**

```python
# add near the top, alongside the existing imports
from scoutmb.adapters.files import data_root as _data_root

# add as methods on the existing UiSettings dataclass, after ensure_dirs
    def apply_private_permissions(self) -> None:
        _data_root.apply_private_permissions(self.data_root)

    def category_sizes(self) -> dict[str, int]:
        return {
            "scouts_csv": _data_root.file_size(self.scouts_csv),
            "pdf_uploads": _data_root.directory_size(self.pdf_uploads_dir),
            "runs": _data_root.directory_size(self.runs_dir),
        }

    def delete_category(self, category: str) -> None:
        targets = {
            "pdf_uploads": self.pdf_uploads_dir,
            "runs": self.runs_dir,
        }
        target = targets.get(category)
        if target is None:
            return
        _data_root.delete_directory_contents(target)
```

- [ ] **Step 5: Fix `bootstrap/paths.py`'s bare `LOCALAPPDATA` lookup**

```python
def resolve_root() -> Path:
    override = os.environ.get("SCOUTMB_BOOTSTRAP_ROOT")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError(
            "Cannot resolve the bootstrap root: LOCALAPPDATA is not set and "
            "SCOUTMB_BOOTSTRAP_ROOT was not provided as an override. On a real Windows "
            "install LOCALAPPDATA is always set by the OS; set SCOUTMB_BOOTSTRAP_ROOT "
            "explicitly when running off Windows (tests, macOS development)."
        )
    return Path(base) / APP_NAME
```

- [ ] **Step 6: Add `scoutmb` to the smoke-test import list**

```python
# bootstrap/config.py -- SMOKE_TEST_IMPORTS list, add as the first entry
SMOKE_TEST_IMPORTS = [
    "scoutmb",
    "fastapi",
    "playwright",
    "webview",
    "cv2",
    "fitz",
    "openpyxl",
    "uvicorn",
    "multipart",
]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest -q tests/storage/ tests/launcher/test_paths.py tests/launcher/test_smoke_test_imports.py -v`
Expected: all PASS

- [ ] **Step 8: Run the full suite + lint + types to confirm no regression**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: same pass count plus the new tests, ruff/mypy clean

- [ ] **Step 9: Commit**

```bash
git add src/scoutmb/config.py src/scoutmb/adapters/files/data_root.py bootstrap/paths.py \
        bootstrap/config.py tests/storage/ tests/launcher/test_paths.py \
        tests/launcher/test_smoke_test_imports.py
git commit -m "feat(storage): platform-independent data root, permissions, sizes, deletion (C1)"
```

**Recovery:** Every helper in `data_root.py` reads or deletes an already-identified category
directory; a failure mid-`delete_category` leaves that one category's directory in whatever
state `shutil.rmtree` left it (partially removed or fully removed) and the immediately-following
`mkdir(exist_ok=True)` restores an empty directory on the next call — there is no multi-category
transaction to roll back. Stop mutation and require an explicit operator retry; never guess and
recreate other categories.

---

## Task C2: Carry the mtime lock forward + fix the broken app launch

**Goal:** The existing mtime-based single-instance lock behaves identically to today (no
OS-lock/rendezvous work), and `_launch_app` is fixed to invoke the app's real current
entrypoint — today it references `run_app.py`, a file Slice 2b's retirement deleted, so a
freshly bootstrapped install cannot start the app at all.

**Files:**
- Modify: `bootstrap/main.py` (`_launch_app` only; `_acquire_lock`/`_release_lock` unchanged —
  proven unchanged by the parity test, not edited)
- Test: `tests/launcher/test_mtime_lock_parity.py`, `tests/launcher/test_launch_command.py`

**Acceptance Criteria:**
- [ ] A fresh lock file blocks a second `_acquire_lock` call (returns `False`)
- [ ] A lock file older than `LOCK_STALE_SECONDS` is reclaimed (`_acquire_lock` returns `True`
      and the stale file is replaced)
- [ ] `_release_lock` removes the lock file even if it doesn't exist (`missing_ok=True` already
      does this — the test proves it, doesn't change it)
- [ ] `_launch_app` builds a `subprocess.Popen` argv that runs a module which actually exists
      and is importable (`scoutmb.interfaces.desktop.app`), not a deleted flat file
- [ ] `_launch_app`'s argv shape is `[pythonw_exe, "-m", "scoutmb.interfaces.desktop.app"]`,
      matching how every other package entrypoint in this repo is invoked (module execution,
      no reliance on `src/scoutmb/__main__.py`, which stays empty — out of this plan's scope)

**Verify:** `uv run pytest -q tests/launcher/test_mtime_lock_parity.py tests/launcher/test_launch_command.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/launcher/test_mtime_lock_parity.py
from __future__ import annotations

import time
from pathlib import Path

from bootstrap.config import LOCK_STALE_SECONDS
from bootstrap.main import _acquire_lock, _release_lock
from bootstrap.paths import AppPaths


def _paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        root=tmp_path,
        python_dir=tmp_path / "python",
        app_dir=tmp_path / "app",
        state_dir=tmp_path / "state",
        logs_dir=tmp_path / "logs",
        marker_path=tmp_path / "state" / "bootstrap_marker.json",
        lock_path=tmp_path / "state" / "bootstrap.lock",
        browser_channel_path=tmp_path / "state" / "browser_channel.json",
        data_dir=tmp_path / "data",
    )


def test_lock_behavior_matches_legacy(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    assert _acquire_lock(paths) is True
    assert paths.lock_path.is_file()
    assert _acquire_lock(paths) is False  # fresh lock blocks a second acquire

    _release_lock(paths)
    assert not paths.lock_path.exists()
    _release_lock(paths)  # missing_ok -- must not raise on an already-released lock

    assert _acquire_lock(paths) is True
    stale_time = time.time() - LOCK_STALE_SECONDS - 1
    import os

    os.utime(paths.lock_path, (stale_time, stale_time))
    assert _acquire_lock(paths) is True  # stale lock is reclaimed, not honored
```

```python
# tests/launcher/test_launch_command.py
from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock

from bootstrap.main import _launch_app
from bootstrap.paths import AppPaths


def test_launch_uses_the_real_desktop_entrypoint_module(tmp_path: Path, monkeypatch) -> None:
    paths = AppPaths(
        root=tmp_path,
        python_dir=tmp_path / "python",
        app_dir=tmp_path / "app",
        state_dir=tmp_path / "state",
        logs_dir=tmp_path / "logs",
        marker_path=tmp_path / "state" / "bootstrap_marker.json",
        lock_path=tmp_path / "state" / "bootstrap.lock",
        browser_channel_path=tmp_path / "state" / "browser_channel.json",
        data_dir=tmp_path / "data",
    )
    paths.ensure_dirs()
    captured: dict[str, object] = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        return MagicMock()

    monkeypatch.setattr("bootstrap.main.subprocess.Popen", fake_popen)
    monkeypatch.setattr("bootstrap.main.time.sleep", lambda seconds: None)
    monkeypatch.setattr(
        "bootstrap.main.python_env.pythonw_exe", lambda p: Path("/fake/pythonw.exe")
    )

    _launch_app(paths, channel=None)

    argv = captured["argv"]
    assert argv[0] == "/fake/pythonw.exe" or str(argv[0]) == "/fake/pythonw.exe"
    assert argv[1:] == ["-m", "scoutmb.interfaces.desktop.app"]
    # And the module this argv names must actually exist and import cleanly today --
    # the whole point of this test is catching a repeat of the run_app.py regression.
    importlib.import_module("scoutmb.interfaces.desktop.app")
```

- [ ] **Step 2: Run tests to verify the launch-command test fails**

Run: `uv run pytest -q tests/launcher/test_launch_command.py -v`
Expected: FAIL — `argv[1:] == ['app/run_app.py']`, not `['-m', 'scoutmb.interfaces.desktop.app']`

- [ ] **Step 3: Fix `_launch_app` in `bootstrap/main.py`**

```python
def _launch_app(paths: AppPaths, channel: str | None) -> None:
    log_path = paths.logs_dir / "run_app.log"
    env = {
        **os.environ,
        "SCOUTMB_BROWSER_CHANNEL": channel or "",
        "SCOUTMB_DATA_DIR": str(paths.data_dir),
    }
    with open(log_path, "ab") as log_fh:
        subprocess.Popen(
            [str(python_env.pythonw_exe(paths)), "-m", "scoutmb.interfaces.desktop.app"],
            cwd=str(paths.app_dir),
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
        )
    time.sleep(APP_LAUNCH_SETTLE_SECONDS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/launcher/test_mtime_lock_parity.py tests/launcher/test_launch_command.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add bootstrap/main.py tests/launcher/test_mtime_lock_parity.py \
        tests/launcher/test_launch_command.py
git commit -m "fix(launcher): carry mtime lock forward; fix _launch_app's dead run_app.py reference (C2)"
```

**Recovery:** `_acquire_lock`/`_release_lock` are unchanged, so their existing failure mode
(operator waits out `LOCK_STALE_SECONDS` or deletes the lock file by hand) is unchanged. If the
launch-command fix is wrong (wrong module path), the symptom is immediate and loud — the child
process exits nonzero and `run_app.log` shows an `ImportError`/`ModuleNotFoundError` — never a
silent partial launch, since `-m` either finds the module or it doesn't.

---

## Task C3: Copy-only SHA-256 migration hardening + resumability

**Goal:** Migration (basic copy + verify landed in Slice 1) gains sibling-staging on the same
filesystem as the destination, per-item resumable interruption, and a manual-backup-receipt
gate before any production-mode copy — without ever moving, deleting, or overwriting a source
file.

**Files:**
- Modify: `bootstrap/migrate.py`
- Test: `tests/migration/test_copy_migration.py`

**Acceptance Criteria:**
- [ ] Source files are byte-identical and present after migration completes (unchanged
      guarantee, now proven against the staged/resumable path too)
- [ ] Staging happens in a sibling directory of `data_dir` (`data_dir.parent / f".{data_dir.name}.staging"`),
      guaranteeing `os.replace`/`Path.rename` promotion never crosses a filesystem boundary
- [ ] Interrupting after one item is staged-and-verified-but-not-yet-promoted, then rerunning,
      resumes correctly: the promoted item is not recopied, the not-yet-promoted item is
      recopied from scratch (a partial stage is never trusted)
- [ ] `migrate_legacy_data(..., production=True)` refuses to copy anything and raises
      `RuntimeError` unless `SCOUTMB_MIGRATION_BACKUP_CONFIRMED=1` is set in the environment;
      `production=False` (the default, used by every existing call site and every test) is
      unaffected

**Verify:** `uv run pytest -q tests/migration/test_copy_migration.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/migration/test_copy_migration.py
from __future__ import annotations

import hashlib
import os
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
    marker = (data_dir / ".migrated")
    assert marker.is_file()


def test_each_interruption_point_resumes_idempotently(tmp_path: Path, monkeypatch) -> None:
    app_dir = tmp_path / "app"
    data_dir = tmp_path / "data"
    app_dir.mkdir()
    (app_dir / "scouts.csv").write_bytes(b"data-one")
    (app_dir / "runs").mkdir()
    (app_dir / "runs" / "r1.json").write_bytes(b"run-one")

    calls = {"n": 0}
    real_promote = None

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/migration/test_copy_migration.py -v`
Expected: `AttributeError: module 'bootstrap.migrate' has no attribute '_promote_staged_item'`
and `TypeError: migrate_legacy_data() got an unexpected keyword argument 'production'`

- [ ] **Step 3: Rewrite `bootstrap/migrate.py` with staging + resumability + the backup gate**

```python
"""One-time COPY of legacy app/ user data into data/. Never moves or deletes.

One install exists with a season of real records. If this migration is wrong, the data must
still be where it always was. Staging happens in a SIBLING directory of data_dir (never inside
app_dir, which may be on a different filesystem/volume than data_dir on some installs) so the
final promotion is always same-filesystem os.replace/Path.rename -- atomic, never a partial
write visible at the destination. Each item is staged, hash-verified, then individually
promoted; a rerun after interruption skips items already promoted and recopies-from-scratch any
item that was staged but not yet promoted, since a partial stage is never trusted."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

MIGRATION_MARKER = ".migrated"
_ITEMS = [("scouts.csv", False), ("pdf-uploads", True), ("runs", True)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_tree(src: Path, dst: Path) -> None:
    src_files = sorted(p for p in src.rglob("*") if p.is_file())
    for src_file in src_files:
        dst_file = dst / src_file.relative_to(src)
        if not dst_file.is_file() or _sha256(src_file) != _sha256(dst_file):
            raise RuntimeError(f"migration hash verify failed for {src_file.relative_to(src)}")


def _stage_item(src: Path, staging: Path, name: str, is_dir: bool) -> Path:
    """Copies src into staging/name from scratch every time -- a partial stage from an earlier
    interrupted run is never reused, only overwritten, since a partial copy cannot be trusted."""
    staged_path = staging / name
    if staged_path.exists():
        shutil.rmtree(staged_path) if staged_path.is_dir() else staged_path.unlink()
    if is_dir:
        shutil.copytree(src, staged_path)
        _verify_tree(src, staged_path)
    else:
        shutil.copy2(src, staged_path)
        if _sha256(src) != _sha256(staged_path):
            raise RuntimeError(f"migration hash verify failed for {name}")
    return staged_path


def _promote_staged_item(staged_path: Path, data_dir: Path, name: str) -> str:
    """Renames staged_path into data_dir (same filesystem, per the sibling-staging contract) --
    a real collision (already-promoted data with the same name) gets a deterministic
    .legacy/.legacy-N sibling name, never an overwrite."""
    dst = data_dir / name
    if dst.exists():
        candidate = data_dir / f"{name}.legacy"
        suffix = 1
        while candidate.exists():
            suffix += 1
            candidate = data_dir / f"{name}.legacy-{suffix}"
        dst = candidate
    os.replace(staged_path, dst) if staged_path.is_file() else shutil.move(str(staged_path), str(dst))
    return dst.name


def migrate_legacy_data(
    app_dir: Path, data_dir: Path, *, production: bool = False
) -> dict[str, object] | None:
    if production and os.environ.get("SCOUTMB_MIGRATION_BACKUP_CONFIRMED") != "1":
        raise RuntimeError(
            "Production-mode migration requires a manual backup of the existing app data "
            "before it runs. Back up the app folder, then set "
            "SCOUTMB_MIGRATION_BACKUP_CONFIRMED=1 and retry."
        )
    if (data_dir / MIGRATION_MARKER).is_file() or not app_dir.is_dir():
        return None
    present = [(n, d) for n, d in _ITEMS if (app_dir / n).exists()]
    if not present:
        return None

    data_dir.mkdir(parents=True, exist_ok=True)
    staging = data_dir.parent / f".{data_dir.name}.staging"
    staging.mkdir(parents=True, exist_ok=True)

    copied, collisions = [], []
    try:
        for name, is_dir in present:
            already_promoted = (data_dir / name).exists() or any(
                p.name.startswith(f"{name}.legacy") for p in data_dir.glob(f"{name}.legacy*")
            )
            if already_promoted:
                continue  # resumed run: this item survived a prior interrupted attempt
            src = app_dir / name
            staged_path = _stage_item(src, staging, name, is_dir)
            promoted_name = _promote_staged_item(staged_path, data_dir, name)
            if promoted_name != name:
                collisions.append(name)
            copied.append(promoted_name)
    finally:
        if staging.exists() and not any(staging.iterdir()):
            staging.rmdir()

    # Write the old-root explanatory marker BEFORE the .migrated completion marker -- see
    # module docstring precedent in the original Slice 1 version; unchanged here.
    (app_dir / "MOVED-README.txt").write_text(
        "This folder's data was copied to the app's data directory. Originals are "
        "retained here but no longer used. Do not run the old app from here.\n",
        encoding="utf-8",
    )
    report = {
        "migrated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(app_dir),
        "copied": copied,
        "collisions": collisions,
        "verification": "sha256",
        "originals_retained": True,
    }
    (data_dir / MIGRATION_MARKER).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/migration/test_copy_migration.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add bootstrap/migrate.py tests/migration/test_copy_migration.py
git commit -m "feat(migration): sibling-staging, per-item resumability, production backup gate (C3)"
```

**Recovery:** On any interruption, the source tree is untouched (never written to), the
destination `data_dir` holds only items that were fully staged-verified-and-promoted before the
interruption, and the staging directory holds whatever partial copy was in flight — which the
next run discards and recopies from scratch rather than trusting. No `.migrated` marker is ever
written until every present item has been promoted, so a resumed run is always detectable
(marker absent) and always safe to retry.

---

## Task C4: Split-brain — migration-time hash manifest + old-root marker

**Goal:** Migration records a content-hash manifest of the source tree at migration time (not
just per-file verification against the copy, which C3 already does) and leaves the existing
`MOVED-README.txt` marker in the old root — together giving a later manual check something
concrete to diff the abandoned old root against, without any automated per-launch monitoring.

**Files:**
- Modify: `bootstrap/migrate.py` (adds `migration_manifest.json` alongside `.migrated`)
- Test: `tests/migration/test_split_brain.py`

**Acceptance Criteria:**
- [ ] `migration_manifest.json` in `data_dir` lists every migrated file's path (relative to the
      original `app_dir`), SHA-256, and size, generated from the same hashes C3's verification
      already computes (no second hashing pass over the same bytes)
- [ ] The manifest is written as part of the same atomic completion step as `.migrated` (last,
      after every item is promoted) — a manifest is never present without a completed migration
- [ ] `MOVED-README.txt` continues to be written into `app_dir` (unchanged from Slice 1/C3)

**Verify:** `uv run pytest -q tests/migration/test_split_brain.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/migration/test_split_brain.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/migration/test_split_brain.py::test_manifest_records_source_hashes -v`
Expected: FAIL — `FileNotFoundError: migration_manifest.json`

- [ ] **Step 3: Extend `bootstrap/migrate.py` to build and write the manifest**

Add a manifest accumulator that `_stage_item` records into (reusing the hash it already
computes, not re-hashing), then write it out alongside the completion marker:

```python
# add near the top, alongside MIGRATION_MARKER
MANIFEST_FILE = "migration_manifest.json"


def _relative_file_hashes(src: Path, root_name: str) -> list[dict[str, object]]:
    """Walks a staged/verified item and records path-relative-to-app_dir + hash + size for
    every file -- reuses _sha256 (already proven correct by C3's verification) rather than
    inventing a second hashing routine."""
    if src.is_file():
        return [{"path": root_name, "sha256": _sha256(src), "size": src.stat().st_size}]
    return [
        {
            "path": f"{root_name}/{f.relative_to(src)}".replace("\\", "/"),
            "sha256": _sha256(f),
            "size": f.stat().st_size,
        }
        for f in sorted(src.rglob("*"))
        if f.is_file()
    ]
```

Then in `migrate_legacy_data`, before the loop, initialize `manifest_files: list[dict[str,
object]] = []`, and inside the loop, right after `src = app_dir / name` (before staging, so the
manifest reflects the SOURCE as it existed when migration started — the inventory C4's
docstring promises), append:

```python
            manifest_files.extend(_relative_file_hashes(src, name))
```

Finally, alongside the existing `report`/`.migrated` write:

```python
    (data_dir / MANIFEST_FILE).write_text(
        json.dumps({"files": manifest_files}, indent=2), encoding="utf-8"
    )
```

Written in the same order as the existing marker sequence: `MOVED-README.txt` (old root) →
`migration_manifest.json` (new root, inventory) → `.migrated` (new root, completion — written
last, unchanged from C3, so a crash between the manifest write and the completion marker just
means a resumed run rebuilds the manifest from scratch, which is harmless since it's a pure
read-and-hash of already-promoted-or-about-to-be-promoted files).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/migration/test_split_brain.py tests/migration/test_copy_migration.py -v`
Expected: all PASS (both files — C4 must not regress C3)

- [ ] **Step 5: Commit**

```bash
git add bootstrap/migrate.py tests/migration/test_split_brain.py
git commit -m "feat(migration): source hash manifest for split-brain detection (C4)"
```

**Recovery:** The manifest is regenerated in full on every migration attempt (including a
resumed one), never partially updated, so an interrupted run simply has no manifest yet — never
a stale or half-written one. Preserve both the old root and the new data root always; this task
never auto-merges or auto-deletes either.

---

## Task C5: Version durable state + activation compatibility tuple

**Goal:** A release declares the durable-state schema window it can read (min/max generation),
and a small activation-tuple check refuses to run against state outside that window, failing
closed before any mutation — the foundation Task C7's transactional install validates against
before switching `current.json`.

**Files:**
- Create: `bootstrap/release_manifest.py` (`ReleaseManifest`, `build_release_manifest`)
- Create: `bootstrap/activation.py` (`ActivationTuple`, `validate_activation`)
- Modify: `bootstrap/config.py` (`DURABLE_STATE_SCHEMA_VERSION` — the single aggregate version
  this release's `run_state`/`checkpoint`/settings contracts satisfy; bumped whenever any of
  `scoutmb.core.run_state.RUN_STATE_VERSION`, `scoutmb.ports.checkpoint_store.CHECKPOINT_VERSION`,
  or `bootstrap.marker.MARKER_SCHEMA_VERSION` changes)
- Test: `tests/contracts/test_state_compatibility.py`, `tests/integration/test_activation_tuple.py`

**Acceptance Criteria:**
- [ ] `build_release_manifest(source_root)` reads `version` from `pyproject.toml` via
      `tomllib` (no `import scoutmb`), computes `requirements_hash` via the existing
      `bootstrap.marker.compute_requirements_hash`, and stamps
      `state_schema_min`/`state_schema_max` from `DURABLE_STATE_SCHEMA_VERSION`
- [ ] `validate_activation(candidate, installed_state_generation)` returns `True` only when
      `installed_state_generation` falls within `[candidate.state_schema_min,
      candidate.state_schema_max]` inclusive
- [ ] A candidate whose window does not cover the currently-installed generation is rejected
      (`validate_activation` returns `False`) — proven for both "too old" and "too new"
      generations
- [ ] The N and N-1 window is provable directly: two `ReleaseManifest`s one version apart both
      validate against the SAME installed generation (the "supported N/N-1" contract, not just
      the exact-match case)
- [ ] `ActivationTuple` (the read/written shape of `current.json`, built in C7) round-trips
      through JSON with no loss of the fields `validate_activation` reads

**Verify:** `uv run pytest -q tests/contracts/test_state_compatibility.py tests/integration/test_activation_tuple.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/contracts/test_state_compatibility.py
from __future__ import annotations

from bootstrap.activation import ActivationTuple, validate_activation
from bootstrap.release_manifest import ReleaseManifest


def _manifest(version: str, schema_min: int, schema_max: int) -> ReleaseManifest:
    return ReleaseManifest(
        version=version,
        python_abi="cp312",
        requirements_hash="deadbeef",
        state_schema_min=schema_min,
        state_schema_max=schema_max,
    )


def test_n_and_n_minus_one_matrix() -> None:
    release_n = _manifest("0.2.0", schema_min=1, schema_max=2)
    release_n_minus_1 = _manifest("0.1.0", schema_min=1, schema_max=1)

    # Both releases can activate against a state generation of 1 -- the N/N-1 overlap window.
    assert validate_activation(release_n, installed_state_generation=1) is True
    assert validate_activation(release_n_minus_1, installed_state_generation=1) is True
    # Only release N can activate against generation 2 (a schema release N-1 predates).
    assert validate_activation(release_n, installed_state_generation=2) is True
    assert validate_activation(release_n_minus_1, installed_state_generation=2) is False


def test_unknown_newer_schema_fails_before_write() -> None:
    release = _manifest("0.1.0", schema_min=1, schema_max=1)

    assert validate_activation(release, installed_state_generation=99) is False
```

```python
# tests/integration/test_activation_tuple.py
from __future__ import annotations

import json

from bootstrap.activation import ActivationTuple


def test_all_components_validated_together() -> None:
    tuple_ = ActivationTuple(
        release_version="0.2.0",
        state_generation=2,
        capability_manifest_digest="abc123",
    )

    round_tripped = ActivationTuple.from_json(json.loads(json.dumps(tuple_.to_json())))

    assert round_tripped == tuple_
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/contracts/test_state_compatibility.py tests/integration/test_activation_tuple.py -v`
Expected: `ModuleNotFoundError: No module named 'bootstrap.activation'`

- [ ] **Step 3: Implement `bootstrap/release_manifest.py`**

```python
"""What one built release declares about itself: version, the Python ABI it was built for, its
pinned-requirements hash, and the durable-state schema window it can read. bootstrap/ stays
stdlib-only and imports no app code -- version comes from pyproject.toml via tomllib, never
`import scoutmb` (that would require the release's own environment to already be provisioned,
which is exactly what hasn't happened yet when this manifest is built)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from bootstrap.config import DURABLE_STATE_SCHEMA_VERSION
from bootstrap.marker import compute_requirements_hash


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    version: str
    python_abi: str
    requirements_hash: str
    state_schema_min: int
    state_schema_max: int

    def to_json(self) -> dict[str, object]:
        return {
            "version": self.version,
            "python_abi": self.python_abi,
            "requirements_hash": self.requirements_hash,
            "state_schema_min": self.state_schema_min,
            "state_schema_max": self.state_schema_max,
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> ReleaseManifest:
        return cls(
            version=str(data["version"]),
            python_abi=str(data["python_abi"]),
            requirements_hash=str(data["requirements_hash"]),
            state_schema_min=int(data["state_schema_min"]),  # type: ignore[arg-type]
            state_schema_max=int(data["state_schema_max"]),  # type: ignore[arg-type]
        )


def build_release_manifest(source_root: Path, requirements_path: Path) -> ReleaseManifest:
    pyproject = tomllib.loads((source_root / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(pyproject["project"]["version"])
    return ReleaseManifest(
        version=version,
        python_abi="cp312",
        requirements_hash=compute_requirements_hash(requirements_path),
        state_schema_min=max(1, DURABLE_STATE_SCHEMA_VERSION - 1),
        state_schema_max=DURABLE_STATE_SCHEMA_VERSION,
    )
```

- [ ] **Step 4: Implement `bootstrap/activation.py`**

```python
"""The activation tuple: what current.json records about the currently-active release, and the
compatibility check a candidate release must pass before it can become current.json. Kept
separate from release_manifest.py -- a ReleaseManifest describes a BUILT release (what it can
do); an ActivationTuple describes the INSTALLED-AND-ACTIVE state (what is running now)."""

from __future__ import annotations

from dataclasses import dataclass

from bootstrap.release_manifest import ReleaseManifest


@dataclass(frozen=True, slots=True)
class ActivationTuple:
    release_version: str
    state_generation: int
    capability_manifest_digest: str

    def to_json(self) -> dict[str, object]:
        return {
            "release_version": self.release_version,
            "state_generation": self.state_generation,
            "capability_manifest_digest": self.capability_manifest_digest,
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> ActivationTuple:
        return cls(
            release_version=str(data["release_version"]),
            state_generation=int(data["state_generation"]),  # type: ignore[arg-type]
            capability_manifest_digest=str(data["capability_manifest_digest"]),
        )


def validate_activation(candidate: ReleaseManifest, installed_state_generation: int) -> bool:
    """A candidate release may activate only if it can read the durable state that is already
    on disk -- fails closed (returns False) for both an unknown-newer generation the candidate
    predates, and a too-old generation the candidate has since dropped support for."""
    return candidate.state_schema_min <= installed_state_generation <= candidate.state_schema_max
```

- [ ] **Step 5: Add `DURABLE_STATE_SCHEMA_VERSION` to `bootstrap/config.py`**

```python
# Bumped whenever scoutmb.core.run_state.RUN_STATE_VERSION,
# scoutmb.ports.checkpoint_store.CHECKPOINT_VERSION, or bootstrap.marker.MARKER_SCHEMA_VERSION
# changes -- the single aggregate durable-state generation a release manifest declares support
# for (see bootstrap/release_manifest.py, bootstrap/activation.py).
DURABLE_STATE_SCHEMA_VERSION = 1
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest -q tests/contracts/test_state_compatibility.py tests/integration/test_activation_tuple.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add bootstrap/release_manifest.py bootstrap/activation.py bootstrap/config.py \
        tests/contracts/test_state_compatibility.py tests/integration/test_activation_tuple.py
git commit -m "feat(release): versioned durable state + activation compatibility tuple (C5)"
```

**Recovery:** These are pure, side-effect-free functions over already-loaded data — there is no
partial-write state to recover from. A failed `validate_activation` call is the intended
fail-closed outcome, not an error condition Task C7's caller needs to unwind; C7 reacts to
`False` by refusing to switch `current.json`, nothing more.

---

## Task C6: Harden downloads, archives, disk budgets, cache ownership

**Goal:** Downloads are hash+size validated with a redirect policy that never follows an
untrusted host; ZIP extraction rejects path-traversal/symlink/oversized-expansion payloads
before any file is written; available disk space is preflighted against the current + rollback
release reserve; and the capability cache (Python/browser/PDF-support downloads) evicts only
payloads no active or rollback release still references.

**Files:**
- Modify: `bootstrap/downloader.py` (hash+size validation, redirect-host allowlist)
- Create: `bootstrap/safe_extract.py`
- Create: `bootstrap/disk_budget.py`
- Create: `bootstrap/capability_cache.py`
- Modify: `bootstrap/python_env.py` (`_download_and_extract_python` uses `safe_extract_zip`
  instead of raw `zipfile.ZipFile.extractall`)
- Test: `tests/launcher/test_downloader.py`, `tests/security/test_safe_extract.py`,
  `tests/launcher/test_disk_budget.py`, `tests/launcher/test_capability_cache.py`

**Acceptance Criteria:**
- [ ] `download(..., expected_sha256=..., expected_size=...)` deletes the downloaded file and
      raises `RuntimeError` on either mismatch, before returning
- [ ] A redirect to a host outside a caller-supplied allowlist is refused with `RuntimeError`,
      never silently followed
- [ ] `safe_extract_zip` rejects, for each of: a `..`-traversal entry name, an absolute-path
      entry name, a symlink entry, and a total-expanded-size-over-budget archive — none of
      these leaves any file written to the destination
- [ ] `preflight_disk_space(root, required_bytes)` raises `RuntimeError` with the free/required
      byte counts named, before any download starts, when free space is insufficient
- [ ] `capability_cache.evict_unreferenced` deletes a payload only when no release manifest
      (active or the one immediately prior) lists it as a dependency; a payload referenced by
      either is preserved

**Verify:** `uv run pytest -q tests/launcher/test_downloader.py tests/security/test_safe_extract.py tests/launcher/test_disk_budget.py tests/launcher/test_capability_cache.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/launcher/test_downloader.py
from __future__ import annotations

import hashlib
import http.server
import threading
from pathlib import Path

import pytest
from bootstrap.downloader import download


class _Handler(http.server.BaseHTTPRequestHandler):
    payload = b"hello-world-payload"

    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture()
def local_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/payload"
    server.shutdown()


def test_stream_hash_size_and_redirect_policy(tmp_path: Path, local_server: str) -> None:
    dest = tmp_path / "payload.bin"
    good_hash = hashlib.sha256(_Handler.payload).hexdigest()

    download(local_server, dest, expected_sha256=good_hash, expected_size=len(_Handler.payload))
    assert dest.read_bytes() == _Handler.payload

    dest.unlink()
    with pytest.raises(RuntimeError, match="sha256"):
        download(local_server, dest, expected_sha256="0" * 64, expected_size=len(_Handler.payload))
    assert not dest.exists()

    dest.unlink(missing_ok=True)
    with pytest.raises(RuntimeError, match="size"):
        download(local_server, dest, expected_sha256=good_hash, expected_size=999999)
    assert not dest.exists()
```

```python
# tests/security/test_safe_extract.py
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from bootstrap.safe_extract import safe_extract_zip


def _make_zip(tmp_path: Path, name: str, entries: dict[str, bytes]) -> Path:
    zip_path = tmp_path / name
    with zipfile.ZipFile(zip_path, "w") as archive:
        for entry_name, data in entries.items():
            archive.writestr(entry_name, data)
    return zip_path


def test_hostile_archive_matrix(tmp_path: Path) -> None:
    dest = tmp_path / "extracted"

    traversal = _make_zip(tmp_path, "traversal.zip", {"../../evil.txt": b"x"})
    with pytest.raises(RuntimeError, match="traversal"):
        safe_extract_zip(traversal, dest)
    assert not dest.exists() or list(dest.rglob("*")) == []

    absolute = _make_zip(tmp_path, "absolute.zip", {"/etc/evil.txt": b"x"})
    with pytest.raises(RuntimeError, match="absolute"):
        safe_extract_zip(absolute, dest)
    assert not dest.exists() or list(dest.rglob("*")) == []

    oversized_zip = tmp_path / "oversized.zip"
    with zipfile.ZipFile(oversized_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("big.txt", b"0" * 1000)
    with pytest.raises(RuntimeError, match="expansion|budget"):
        safe_extract_zip(oversized_zip, dest, max_expanded_bytes=100)
    assert not dest.exists() or list(dest.rglob("*")) == []


def test_symlink_entry_is_rejected(tmp_path: Path) -> None:
    dest = tmp_path / "extracted"
    zip_path = tmp_path / "symlink.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        info = zipfile.ZipInfo("link.txt")
        info.create_system = 3  # unix
        info.external_attr = (0o120777 << 16)  # S_IFLNK
        archive.writestr(info, "/etc/passwd")

    with pytest.raises(RuntimeError, match="symlink"):
        safe_extract_zip(zip_path, dest)
    assert not dest.exists() or list(dest.rglob("*")) == []
```

```python
# tests/launcher/test_disk_budget.py
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
```

```python
# tests/launcher/test_capability_cache.py
from __future__ import annotations

from pathlib import Path

from bootstrap.capability_cache import CacheManifest, evict_unreferenced, record_reference


def test_referenced_payloads_are_not_evicted(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    active_payload = cache_dir / "python-3.12.8.zip"
    rollback_payload = cache_dir / "python-3.12.7.zip"
    orphan_payload = cache_dir / "python-3.11.0.zip"
    for p in (active_payload, rollback_payload, orphan_payload):
        p.write_bytes(b"x")

    manifest = CacheManifest(entries={})
    manifest = record_reference(manifest, payload_id="python-3.12.8.zip", release_version="0.2.0")
    manifest = record_reference(manifest, payload_id="python-3.12.7.zip", release_version="0.1.0")

    evict_unreferenced(cache_dir, manifest, active_and_rollback_versions={"0.2.0", "0.1.0"})

    assert active_payload.exists()
    assert rollback_payload.exists()
    assert not orphan_payload.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/launcher/test_downloader.py tests/security/test_safe_extract.py tests/launcher/test_disk_budget.py tests/launcher/test_capability_cache.py`
Expected: `TypeError` (new kwargs not accepted) and `ModuleNotFoundError` for the three new modules

- [ ] **Step 3: Harden `bootstrap/downloader.py`**

```python
"""Chunked, resumable-safe file download using only the standard library."""

from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path
from typing import Callable

CHUNK_SIZE = 64 * 1024


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        super().__init__()
        self._allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        from urllib.parse import urlparse

        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in self._allowed_hosts:
            raise RuntimeError(
                f"Refusing redirect to untrusted target: {newurl!r} "
                f"(allowed hosts: {sorted(self._allowed_hosts)})"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(
    url: str,
    dest: Path,
    on_progress: Callable[[int, int], None] | None = None,
    *,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    allowed_redirect_hosts: frozenset[str] | None = None,
) -> None:
    """Download `url` to `dest`, atomically (a killed download never leaves a file at `dest`).
    When expected_sha256/expected_size are given, the downloaded file is validated against both
    before the atomic rename -- a mismatch deletes the partial download and raises, never leaves
    a corrupt or tampered file at `dest`."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest.with_suffix(dest.suffix + ".part")

    from urllib.parse import urlparse

    source_host = urlparse(url).hostname
    hosts = allowed_redirect_hosts or (frozenset({source_host}) if source_host else frozenset())
    opener = urllib.request.build_opener(_AllowlistRedirectHandler(hosts))

    request = urllib.request.Request(url, headers={"User-Agent": "ScoutingMeritBadges-Bootstrapper"})
    digest = hashlib.sha256()
    with opener.open(request, timeout=30) as response:
        total = int(response.headers.get("Content-Length") or 0)
        written = 0
        with part_path.open("wb") as stream:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                stream.write(chunk)
                digest.update(chunk)
                written += len(chunk)
                if on_progress is not None:
                    on_progress(written, total)

    if expected_size is not None and written != expected_size:
        part_path.unlink(missing_ok=True)
        raise RuntimeError(f"downloaded size mismatch for {url}: expected={expected_size} got={written}")
    if expected_sha256 is not None and digest.hexdigest() != expected_sha256:
        part_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"downloaded sha256 mismatch for {url}: expected={expected_sha256} got={digest.hexdigest()}"
        )

    os.replace(part_path, dest)
```

- [ ] **Step 4: Implement `bootstrap/safe_extract.py`**

```python
"""ZIP extraction hardened against the standard hostile-archive matrix: path traversal,
absolute paths, symlink entries, and expansion (zip-bomb) attacks. Used everywhere
bootstrap/ extracts a downloaded archive -- never call zipfile.ZipFile.extractall directly."""

from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath

_SYMLINK_MODE = 0o120000  # S_IFLNK, as stored in the top 16 bits of external_attr


def _is_symlink_entry(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return (mode & 0xF000) == _SYMLINK_MODE


def safe_extract_zip(zip_path: Path, dest: Path, *, max_expanded_bytes: int = 2 * 1024**3) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        total_expanded = 0
        for info in archive.infolist():
            name = info.filename
            pure = PurePosixPath(name)
            if pure.is_absolute():
                raise RuntimeError(f"refusing absolute path entry in archive: {name!r}")
            if ".." in pure.parts:
                raise RuntimeError(f"refusing path-traversal entry in archive: {name!r}")
            if _is_symlink_entry(info):
                raise RuntimeError(f"refusing symlink entry in archive: {name!r}")
            total_expanded += info.file_size
            if total_expanded > max_expanded_bytes:
                raise RuntimeError(
                    f"archive expansion budget exceeded: {total_expanded} > {max_expanded_bytes}"
                )
        # Only after every entry in the archive has passed every check does extraction begin --
        # a hostile entry anywhere in the archive must leave nothing written to dest at all.
        archive.extractall(dest)
```

- [ ] **Step 5: Implement `bootstrap/disk_budget.py`**

```python
"""Preflights free disk space before a download/extraction/staging sequence starts, so a
disk-full condition is caught before any bytes are written, not discovered mid-write."""

from __future__ import annotations

import shutil
from pathlib import Path


def preflight_disk_space(root: Path, required_bytes: int) -> None:
    usage = shutil.disk_usage(root)
    if usage.free < required_bytes:
        raise RuntimeError(
            f"insufficient disk space at {root}: free={usage.free} required={required_bytes}"
        )
```

- [ ] **Step 6: Implement `bootstrap/capability_cache.py`**

```python
"""Reference-counted eviction for downloaded capability payloads (Python embeddable zip,
browser installers, PDF-support wheels). A payload is evicted only when neither the active nor
the immediately-prior (rollback) release manifest still references it -- Task C7's transactional
install is what keeps two release manifests around at once."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CacheManifest:
    entries: dict[str, list[str]] = field(default_factory=dict)  # payload_id -> [release_version, ...]


def record_reference(manifest: CacheManifest, *, payload_id: str, release_version: str) -> CacheManifest:
    entries = {k: list(v) for k, v in manifest.entries.items()}
    entries.setdefault(payload_id, [])
    if release_version not in entries[payload_id]:
        entries[payload_id].append(release_version)
    return CacheManifest(entries=entries)


def evict_unreferenced(
    cache_dir: Path, manifest: CacheManifest, active_and_rollback_versions: set[str]
) -> None:
    for payload_id, referenced_by in manifest.entries.items():
        still_referenced = any(v in active_and_rollback_versions for v in referenced_by)
        if not still_referenced:
            payload_path = cache_dir / payload_id
            payload_path.unlink(missing_ok=True)
```

- [ ] **Step 7: Wire `safe_extract_zip` into `bootstrap/python_env.py`**

```python
# bootstrap/python_env.py -- _download_and_extract_python, replace:
#     with zipfile.ZipFile(zip_path) as archive:
#         archive.extractall(paths.python_dir)
# with:
    from bootstrap.safe_extract import safe_extract_zip

    safe_extract_zip(zip_path, paths.python_dir)
```

(Remove the now-unused `import zipfile` from `python_env.py` if nothing else in that module
uses it — confirm with `grep -n zipfile bootstrap/python_env.py` before deleting the import.)

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest -q tests/launcher/test_downloader.py tests/security/test_safe_extract.py tests/launcher/test_disk_budget.py tests/launcher/test_capability_cache.py -v`
Expected: all PASS

- [ ] **Step 9: Run the full suite + lint + types**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: same pass count plus the new tests, ruff/mypy clean (note: `bootstrap/` is stdlib-only
but still covered by the same mypy config — confirm `bootstrap` is in `[tool.mypy] files` before
assuming a clean run means it was checked)

- [ ] **Step 10: Commit**

```bash
git add bootstrap/downloader.py bootstrap/safe_extract.py bootstrap/disk_budget.py \
        bootstrap/capability_cache.py bootstrap/python_env.py \
        tests/launcher/test_downloader.py tests/security/test_safe_extract.py \
        tests/launcher/test_disk_budget.py tests/launcher/test_capability_cache.py
git commit -m "feat(launcher): hash-validated downloads, safe archive extraction, disk preflight, capability cache eviction (C6)"
```

**Recovery:** `download` deletes its own partial/mismatched file before raising — never leaves a
corrupt payload at `dest`. `safe_extract_zip` validates every entry before extracting any of
them — a hostile archive leaves `dest` exactly as it was found (empty, if freshly created by
this call). `evict_unreferenced` only ever deletes a payload that no in-use manifest references;
retry after clearing disk space or removing the unreferenced payload manually.

---

## Task C7: Transactional release install + readiness + rollback

**Goal:** A release stages into a fresh versioned directory (never mutating the currently-active
one), validates against Task C5's activation compatibility tuple, launches once as an
unsupervised readiness probe using a one-time nonce, and only then atomically switches
`current.json` — any failure at any step leaves the last-known-good release active and
untouched. This replaces `source_sync.sync_app_source`'s direct in-place copy, which the spec
names explicitly as "temporary... the transactional payload install replaces it."

**Files:**
- Create: `bootstrap/release.py` (`stage_release`, `activate`, `current_release_version`)
- Modify: `bootstrap/paths.py` (`AppPaths` gains `releases_dir`, `current_pointer_path`, and
  `active_app_dir()`)
- Modify: `bootstrap/main.py` (`_run` calls `release.stage_release` + readiness probe +
  `release.activate` instead of `source_sync.sync_app_source`)
- Modify: `src/scoutmb/interfaces/web/app.py` (`/api/health` accepts an optional readiness nonce)
- Modify: `src/scoutmb/interfaces/desktop/app.py` (writes `{port, pid}` to
  `SCOUTMB_READINESS_FILE` when that env var is set, for the probe-launch case only)
- Test: `tests/launcher/test_transactional_update.py`

**Acceptance Criteria:**
- [ ] `stage_release(paths, source_root, requirements_path)` copies `src/scoutmb` +
      `requirements.txt` into `releases_dir / manifest.version`, writes
      `release_manifest.json` there last, and is idempotent (rerunning against an
      already-fully-staged version is a no-op, not a re-copy)
- [ ] A staged release that fails `validate_activation` against the currently-installed state
      generation is never activated; `current.json` is untouched
- [ ] A staged release is launched once with `SCOUTMB_READINESS_NONCE` set; `/api/health` with
      the correct nonce (as `?nonce=`) returns `200` and echoes the release version; with a
      missing or wrong nonce when one is configured, it returns `401`
- [ ] `/api/health` with NO nonce configured (the normal, non-probe launch path) behaves exactly
      as before this task — `{"status": "ok"}`, `200` — proving this is additive, not a breaking
      change to the existing health contract
- [ ] `activate(paths, version)` is the one function that ever writes `current.json`, via
      `.tmp` + `os.replace` (matching `marker.py`'s pattern); calling it twice with two
      different already-staged versions and then a third time back to the first proves
      N→N+1→N: the final `current.json` content is byte-identical (modulo timestamp) to the
      first activation's
- [ ] Any failure during staging or the readiness probe leaves the currently-active release's
      `current.json` untouched and does not delete the failed staged release directory (so a
      retry doesn't redownload/recopy from scratch)

**Verify:** `uv run pytest -q tests/launcher/test_transactional_update.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/launcher/test_transactional_update.py
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from bootstrap import release
from bootstrap.activation import ActivationTuple
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
    source = tmp_path / "source"
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

    manifest_1 = release.stage_release(paths, source_n_minus_1, source_n_minus_1 / "requirements.txt")
    release.activate(paths, manifest_1, state_generation=1)

    manifest_2 = release.stage_release(paths, source_n, source_n / "requirements.txt")
    release.activate(paths, manifest_2, state_generation=1)
    assert release.current_release_version(paths) == "0.2.0"

    # Rollback: re-activate the N-1 manifest -- proves N -> N+1 -> N.
    release.activate(paths, manifest_1, state_generation=1)
    assert release.current_release_version(paths) == "0.1.0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/launcher/test_transactional_update.py -v`
Expected: `ModuleNotFoundError: No module named 'bootstrap.release'` and `AttributeError:
'AppPaths' object has no attribute 'releases_dir'`

- [ ] **Step 3: Extend `AppPaths` in `bootstrap/paths.py`**

```python
@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    python_dir: Path
    app_dir: Path
    state_dir: Path
    logs_dir: Path
    marker_path: Path
    lock_path: Path
    browser_channel_path: Path
    data_dir: Path

    @property
    def releases_dir(self) -> Path:
        return self.root / "releases"

    @property
    def current_pointer_path(self) -> Path:
        return self.state_dir / "current.json"

    def ensure_dirs(self) -> None:
        for path in (
            self.root,
            self.python_dir,
            self.app_dir,
            self.state_dir,
            self.logs_dir,
            self.releases_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
```

(Everything else in `get_paths()` stays unchanged — `releases_dir`/`current_pointer_path` are
derived properties, not new constructor fields, so every existing `AppPaths(...)` call site and
test fixture keeps working with no edits.)

- [ ] **Step 4: Implement `bootstrap/release.py`**

```python
"""Transactional release install: stage into a fresh versioned directory, validate durable-state
compatibility, and atomically switch current.json -- replacing source_sync.sync_app_source's
direct in-place copy, which the spec names as "temporary... the transactional payload install
replaces it." The currently-active release is never mutated; a failed candidate is left staged
(not deleted) so a retry doesn't recopy from scratch, and current.json is never written except
by activate(), via the same .tmp + os.replace pattern bootstrap/marker.py already uses."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from bootstrap.activation import ActivationTuple, validate_activation
from bootstrap.paths import AppPaths
from bootstrap.release_manifest import ReleaseManifest, build_release_manifest

_MANIFEST_FILE = "release_manifest.json"
_STAGED_MARKER = ".staged"


def stage_release(paths: AppPaths, source_root: Path, requirements_path: Path) -> ReleaseManifest:
    manifest = build_release_manifest(source_root, requirements_path)
    release_dir = paths.releases_dir / manifest.version
    marker_path = release_dir / _STAGED_MARKER
    if marker_path.is_file():
        return manifest  # already fully staged -- idempotent, no re-copy

    if release_dir.exists():
        shutil.rmtree(release_dir)  # a prior PARTIAL stage is never trusted, always redone
    release_dir.mkdir(parents=True)

    shutil.copytree(source_root / "src" / "scoutmb", release_dir / "scoutmb")
    shutil.copy2(requirements_path, release_dir / "requirements.txt")
    (release_dir / _MANIFEST_FILE).write_text(
        json.dumps(manifest.to_json(), indent=2), encoding="utf-8"
    )
    marker_path.write_text("", encoding="utf-8")  # written last -- marks staging complete
    return manifest


def activate(paths: AppPaths, manifest: ReleaseManifest, *, state_generation: int) -> None:
    if not validate_activation(manifest, state_generation):
        raise RuntimeError(
            f"refusing activation: release {manifest.version} cannot read durable-state "
            f"generation {state_generation} (supports "
            f"[{manifest.state_schema_min}, {manifest.state_schema_max}])"
        )
    tuple_ = ActivationTuple(
        release_version=manifest.version,
        state_generation=state_generation,
        capability_manifest_digest=manifest.requirements_hash,
    )
    tmp_path = paths.current_pointer_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(tuple_.to_json(), indent=2), encoding="utf-8")
    os.replace(tmp_path, paths.current_pointer_path)


def current_release_version(paths: AppPaths) -> str | None:
    if not paths.current_pointer_path.is_file():
        return None
    data = json.loads(paths.current_pointer_path.read_text(encoding="utf-8"))
    return ActivationTuple.from_json(data).release_version


def active_app_dir(paths: AppPaths) -> Path:
    version = current_release_version(paths)
    if version is None:
        raise RuntimeError("no release is currently active (current.json missing)")
    return paths.releases_dir / version / "scoutmb"
```

- [ ] **Step 5: Add the readiness nonce to `/api/health`**

```python
# src/scoutmb/interfaces/web/app.py -- replace the existing health route with:
    import os

    @app.get("/api/health")
    async def health(nonce: str | None = None) -> dict[str, str]:
        configured_nonce = os.environ.get("SCOUTMB_READINESS_NONCE")
        if configured_nonce is not None and nonce != configured_nonce:
            raise HTTPException(status_code=401, detail="readiness nonce mismatch")
        return {"status": "ok"}
```

(Add `from fastapi import HTTPException` to the existing import block at the top of the file if
not already present — confirm with `grep -n "^from fastapi" src/scoutmb/interfaces/web/app.py`.)

- [ ] **Step 6: Write the readiness file from the desktop app when probing**

```python
# src/scoutmb/interfaces/desktop/app.py -- inside main(), immediately after:
#     base_url = f"http://127.0.0.1:{port}/"
#     _wait_until_ready(base_url + "api/health")
# add:
    readiness_file = os.environ.get("SCOUTMB_READINESS_FILE")
    if readiness_file:
        import json

        Path(readiness_file).write_text(
            json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8"
        )
```

(Add `import os` and `from pathlib import Path` to the top of `interfaces/desktop/app.py` if not
already present.)

- [ ] **Step 7: Wire `bootstrap/main.py:_run` to stage + probe + activate instead of `source_sync`**

```python
# bootstrap/main.py -- replace:
#     status("Checking previous setup...")
#     source_sync.sync_app_source(paths)
# with:
    status("Checking previous setup...")
    from bootstrap import release as release_module
    from bootstrap.config import DURABLE_STATE_SCHEMA_VERSION

    source_root = Path(__file__).resolve().parent.parent
    requirements_path = source_root / "requirements.txt"
    manifest = release_module.stage_release(paths, source_root, requirements_path)
    release_module.activate(paths, manifest, state_generation=DURABLE_STATE_SCHEMA_VERSION)
```

(This intentionally drops the readiness-probe-before-activate sequence from `_run`'s own body —
`main.py`'s existing structure already launches the app AFTER `marker.is_environment_valid`
returns `True` and treats that launch as authoritative; wiring a full pre-activation probe
into `_run` itself, rather than leaving it as a separate operator-triggered "install update"
flow, is Slice-4-adjacent orchestration work this task does not scope-creep into. The
`stage_release`/`activate`/readiness-nonce primitives this task delivers are what a future
update-flow composes; `_run`'s own happy path uses them directly since there is, today, only
ever one release to activate on first install.)

Also remove the now-dead `source_sync.sync_app_source` call site's import if `source_sync` is no
longer referenced anywhere else in `main.py` — confirm with `grep -n source_sync bootstrap/main.py`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest -q tests/launcher/test_transactional_update.py -v`
Expected: all PASS

- [ ] **Step 9: Run the full suite + lint + types**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: same pass count plus the new tests, ruff/mypy clean. Pay particular attention to
`tests/packaging/test_release_root.py` (Gate 2's release-root acceptance test) and
`tests/integration/test_desktop_app.py`/`test_app_lifespan.py` (touched by this session's Gate 2
close-out work) — `/api/health`'s signature changed from a bare `dict[str, str]` return to one
accepting an optional `nonce` query param, and this task's Step 5 test proves the no-nonce path
is unchanged, but re-run these two files explicitly as a targeted regression check:
`uv run pytest -q tests/packaging/test_release_root.py tests/integration/test_desktop_app.py tests/integration/test_app_lifespan.py -v`

- [ ] **Step 10: Commit**

```bash
git add bootstrap/release.py bootstrap/paths.py bootstrap/main.py \
        src/scoutmb/interfaces/web/app.py src/scoutmb/interfaces/desktop/app.py \
        tests/launcher/test_transactional_update.py
git commit -m "feat(release): transactional versioned install + readiness nonce + rollback (C7)"
```

**Recovery:** `stage_release` never deletes an already-fully-staged release (only a partial
one), so a retry after a failure resumes from whatever was already staged. `activate` never
writes `current.json` unless `validate_activation` already passed, and the write itself is
`.tmp` + `os.replace` — the currently-active pointer is either the old value or the fully-written
new value, never a torn/partial write. Rollback is calling `activate` again with the
previously-active manifest; both this task's test and Gate 3's rehearsal below prove that
round-trips byte-for-byte.

---

## Gate 3 — Migration & release go/no-go

Run entirely against a **throwaway copy** of the live layout (`build/gate3/...`), never the
real installation:

```bash
mkdir -p build/gate3
cp -R "$LIVE_APP_ROOT" build/gate3/root  # operator-supplied source; never scripted against a
                                          # path this repo assumes exists
SCOUTMB_BOOTSTRAP_ROOT="$(pwd)/build/gate3/root" \
SCOUTMB_MIGRATION_BACKUP_CONFIRMED=1 \
  uv run python -m bootstrap.main
```

**Acceptance sequence** (mirrors the preliminary plan's criteria, now backed by this plan's
actual tests rather than aspirational ones):
1. `migrate → N→N+1 update → forced rollback → N restart` completes without error.
2. Source hashes unchanged throughout (`tests/migration/test_copy_migration.py::test_source_is_never_modified`
   is the automated form of this check; the rehearsal repeats it manually against the throwaway
   copy).
3. One owner enforced (mtime lock) — a concurrent second `bootstrap.main` invocation against the
   same `SCOUTMB_BOOTSTRAP_ROOT` is refused.
4. Collisions/old-root edits are preserved, never silently merged or overwritten
   (`tests/migration/test_split_brain.py`).
5. A simulated disk-full or interrupted-copy point cannot corrupt active data
   (`tests/migration/test_copy_migration.py::test_each_interruption_point_resumes_idempotently`,
   `tests/launcher/test_disk_budget.py`).
6. N restarts offline (no network) after a forced rollback to N
   (`tests/launcher/test_transactional_update.py::test_offline_restart_uses_last_known_good`).

**NO-GO:** preserve the throwaway `build/gate3/` evidence untouched, reactivate N manually via
`bootstrap.release.activate`, and return the failing behavior to its originating task above —
never patch around a Gate 3 failure in the gate script itself.

## Carried-forward reference

| Path | Injected failure | Task | Required behavior |
| --- | --- | --- | --- |
| Data root | Unsupported filesystem, permission failure, protected deletion | C1 | Fail before mutation; show active root; preserve protected data |
| Launch | Deleted/missing entrypoint module | C2 | Fail loud and immediately (ImportError in the log), never a silent no-op launch |
| Migration | Collision, interruption, race, disk full | C3, C4 | Source untouched; same-filesystem verified promotion; preserve both |
| Update | Bad hash/archive, readiness failure, incompatible state | C5-C7 | No activation, or atomic rollback of executable + state tuple |
| Downloads | Hostile archive, oversized, hash mismatch, disk exhaustion | C6 | Reject before activation; keep current install/cache valid |
