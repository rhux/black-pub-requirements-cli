# Slice 3 follow-up: launch/release-layout test gap

**Status: fix and tests landed 2026-08-26 (936 passed, no regressions). Gate 3
rehearsal below is still outstanding — operator-only, see that section.**

## Context

Slice 3's C7 task moved app source out of the static `paths.app_dir` and into
versioned release directories (`releases/<version>/scoutmb`), staged by
`bootstrap/release.stage_release` and switched over by `bootstrap/release.activate`.
The task's own retrospective flagged an untested integration gap: `_launch_app`
(bootstrap/main.py) and `python_env._patch_pth_file` (bootstrap/python_env.py)
were never updated to follow the new layout, and no test in the suite exercised
the real subprocess-launch path against a staged release. The recommendation was
to run this plan's Gate 3 rehearsal, which needs an operator-supplied copy of a
real live install.

Reading the code (bootstrap/main.py, release.py, python_env.py, paths.py)
confirmed the gap was real:

- `bootstrap/release.py:67-71` already defined `active_app_dir(paths)`, which
  correctly resolves `releases_dir / current_release_version(paths) / "scoutmb"`.
  It was never called anywhere.
- `_launch_app` (bootstrap/main.py:62) did `cwd=str(paths.app_dir)`.
- `_patch_pth_file` (bootstrap/python_env.py, was line 61) did
  `app_dir_str = str(paths.app_dir)`, written into the embeddable Python's
  `._pth` file as the only non-stdlib import path.
- `paths.app_dir` (bootstrap/paths.py:16, `root / "app"`) is a static,
  non-versioned directory. Since C7, nothing populates it — the old
  `source_sync.sync_app_source` that used to copy source into it is no longer
  called from `_run`. So on a fresh install it's created empty
  (`AppPaths.ensure_dirs()`), and both `_launch_app`'s `cwd` and the `._pth`
  entry pointed at an empty directory instead of the populated release dir.
- Call-order check in `_run` (bootstrap/main.py:81-119): `stage_release` +
  `activate` run unconditionally at the top, on *every* invocation, before
  either code path reaches `provision_python`/`_patch_pth_file` or
  `_launch_app`. So `current.json` always exists by the time either fix site
  runs — `active_app_dir(paths)` can be called directly, no need to thread a
  version through.
- Existing coverage didn't catch this: `tests/launcher/test_launch_command.py`
  built a synthetic `AppPaths`, monkeypatched `subprocess.Popen`, and only
  asserted on `argv`, never on `cwd`, and never ran a real `stage_release`/
  `activate` cycle first. There was no test at all for `_patch_pth_file`.

This was exactly the kind of gap that should be closed with an ordinary
automated regression test, not by waiting on a manual Gate 3 rehearsal —
Gate 3 (real live-install copy, operator-only, per this plan's own binding
constraint that it never runs against a scripted/assumed path) is a
higher-level sign-off, not the place to catch a wiring bug like this. So the
work below fixed the bug and added tmp_path-based integration tests that
exercise the real `stage_release → activate → _launch_app`/`_patch_pth_file`
chain — closing the specific gap called out, without needing operator access.
Gate 3 itself is still worth running before calling the slice fully done.

## Fix (landed)

1. **bootstrap/main.py `_launch_app`**: `cwd=str(paths.app_dir)` →
   `cwd=str(release_module.active_app_dir(paths))`. `release_module` was
   already imported.

2. **bootstrap/python_env.py `_patch_pth_file`**: `app_dir_str = str(paths.app_dir)`
   → `app_dir_str = str(release.active_app_dir(paths))`. This needed a
   *deferred* (function-local) `from bootstrap import release` import rather
   than a module-level one: `bootstrap.python_env` is imported by
   `bootstrap.marker` (for `smoke_test`), and `bootstrap.release` transitively
   imports `bootstrap.marker` via `activation` → `release_manifest` → `marker`
   — a module-level import created a circular-import `ImportError` on
   `smoke_test`. The fix imports `release` inside `_patch_pth_file`'s body,
   which resolves cleanly since by call time all modules have finished
   loading.

`paths.app_dir` itself was left as-is — it's still referenced by
`migrate.migrate_legacy_data(paths.app_dir, ...)` in `_run` as the legacy,
pre-versioned location to migrate *from*, unrelated to this bug.

## Tests (landed)

Both are pure `tmp_path` integration tests — real `stage_release`/`activate`
calls against a throwaway temp directory, no network, no operator step, no
live install:

1. `tests/launcher/test_launch_command.py::test_launch_uses_active_release_dir_as_cwd_after_staging`
   — stages and activates a release, monkeypatches `subprocess.Popen` to
   capture the `cwd` kwarg, asserts it equals `release_module.active_app_dir(paths)`
   and explicitly differs from `paths.app_dir`. Skipped on macOS
   (`pytest.importorskip("winreg")`, since `bootstrap.main` transitively
   imports `bootstrap.webview2` → `winreg`) — only actually runs on Windows or
   in a Windows CI lane.

2. `tests/launcher/test_python_env_pth.py::test_patch_pth_file_points_at_active_release_dir`
   (new file) — stages and activates a release, writes a placeholder `._pth`
   file, calls `_patch_pth_file`, asserts the appended path equals
   `active_app_dir(paths)` and not `paths.app_dir`. Runs on macOS too (no
   Windows-only imports in this chain).

Verification: RED confirmed against the unmodified code first (both tests
failed for the expected reason), then GREEN after the fix
(`tests/launcher/` + `tests/storage/`: 13 passed, 3 skipped). Full suite:
936 passed, 5 skipped, 3 deselected, no regressions.

## Gate 3 (still outstanding — manual, operator-only)

The landed tests close the specific "no test exercises the real launch" gap
and catch this exact class of bug going forward, but they still run against
synthetic fixtures. This plan's own Gate 3 rehearsal
(`docs/superpowers/plans/2026-07-22-slice-3-storage-migration-releases.md`,
lines 2069-2101) is the actual end-to-end sanity check against a real
installed layout, and per that doc's binding constraint it must never run
against a scripted/assumed path — only a throwaway copy of a real live
install, which only the operator can supply. Once you have access to a real
installed `$LIVE_APP_ROOT` (e.g. on the Windows machine where this was last
installed), run:

```bash
mkdir -p build/gate3
cp -R "$LIVE_APP_ROOT" build/gate3/root   # never run this against the real path directly
SCOUTMB_BOOTSTRAP_ROOT="$(pwd)/build/gate3/root" \
SCOUTMB_MIGRATION_BACKUP_CONFIRMED=1 \
  uv run python -m bootstrap.main
```

and step through the six-point acceptance sequence in that section of the
plan doc (migrate → update → forced rollback → restart; source hashes
unchanged; single-owner lock enforced; collisions preserved; disk-full/
interrupted-copy resilience; offline restart after rollback). On any failure,
preserve `build/gate3/` untouched, reactivate the last-known-good release via
`bootstrap.release.activate`, and route the failure back to its originating
task rather than patching around it in the gate script.
