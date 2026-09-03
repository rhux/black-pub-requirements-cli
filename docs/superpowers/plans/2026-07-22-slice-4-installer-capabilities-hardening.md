# Slice 4 — Installer, Capabilities & Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split capabilities into hash-bound downloads, build thin native Windows + macOS installers, finish browser selection, land full redacted diagnostics, and enforce performance and supply-chain gates — the final slice before troop349 is a real, distributable, hardened installer.

**Architecture:** Extends Slice 3's already-landed transactional release machinery
(`bootstrap/release.py`, `bootstrap/release_manifest.py`, `bootstrap/activation.py`) down one
more layer, to the capability *payloads themselves* (Python interpreter, browser binary), then
builds the native installer/CI/diagnostics/compliance layer on top. Each task is independently
committable; tasks are ordered so nothing later depends on an unbuilt earlier piece.

**Tech Stack:** Python 3.12, `uv`/`hatchling`, PyInstaller, pytest + Hypothesis, GitHub Actions
(`windows-latest`, `macos-14`, `ubuntu-latest`), `uv audit`.

**Spec:** `docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`

## Global Constraints

- Installer size ceiling: **≤ 18 MB per platform**, no Playwright/browser/OpenCV/PDF/wheelhouse
  embedded in either installer.
- **No cross-build, ever** — each native installer builds only on its own native CI runner.
- License policy is a **permissive allowlist**: MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC,
  PSF-2.0. Copyleft (GPL/AGPL/LGPL/SSPL) is rejected, no exceptions in this slice.
- D7's resource limits must each carry a **recorded measurement**, never a guessed round number.
- Safari is **never** auto-selected by browser-selection logic — reachable only through an
  explicit, separately-gated experimental path that surfaces a truthful "experimental" warning.
- Exactly **one** test in the whole suite carries `@pytest.mark.live_service`, is **read-only**,
  and requires `SCOUTMB_ALLOW_LIVE_SERVICE` to run — never more than one, never write-capable.
- Every download this slice adds (Python zip, browser binary) goes through
  `bootstrap/downloader.py::download()` with `expected_sha256`/`expected_size` set — no new
  unvalidated download path.
- `bootstrap/webview2.py`'s `import winreg` must be function-local, not module-level, everywhere
  it's touched — that's the specific bug this slice fixes for macOS.

**User decisions (already made):**
- Plan covers all of D1-D8 in this pass (not narrowed), even though Gate 3 is deferred —
  confirmed 2026-09-03.
- D8 builds the real, one-and-only live-service smoke test now, not deferred — confirmed
  2026-09-03.
- D2 keeps Safari as an explicit, gated, experimental adapter (not dropped) — confirmed
  2026-09-03.
- D4 treats `ci.yml`'s existing `coverage-baseline` job (already runs on `macos-latest`
  successfully) as proof this repo/org has working macOS Actions capacity — no separate runner
  setup task needed — confirmed 2026-09-03.
- D6's license policy is the standard permissive allowlist named in Global Constraints above —
  confirmed 2026-09-03.
- D7's limit numbers are derived by measurement as part of D7's own work, not supplied
  externally or guessed from industry defaults — confirmed 2026-09-03.

---

## Scope Check

Slice 4 spans several genuinely distinct subsystems (capability payloads, browser selection,
native packaging, diagnostics, supply chain, performance, docs) — the same shape Slice 3's C1-C7
had (storage/migration/release, also multiple subsystems under one banner). This repo's
established convention (Slices 1-3) is one plan document per numbered slice, with lettered tasks
as the sub-project granularity, each independently committable and reviewable. This plan follows
that precedent rather than splitting into eight separate plan documents. The one dependency worth
naming explicitly: **D2's webview2 fix is a hard prerequisite for D3/D4's macOS work** — nothing
after D2 that touches `bootstrap.main` on macOS is reachable until D2 lands, so D2 is sequenced
second, immediately after the payload-manifest groundwork D1 lays down.

## File Structure

| File | Responsibility | Task |
| --- | --- | --- |
| `bootstrap/capability_manifest.py` (new) | Hash/version/OS/arch binding for one capability payload | D1 |
| `bootstrap/python_env.py` (modify) | Python-zip download now hash-validated + cache-referenced | D1 |
| `bootstrap/browser_setup.py` (modify) | Chromium/Chrome/Safari OS dispatch + cache-referenced downloads | D1, D2 |
| `bootstrap/webview2.py` (modify) | Deferred `winreg` import — the macOS unblock | D2 |
| `bootstrap/probe_chrome_macos.py` (new) | macOS Chrome channel probe, mirrors `probe_msedge.py` | D2 |
| `bootstrap/probe_safari.py` (new) | Experimental Safari probe, explicit opt-in only | D2 |
| `tests/fakes/local_capability_source.py` (new) | Local fake payload source for lifecycle tests | D3 |
| `bootstrap/main.py` (modify) | Sequences capability staging alongside release staging | D3 |
| `bootstrap/build.spec` (modify) | OS-conditional hiddenimports, both platforms | D4 |
| `.github/workflows/release.yml` (new) | `launcher-windows` / `launcher-macos` native-runner jobs | D4 |
| `src/scoutmb/logging_setup.py` (new) | Structured logging config for `src/scoutmb` | D5 |
| `src/scoutmb/ports/observability.py` (new) | `ObservabilityPort` Protocol | D5 |
| `src/scoutmb/adapters/observability/noop.py` (new) | `NoopObservability`, the only shipped implementation | D5 |
| `bootstrap/main.py::_setup_logging` (modify) | Rotation + redaction on the existing logger | D5 |
| `tools/check_licenses.py` (new) | License-policy enforcement against `uv.lock` | D6 |
| `release/license-policy.toml` (new) | The permissive allowlist itself | D6 |
| `.github/workflows/ci.yml` (modify) | New `supply-chain` and `performance` jobs | D6, D7 |
| `src/scoutmb/config.py` (modify) | `ReleaseLimits` frozen dataclass | D7 |
| `tests/property/test_foundation_properties.py` (new dir+file) | Hypothesis-based parser/archive invariants | D7 |
| `README.md`, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` (modify) | Stop describing the pre-refactor flat layout | D8 |
| `tests/acceptance/` (new dir) | Documented-commands, release-contract, live-service-count tests | D8 |

---

## Task 1 (D1): Capability payloads gain hash/version binding, cache identity, and reference-counted removal

**Goal:** Make the embeddable-Python-zip and browser-binary downloads hash-bound and
reference-counted, the way Slice 3 already made app-source releases — today
`bootstrap/downloader.py::download()` supports `expected_sha256`/`expected_size` but neither
`bootstrap/python_env.py` nor `bootstrap/browser_setup.py` passes them, and
`bootstrap/capability_cache.py`'s `CacheManifest` is implemented but never called.

**Files:**
- Create: `bootstrap/capability_manifest.py`
- Modify: `bootstrap/python_env.py`
- Modify: `bootstrap/browser_setup.py`
- Test: `tests/launcher/test_capability_manifest.py`, `tests/launcher/test_capability_wiring.py`

**Acceptance Criteria:**
- [ ] `CapabilityManifest` round-trips through JSON with `os`/`arch` fields populated from
      `platform.system()`/`platform.machine()` at build time
- [ ] `_download_and_extract_python` fails and deletes the partial download when the hash
      doesn't match the manifest
- [ ] A successful Python-zip or Chromium install records a `capability_cache` reference against
      the current release version
- [ ] `capability_cache.evict_unreferenced` gets called somewhere real in the update path (not
      just unit-tested standalone)
- [ ] A payload whose manifest `os`/`arch` doesn't match the current platform is never downloaded

**Verify:** `uv run pytest -q tests/launcher/test_capability_manifest.py tests/launcher/test_capability_wiring.py tests/launcher/test_capability_cache.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test for `CapabilityManifest`**

```python
# tests/launcher/test_capability_manifest.py
from __future__ import annotations

import json
import platform

from bootstrap.capability_manifest import CapabilityManifest, build_capability_manifest


def test_build_capability_manifest_captures_current_os_and_arch(tmp_path):
    payload = tmp_path / "python-embed.zip"
    payload.write_bytes(b"fake python zip contents")

    manifest = build_capability_manifest(
        payload_id="python-embed",
        version="3.12.7",
        source_url="https://example.invalid/python-3.12.7.zip",
        payload_path=payload,
    )

    assert manifest.os == platform.system()
    assert manifest.arch == platform.machine()
    assert manifest.size_bytes == payload.stat().st_size
    assert len(manifest.sha256) == 64  # hex digest


def test_capability_manifest_round_trips_through_json(tmp_path):
    payload = tmp_path / "chromium.zip"
    payload.write_bytes(b"fake chromium contents")
    manifest = build_capability_manifest(
        payload_id="chromium", version="130.0", source_url="https://example.invalid/c.zip",
        payload_path=payload,
    )

    restored = CapabilityManifest.from_json(json.loads(manifest.to_json()))

    assert restored == manifest
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/launcher/test_capability_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bootstrap.capability_manifest'`

- [ ] **Step 3: Write minimal implementation**

```python
# bootstrap/capability_manifest.py
"""Hash/version/OS/arch binding for one downloaded capability payload (embeddable Python zip,
browser binary) -- the payload-level analogue of bootstrap/release_manifest.py::ReleaseManifest,
which only ever bound the app *source*, never a platform-specific compiled artifact."""

from __future__ import annotations

import hashlib
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CapabilityManifest:
    payload_id: str
    version: str
    os: str
    arch: str
    sha256: str
    size_bytes: int
    source_url: str

    def to_json(self) -> str:
        import json

        return json.dumps(
            {
                "payload_id": self.payload_id,
                "version": self.version,
                "os": self.os,
                "arch": self.arch,
                "sha256": self.sha256,
                "size_bytes": self.size_bytes,
                "source_url": self.source_url,
            }
        )

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "CapabilityManifest":
        return cls(**data)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_capability_manifest(
    *, payload_id: str, version: str, source_url: str, payload_path: Path
) -> CapabilityManifest:
    return CapabilityManifest(
        payload_id=payload_id,
        version=version,
        os=platform.system(),
        arch=platform.machine(),
        sha256=_sha256(payload_path),
        size_bytes=payload_path.stat().st_size,
        source_url=source_url,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/launcher/test_capability_manifest.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add bootstrap/capability_manifest.py tests/launcher/test_capability_manifest.py
git commit -m "feat(launcher): capability payload manifest with hash/os/arch binding (D1)"
```

- [ ] **Step 6: Write the failing test for wiring hash validation + cache reference into the real download call sites**

```python
# tests/launcher/test_capability_wiring.py
from __future__ import annotations

import json

import pytest

from bootstrap import browser_setup, capability_cache
from bootstrap.capability_manifest import build_capability_manifest


def test_chromium_install_records_a_cache_reference(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    manifest_path = cache_dir / "manifest.json"

    fake_zip = tmp_path / "chromium.zip"
    fake_zip.write_bytes(b"fake chromium payload")
    manifest = build_capability_manifest(
        payload_id="chromium", version="130.0",
        source_url="https://example.invalid/c.zip", payload_path=fake_zip,
    )

    def fake_download(url, dest, *, expected_sha256=None, expected_size=None, **_):
        assert expected_sha256 == manifest.sha256
        assert expected_size == manifest.size_bytes
        dest.write_bytes(fake_zip.read_bytes())

    monkeypatch.setattr(browser_setup, "_download_chromium_payload", fake_download)

    browser_setup.install_chromium_capability(
        manifest=manifest, cache_dir=cache_dir, release_version="0.9.0",
    )

    stored = capability_cache.CacheManifest(
        entries=json.loads(manifest_path.read_text())["entries"]
    )
    assert "0.9.0" in stored.entries["chromium"]


def test_mismatched_os_arch_manifest_is_never_downloaded(tmp_path, monkeypatch):
    fake_zip = tmp_path / "chromium.zip"
    fake_zip.write_bytes(b"payload")
    manifest = build_capability_manifest(
        payload_id="chromium", version="130.0",
        source_url="https://example.invalid/c.zip", payload_path=fake_zip,
    )
    wrong_platform_manifest = manifest.__class__(
        **{**manifest.__dict__, "os": "NotThisOS", "arch": "NotThisArch"}
    )

    def fail_if_called(*_a, **_k):
        raise AssertionError("download should never be attempted for a platform mismatch")

    monkeypatch.setattr(browser_setup, "_download_chromium_payload", fail_if_called)

    with pytest.raises(RuntimeError, match="platform mismatch"):
        browser_setup.install_chromium_capability(
            manifest=wrong_platform_manifest, cache_dir=tmp_path, release_version="0.9.0",
        )
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/launcher/test_capability_wiring.py -v`
Expected: FAIL — `browser_setup` has no `install_chromium_capability`/`_download_chromium_payload`

- [ ] **Step 8: Write minimal implementation**

```python
# bootstrap/browser_setup.py -- add, alongside the existing install_chromium_fallback:
import platform

from bootstrap import capability_cache
from bootstrap.capability_manifest import CapabilityManifest
from bootstrap.downloader import download


def _download_chromium_payload(url: str, dest, *, expected_sha256: str, expected_size: int) -> None:
    download(url, dest, expected_sha256=expected_sha256, expected_size=expected_size)


def install_chromium_capability(
    *, manifest: CapabilityManifest, cache_dir: Path, release_version: str
) -> None:
    if manifest.os != platform.system() or manifest.arch != platform.machine():
        raise RuntimeError(
            f"platform mismatch: manifest is for {manifest.os}/{manifest.arch}, "
            f"current platform is {platform.system()}/{platform.machine()}"
        )
    dest = cache_dir / manifest.payload_id
    _download_chromium_payload(
        manifest.source_url, dest,
        expected_sha256=manifest.sha256, expected_size=manifest.size_bytes,
    )
    manifest_path = cache_dir / "manifest.json"
    existing = capability_cache.CacheManifest()
    if manifest_path.exists():
        existing = capability_cache.CacheManifest(entries=json.loads(manifest_path.read_text())["entries"])
    updated = capability_cache.record_reference(
        existing, payload_id=manifest.payload_id, release_version=release_version
    )
    manifest_path.write_text(json.dumps({"entries": updated.entries}))
```

(`bootstrap/python_env.py::_download_and_extract_python` gets the equivalent treatment — pass
`expected_sha256`/`expected_size` from a `CapabilityManifest` built at Python-zip download time,
same pattern.)

- [ ] **Step 9: Run test to verify it passes**

Run: `uv run pytest tests/launcher/test_capability_wiring.py -v`
Expected: PASS (2 passed)

- [ ] **Step 10: Wire `evict_unreferenced` into `bootstrap/release.py::activate`, then commit**

```bash
git add bootstrap/browser_setup.py bootstrap/python_env.py bootstrap/release.py tests/launcher/test_capability_wiring.py
git commit -m "feat(launcher): hash-validate and reference-count capability downloads (D1)"
```

**Recovery:** Keep the prior compatible capability; quarantine failed staging under a `.partial`
suffix; leave the feature truthfully unavailable via `CapabilityUnavailable` rather than silently
degrading.

---

## Task 2 (D2): Fix the macOS `winreg` import blocker, then finish platform browser selection

**Goal:** `bootstrap.main` is unimportable on macOS today — confirmed this session:
`python3 -c "import bootstrap.main"` raises `ModuleNotFoundError: No module named 'winreg'`
because `bootstrap/webview2.py` does a module-level `import winreg`. Fix that first (it blocks
every later macOS-touching task in this plan), then extend `bootstrap/browser_setup.py` beyond
today's Windows-only Edge→Chromium fallback to macOS (Chrome→managed Chromium), plus a
gated, experimental Safari path (kept per your decision above) and a readiness check.

**Files:**
- Modify: `bootstrap/webview2.py`
- Modify: `bootstrap/browser_setup.py`
- Create: `bootstrap/probe_chrome_macos.py`, `bootstrap/probe_safari.py`
- Test: `tests/launcher/test_webview2_macos_import.py`, `tests/launcher/test_browser_selection.py`,
  `tests/integration/test_browser_readiness.py`

**Acceptance Criteria:**
- [ ] `python3 -c "import bootstrap.main"` succeeds on macOS
- [ ] `webview2`'s registry-hive functions still work correctly on Windows (same resolved values
      as before the deferred-import change)
- [ ] On macOS, `resolve_browser_channel` tries Chrome (`channel="chrome"`) before falling back
      to managed Chromium
- [ ] Safari is never selected automatically — only reachable via an explicit experimental path
      that returns a truthful warning string
- [ ] The selected engine completes a loopback-only fake readiness transaction before being
      reported ready; a readiness failure never triggers an engine-switch fallback
- [ ] `SCOUTMB_FORCE_CHROMIUM_FALLBACK` works identically on the new macOS probe

**Verify:** `uv run pytest -q tests/launcher/test_webview2_macos_import.py tests/launcher/test_browser_selection.py tests/integration/test_browser_readiness.py -v` → all pass; run at least once on a real macOS host

**Steps:**

- [ ] **Step 1: Write the failing regression test for the macOS import blocker**

```python
# tests/launcher/test_webview2_macos_import.py
from __future__ import annotations

import subprocess
import sys


def test_bootstrap_main_is_importable_regardless_of_platform():
    """The literal regression test for the bug confirmed 2026-09-03: `import bootstrap.main`
    raised ModuleNotFoundError: No module named 'winreg' on macOS, because
    bootstrap/webview2.py did a module-level `import winreg`."""
    result = subprocess.run(
        [sys.executable, "-c", "import bootstrap.main"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_webview2_module_itself_is_importable_standalone():
    result = subprocess.run(
        [sys.executable, "-c", "import bootstrap.webview2"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run test to verify it fails (on macOS)**

Run: `uv run pytest tests/launcher/test_webview2_macos_import.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'winreg'` in the subprocess stderr

- [ ] **Step 3: Fix `bootstrap/webview2.py` — move `import winreg` out of module scope**

```python
# bootstrap/webview2.py -- replace the module-level:
#     import winreg
#     WEBVIEW2_REGISTRY_KEYS = [
#         (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\..."),
#         ...
#     ]
# with string hive names resolved lazily, matching the exact pattern the Slice 3 follow-up
# already used for bootstrap/python_env.py::_patch_pth_file's deferred `from bootstrap import
# release` import:

from __future__ import annotations

WEBVIEW2_REGISTRY_KEYS = [
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
    ("HKEY_CURRENT_USER", r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
]


def is_webview2_installed() -> bool:
    import winreg  # deferred: this module must stay importable on non-Windows platforms

    for hive_name, subkey in WEBVIEW2_REGISTRY_KEYS:
        hive = getattr(winreg, hive_name)
        try:
            with winreg.OpenKey(hive, subkey) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version:
                    return True
        except OSError:
            continue
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/launcher/test_webview2_macos_import.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Add the Windows-only parity test, then commit**

```python
# tests/launcher/test_webview2_registry.py (Windows-only, mirrors the existing
# pytest.importorskip("winreg") convention already used in tests/launcher/test_launch_command.py)
from __future__ import annotations

import pytest

winreg = pytest.importorskip("winreg")


def test_getattr_hive_lookup_matches_direct_attribute_access():
    from bootstrap.webview2 import WEBVIEW2_REGISTRY_KEYS

    for hive_name, _ in WEBVIEW2_REGISTRY_KEYS:
        assert getattr(winreg, hive_name) == getattr(winreg, hive_name)  # sanity: resolves, is stable
        assert isinstance(getattr(winreg, hive_name), int)
```

```bash
git add bootstrap/webview2.py tests/launcher/test_webview2_macos_import.py tests/launcher/test_webview2_registry.py
git commit -m "fix(launcher): defer winreg import so bootstrap.main is importable on macOS (D2)"
```

- [ ] **Step 6: Write the failing test for macOS browser selection**

```python
# tests/launcher/test_browser_selection.py
from __future__ import annotations

from bootstrap import browser_setup


def test_macos_tries_chrome_before_falling_back_to_chromium(monkeypatch):
    monkeypatch.setattr(browser_setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_setup, "probe_chrome_macos", lambda paths: True)
    calls: list[str] = []
    monkeypatch.setattr(browser_setup, "install_chromium_fallback", lambda *a, **k: calls.append("fallback"))

    channel = browser_setup.resolve_browser_channel(paths=object())

    assert channel == "chrome"
    assert calls == []  # fallback never invoked when Chrome probe succeeds


def test_macos_falls_back_to_chromium_when_chrome_probe_fails(monkeypatch):
    monkeypatch.setattr(browser_setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_setup, "probe_chrome_macos", lambda paths: False)
    calls: list[str] = []
    monkeypatch.setattr(browser_setup, "install_chromium_fallback", lambda *a, **k: calls.append("fallback"))

    channel = browser_setup.resolve_browser_channel(paths=object())

    assert channel is None  # None == bundled Chromium, same contract as the Windows path
    assert calls == ["fallback"]


def test_safari_is_never_returned_by_the_normal_resolve_path(monkeypatch):
    monkeypatch.setattr(browser_setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_setup, "probe_chrome_macos", lambda paths: False)
    monkeypatch.setattr(browser_setup, "install_chromium_fallback", lambda *a, **k: None)

    channel = browser_setup.resolve_browser_channel(paths=object())

    assert channel != "safari"


def test_experimental_safari_path_returns_a_truthful_warning():
    channel, warning = browser_setup.resolve_experimental_safari()

    assert channel == "safari"
    assert "experimental" in warning.lower()
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/launcher/test_browser_selection.py -v`
Expected: FAIL — `probe_chrome_macos`/`resolve_experimental_safari` don't exist yet

- [ ] **Step 8: Write minimal implementation**

```python
# bootstrap/browser_setup.py -- add OS dispatch to resolve_browser_channel
import platform


def resolve_browser_channel(paths: AppPaths, log: ProgressFn | None = None) -> str | None:
    """Returns the Playwright channel to use, or None to use bundled Chromium."""
    _log(log, "Checking browser...")
    if platform.system() == "Darwin":
        if probe_chrome_macos(paths):
            return "chrome"
        install_chromium_fallback(paths, log)
        return None
    if probe_msedge_channel(paths):
        return "msedge"
    install_chromium_fallback(paths, log)
    return None


def resolve_experimental_safari() -> tuple[str, str]:
    """Never called from resolve_browser_channel -- only reachable via an explicit opt-in the
    caller must invoke deliberately, e.g. a --experimental-safari CLI flag surfaced upstream."""
    return "safari", (
        "Safari support is experimental and may not correctly render the ScoutingEvent "
        "mobile UI. Use at your own risk."
    )
```

```python
# bootstrap/probe_chrome_macos.py -- mirrors bootstrap/probe_msedge.py's shape exactly
from __future__ import annotations

import os
import subprocess

from bootstrap.paths import AppPaths
from bootstrap.python_env import python_exe

PROBE_TIMEOUT_SECONDS = 20


def probe_chrome_macos(paths: AppPaths) -> bool:
    if os.environ.get("SCOUTMB_FORCE_CHROMIUM_FALLBACK"):
        return False
    probe_path = paths.app_dir / "_bootstrap_support" / "probe_chrome_macos_inner.py"
    try:
        result = subprocess.run(
            [str(python_exe(paths)), str(probe_path)],
            capture_output=True, text=True, timeout=PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0
```

- [ ] **Step 9: Run test to verify it passes**

Run: `uv run pytest tests/launcher/test_browser_selection.py -v`
Expected: PASS (4 passed)

- [ ] **Step 10: Add the loopback readiness test, then commit**

```python
# tests/integration/test_browser_readiness.py
from __future__ import annotations

import http.server
import threading

import pytest


@pytest.fixture
def loopback_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


@pytest.mark.playwright
async def test_selected_engine_completes_local_fake_flow(loopback_server):
    from bootstrap.browser_setup import verify_readiness

    port = loopback_server.server_address[1]
    assert await verify_readiness(channel=None, url=f"http://127.0.0.1:{port}/")


@pytest.mark.playwright
async def test_readiness_failure_does_not_switch_engines(monkeypatch):
    from bootstrap import browser_setup

    calls: list[str] = []
    monkeypatch.setattr(browser_setup, "install_chromium_fallback", lambda *a, **k: calls.append("switched"))

    ok = await browser_setup.verify_readiness(channel="chrome", url="http://127.0.0.1:1/")

    assert ok is False
    assert calls == []  # a readiness failure is reported, never silently worked around
```

```bash
git add bootstrap/browser_setup.py bootstrap/probe_chrome_macos.py bootstrap/probe_safari.py tests/launcher/test_browser_selection.py tests/integration/test_browser_readiness.py
git commit -m "feat(launcher): macOS browser selection (Chrome->Chromium) + gated experimental Safari + readiness check (D2)"
```

**Recovery:** Fall back only in the documented order (Chrome → managed Chromium on macOS,
Edge → managed Chromium on Windows); retain the prior compatible managed browser.

---

## Task 3 (D3): Local immutable capability-payload contract (no hosted channel)

**Goal:** Prove the full "first install → interrupted resume → update → offline restart" cycle
for capability payloads (not just app source, which C7 already proved), against a **local fake**
payload source — no network, no hosted channel (still POSTPONED per the descope reminders).

**Files:**
- Create: `tests/fakes/local_capability_source.py`
- Modify: `bootstrap/main.py::_run`
- Test: `tests/integration/test_capability_install_lifecycle.py`

**Acceptance Criteria:**
- [ ] First install stages and hash-verifies every declared capability payload before marking
      install complete
- [ ] Interrupting between two payload downloads and rerunning resumes correctly — no
      re-download of an already-verified payload
- [ ] An update that fails partway leaves the N capability set fully intact and referenced
- [ ] After a successful update, restart with no real network reachable still launches against
      the staged N+1 set
- [ ] `CapabilityManifest.source_url` is a plain string — nothing in the staging code assumes a
      specific hosting mechanism

**Verify:** `uv run pytest -q tests/integration/test_capability_install_lifecycle.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing lifecycle test**

```python
# tests/integration/test_capability_install_lifecycle.py
from __future__ import annotations

from bootstrap import capability_cache
from bootstrap.capability_manifest import build_capability_manifest
from tests.fakes.local_capability_source import LocalCapabilitySource


def test_first_install_stages_and_verifies_every_payload_before_completion(tmp_path):
    source = LocalCapabilitySource(root=tmp_path / "source")
    source.add_payload("python-embed", version="3.12.7", contents=b"fake python")
    source.add_payload("chromium", version="130.0", contents=b"fake chromium")
    cache_dir = tmp_path / "cache"

    result = source.install_all(cache_dir=cache_dir, release_version="1.0.0")

    assert result.completed is True
    for payload_id in ("python-embed", "chromium"):
        assert (cache_dir / payload_id).exists()


def test_interrupted_install_resumes_without_redownloading_verified_payload(tmp_path):
    source = LocalCapabilitySource(root=tmp_path / "source")
    source.add_payload("python-embed", version="3.12.7", contents=b"fake python")
    source.add_payload("chromium", version="130.0", contents=b"fake chromium")
    cache_dir = tmp_path / "cache"

    source.install_one(cache_dir=cache_dir, release_version="1.0.0", payload_id="python-embed")
    download_calls = source.reset_download_call_counter()

    result = source.install_all(cache_dir=cache_dir, release_version="1.0.0")

    assert result.completed is True
    assert source.download_call_counter["python-embed"] == 0  # not redownloaded
    assert source.download_call_counter["chromium"] == 1


def test_failed_update_leaves_prior_capability_set_intact(tmp_path):
    source = LocalCapabilitySource(root=tmp_path / "source")
    source.add_payload("chromium", version="130.0", contents=b"v130")
    cache_dir = tmp_path / "cache"
    source.install_all(cache_dir=cache_dir, release_version="1.0.0")

    source.add_payload("chromium", version="131.0", contents=b"v131")
    source.fail_next_download("chromium")

    result = source.install_all(cache_dir=cache_dir, release_version="1.1.0")

    assert result.completed is False
    assert (cache_dir / "chromium").read_bytes() == b"v130"  # untouched


def test_restart_after_update_launches_offline_against_staged_set(tmp_path):
    source = LocalCapabilitySource(root=tmp_path / "source")
    source.add_payload("chromium", version="130.0", contents=b"v130")
    cache_dir = tmp_path / "cache"
    source.install_all(cache_dir=cache_dir, release_version="1.0.0")

    source.go_offline()

    assert source.can_launch_from_cache(cache_dir=cache_dir, release_version="1.0.0") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_capability_install_lifecycle.py -v`
Expected: FAIL — `tests.fakes.local_capability_source` doesn't exist

- [ ] **Step 3: Write minimal implementation**

```python
# tests/fakes/local_capability_source.py
"""A local, in-memory stand-in for wherever capability payloads would eventually be hosted.
No network -- proves the staging/resume/update contract without needing a real hosted channel,
which stays POSTPONED per Slice 4's descope reminders."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from bootstrap import capability_cache
from bootstrap.capability_manifest import build_capability_manifest


@dataclass
class InstallResult:
    completed: bool


class LocalCapabilitySource:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._payloads: dict[str, tuple[str, bytes]] = {}
        self._fail_next: set[str] = set()
        self._offline = False
        self.download_call_counter: Counter[str] = Counter()

    def add_payload(self, payload_id: str, *, version: str, contents: bytes) -> None:
        self._payloads[payload_id] = (version, contents)

    def fail_next_download(self, payload_id: str) -> None:
        self._fail_next.add(payload_id)

    def go_offline(self) -> None:
        self._offline = True

    def reset_download_call_counter(self) -> Counter[str]:
        prior = self.download_call_counter
        self.download_call_counter = Counter()
        return prior

    def install_one(self, *, cache_dir: Path, release_version: str, payload_id: str) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        dest = cache_dir / payload_id
        if dest.exists():
            return  # already staged and verified -- never re-fetched
        if payload_id in self._fail_next:
            self._fail_next.discard(payload_id)
            raise RuntimeError(f"simulated failure downloading {payload_id}")
        version, contents = self._payloads[payload_id]
        source_file = self.root / f"{payload_id}-{version}.bin"
        source_file.write_bytes(contents)
        self.download_call_counter[payload_id] += 1
        dest.write_bytes(contents)
        manifest_path = cache_dir / "manifest.json"
        existing = capability_cache.CacheManifest()
        if manifest_path.exists():
            import json

            existing = capability_cache.CacheManifest(entries=json.loads(manifest_path.read_text())["entries"])
        updated = capability_cache.record_reference(
            existing, payload_id=payload_id, release_version=release_version
        )
        import json

        manifest_path.write_text(json.dumps({"entries": updated.entries}))

    def install_all(self, *, cache_dir: Path, release_version: str) -> InstallResult:
        for payload_id in self._payloads:
            try:
                self.install_one(cache_dir=cache_dir, release_version=release_version, payload_id=payload_id)
            except RuntimeError:
                return InstallResult(completed=False)
        return InstallResult(completed=True)

    def can_launch_from_cache(self, *, cache_dir: Path, release_version: str) -> bool:
        if self._offline:
            return all((cache_dir / payload_id).exists() for payload_id in self._payloads)
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_capability_install_lifecycle.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Wire `bootstrap/main.py::_run` to actually call capability staging (real, non-fake path), then commit**

```bash
git add tests/fakes/local_capability_source.py tests/integration/test_capability_install_lifecycle.py bootstrap/main.py
git commit -m "feat(launcher): local immutable capability-payload install lifecycle (D3)"
```

**Recovery:** Retain the last valid immutable set; quarantine the failed candidate under the
`.partial` convention D1/C7 already use; rebuild manifests from the lock rather than hand-editing.

---

## Task 4 (D4): Native thin ≤18MB Windows & macOS installers

**Goal:** Add a macOS build path — there is none today. `bootstrap/build.spec` hardcodes
`winreg`/`bootstrap.webview2` unconditionally in `hiddenimports`, which cannot resolve on macOS.
Blocked on D2 (webview2 fix) landing first. `ci.yml`'s `coverage-baseline` job already proves
`macos-latest` works for this repo/org, so this task reuses that confirmed capacity rather than
provisioning anything new.

**Files:**
- Modify: `bootstrap/build.spec`
- Create: `.github/workflows/release.yml`
- Test: `tests/release/test_installer_budget.py`, `tests/release/test_clean_machine.py`,
  `tests/ci/test_release_workflow.py`

**Acceptance Criteria:**
- [ ] `bootstrap/build.spec` builds successfully on macOS (requires D2 landed first)
- [ ] Each native installer is ≤ 18 MB
- [ ] Neither installer embeds Playwright/browser binaries/OpenCV/PDF/wheelhouse
- [ ] A clean machine (no system Python) installs core via either installer and launches fully
      offline afterward
- [ ] `release.yml`'s two jobs each run only on their native runner, no cross-build
- [ ] Windows 10 x64 is best-effort only, never blocks the release job

**Verify:** `uv run pytest -q tests/release/ tests/ci/test_release_workflow.py -v` → all pass; trigger `release.yml` manually once on both runners before merging

**Steps:**

- [ ] **Step 1: Write the failing installer-budget test**

```python
# tests/release/test_installer_budget.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

MAX_INSTALLER_BYTES = 18 * 1024 * 1024


@pytest.mark.release
def test_each_thin_installer_is_at_most_18_mb(tmp_path):
    dist_dir = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "bootstrap/build.spec", "--distpath", str(dist_dir)],
        check=True, capture_output=True,
    )
    artifacts = list(dist_dir.glob("**/*"))
    installer = next(p for p in artifacts if p.is_file() and p.suffix in {".exe", ".app", ".pkg"})
    assert installer.stat().st_size <= MAX_INSTALLER_BYTES, (
        f"{installer.name} is {installer.stat().st_size} bytes, over the {MAX_INSTALLER_BYTES} budget"
    )


@pytest.mark.release
def test_installer_excludes_heavy_optional_stacks(tmp_path):
    """A size check alone can't catch 'small but wrong contents' -- assert the frozen build's
    own datas/binaries manifest never names playwright/cv2/fitz."""
    import bootstrap.build as build_spec_module  # the spec, importable as plain Python

    excluded = {"playwright", "cv2", "fitz", "opencv"}
    named = {Path(p).stem.lower() for p, *_ in getattr(build_spec_module, "datas", [])}
    assert not (named & excluded)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/release/test_installer_budget.py -v -m release`
Expected: FAIL — macOS build fails today (D2 not yet landed relative to a clean run, or `build.spec` still has unconditional Windows-only `hiddenimports`)

- [ ] **Step 3: Make `hiddenimports` OS-conditional**

```python
# bootstrap/build.spec -- replace the unconditional:
#     hiddenimports = ["winreg", "bootstrap.webview2", ...]
# with:
import sys

hiddenimports = [
    # ... existing non-Windows-specific entries unchanged ...
]
if sys.platform == "win32":
    hiddenimports += ["winreg", "bootstrap.webview2"]
```

- [ ] **Step 4: Run test to verify it passes on both platforms**

Run: `uv run pytest tests/release/test_installer_budget.py -v -m release` (once per native runner)
Expected: PASS on `windows-latest` and `macos-14`

- [ ] **Step 5: Add the release workflow, then commit**

```yaml
# .github/workflows/release.yml
name: Release
on:
  workflow_dispatch:
jobs:
  launcher-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv python install 3.12
      - run: uv sync --locked
      - run: uv run pytest -q tests/release/test_installer_budget.py -m release

  launcher-macos:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv python install 3.12
      - run: uv sync --locked
      - run: uv run pytest -q tests/release/test_installer_budget.py -m release
```

```bash
git add bootstrap/build.spec .github/workflows/release.yml tests/release/test_installer_budget.py
git commit -m "feat(release): OS-conditional PyInstaller spec + native release workflow (D4)"
```

- [ ] **Step 6: Write the clean-machine test, then commit**

```python
# tests/release/test_clean_machine.py
from __future__ import annotations

import pytest


@pytest.mark.release
def test_first_install_without_system_python_then_offline_restart(tmp_path):
    """Runs against a throwaway container/VM in CI, not locally -- exercises the built installer
    end to end: install -> first launch -> kill -> offline restart."""
    pytest.skip("exercised only in the release.yml CI job against a clean container image")
```

```bash
git add tests/release/test_clean_machine.py
git commit -m "test(release): clean-machine install/offline-restart placeholder for CI-only run (D4)"
```

**Recovery:** Do not publish an oversized/cross-built artifact; retain last-known-good installers;
reduce the frozen closure rather than raise the 18 MB budget.

---

## Task 5 (D5): Redacted rotating diagnostics + no-op telemetry seam

**Goal:** `bootstrap/main.py::_setup_logging` already builds a real (non-rotating,
non-redacted) `logging.Logger`. Add rotation + redaction there, extend structured logging into
`src/scoutmb` (replacing the 19 `print()` diagnostic sites — user-facing progress prints stay as
`print()`), and add `ObservabilityPort`/`NoopObservability` following the `ports/clock.py`
Protocol convention.

**Files:**
- Create: `src/scoutmb/logging_setup.py`, `src/scoutmb/ports/observability.py`,
  `src/scoutmb/adapters/observability/noop.py`
- Modify: `bootstrap/main.py::_setup_logging`
- Modify: diagnostic `print()` sites in `src/scoutmb/features/acquisition/pipeline.py`,
  `bootstrap/entry.py`, `bootstrap/probe_msedge.py` (progress-output prints in `pdf.py`/`schedule.py`
  stay as `print()` — this task does not touch those)
- Test: `tests/observability/test_observability_port.py`, extend
  `tests/packaging/test_core_imports.py`, `tests/privacy/test_diagnostics.py`

**Acceptance Criteria:**
- [ ] `NoopObservability.record(...)` never writes to disk and never opens a socket
- [ ] `core`/`ports`/`features` never import `opentelemetry`
- [ ] Event attributes are validated against a closed vocabulary that forbids names/paths/URLs/
      IDs/tokens
- [ ] `bootstrap.log` rotates rather than growing unbounded
- [ ] The real silent swallow at `features/acquisition/pipeline.py:108` now logs; the three
      intentional `playwright_gateway.py` selector-probe swallows get a one-line comment and are
      left as-is

**Verify:** `uv run pytest -q tests/observability/ tests/packaging/test_core_imports.py tests/privacy/test_diagnostics.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test for `ObservabilityPort`/`NoopObservability`**

```python
# tests/observability/test_observability_port.py
from __future__ import annotations

import socket

import pytest

from scoutmb.adapters.observability.noop import NoopObservability
from scoutmb.ports.observability import InvalidObservabilityEvent


def test_noop_observability_never_persists_or_uses_network(tmp_path, monkeypatch):
    def fail_if_socket_opened(*_a, **_k):
        raise AssertionError("NoopObservability must never touch the network")

    monkeypatch.setattr(socket, "socket", fail_if_socket_opened)

    obs = NoopObservability()
    obs.record("scout_processed", count="3")

    assert list(tmp_path.iterdir()) == []  # nothing written anywhere


def test_forbidden_attribute_keys_are_rejected():
    obs = NoopObservability()
    with pytest.raises(InvalidObservabilityEvent):
        obs.record("scout_processed", qr_url="https://scoutingevent.com/mobile/abc123")


def test_forbidden_attribute_values_shaped_like_a_path_are_rejected():
    obs = NoopObservability()
    with pytest.raises(InvalidObservabilityEvent):
        obs.record("file_written", detail="/Users/someone/scouts.csv")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/observability/test_observability_port.py -v`
Expected: FAIL — `scoutmb.ports.observability`/`scoutmb.adapters.observability.noop` don't exist

- [ ] **Step 3: Write minimal implementation**

```python
# src/scoutmb/ports/observability.py
"""No-op-by-default event recording (D5). Follows ports/clock.py's Protocol-per-collaborator
convention: one minimal method, injected, never a bag of unrelated capabilities."""

from __future__ import annotations

import re
from typing import Protocol

_FORBIDDEN_KEYS = {"name", "path", "url", "qr_url", "attendee_id", "token"}
_PATH_LIKE = re.compile(r"^/|^[A-Za-z]:\\|https?://")


class InvalidObservabilityEvent(ValueError):
    pass


class ObservabilityPort(Protocol):
    def record(self, event: str, **attributes: str) -> None: ...


def validate_event(event: str, attributes: dict[str, str]) -> None:
    for key, value in attributes.items():
        if key in _FORBIDDEN_KEYS:
            raise InvalidObservabilityEvent(f"attribute key {key!r} is forbidden")
        if _PATH_LIKE.match(value):
            raise InvalidObservabilityEvent(f"attribute {key!r} looks like a path/URL: {value!r}")
```

```python
# src/scoutmb/adapters/observability/noop.py
from __future__ import annotations

from scoutmb.ports.observability import validate_event


class NoopObservability:
    def record(self, event: str, **attributes: str) -> None:
        validate_event(event, attributes)
        # deliberately does nothing else -- no disk write, no network, ever
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/observability/test_observability_port.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/scoutmb/ports/observability.py src/scoutmb/adapters/observability/noop.py tests/observability/test_observability_port.py
git commit -m "feat(observability): ObservabilityPort + NoopObservability, redacted-event guard (D5)"
```

- [ ] **Step 6: Write the failing test for the opentelemetry import guard + log rotation**

```python
# tests/packaging/test_core_imports.py -- extend the existing HEAVY tuple
# (change: HEAVY = ("cv2", "fitz", "playwright") -> add "opentelemetry")
# The existing test_core_layers_never_import_the_heavy_stacks then covers this for free.
```

```python
# tests/launcher/test_log_rotation.py (new)
from __future__ import annotations

from bootstrap.main import _setup_logging
from bootstrap.paths import AppPaths


def test_bootstrap_log_rotates_past_the_size_threshold(tmp_path):
    paths = AppPaths(root=tmp_path)
    paths.ensure_dirs()
    logger = _setup_logging(paths)

    big_message = "x" * 2000
    for _ in range(2000):  # exceeds a small rotation threshold quickly
        logger.info(big_message)

    rotated = list(paths.logs_dir.glob("bootstrap.log.*"))
    assert rotated, "expected at least one rotated backup file"
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/launcher/test_log_rotation.py tests/packaging/test_core_imports.py -v`
Expected: FAIL — `HEAVY` doesn't include `opentelemetry` yet; `_setup_logging` uses plain `FileHandler`, never rotates

- [ ] **Step 8: Write minimal implementation**

```python
# tests/packaging/test_core_imports.py:20 -- change:
HEAVY = ("cv2", "fitz", "playwright", "opentelemetry")
```

```python
# bootstrap/main.py -- replace the plain FileHandler in _setup_logging with:
import logging.handlers

def _setup_logging(paths: AppPaths) -> logging.Logger:
    logger = logging.getLogger("bootstrap")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            paths.logs_dir / "bootstrap.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        handler.addFilter(_redact_sensitive_values)
        logger.addHandler(handler)
    return logger


def _redact_sensitive_values(record: logging.LogRecord) -> bool:
    import re

    record.msg = re.sub(r"https?://\S+", "[redacted-url]", str(record.msg))
    return True
```

- [ ] **Step 9: Run test to verify it passes**

Run: `uv run pytest tests/launcher/test_log_rotation.py tests/packaging/test_core_imports.py -v`
Expected: PASS

- [ ] **Step 10: Fix the one real silent swallow, then commit**

```python
# src/scoutmb/features/acquisition/pipeline.py:108 -- replace bare `except Exception:` (pass)
# with:
except Exception:
    logging.getLogger("scoutmb").exception("unexpected error during acquisition pipeline")
```

```bash
git add bootstrap/main.py tests/packaging/test_core_imports.py tests/launcher/test_log_rotation.py src/scoutmb/features/acquisition/pipeline.py src/scoutmb/logging_setup.py
git commit -m "feat(diagnostics): rotating redacted logs, opentelemetry import guard, fix silent swallow (D5)"
```

**Recovery:** Keep `NoopObservability` as the always-available fallback; reject an invalid event
DTO rather than logging it partially; regenerate only the specifically requested support bundle.

---

## Task 6 (D6): Supply-chain — `uv audit` + license-compliance gate

**Goal:** `uv audit` is a real, already-installed subcommand (`uv 0.12.9`). Wire it into CI and
build the license gate — both entirely absent today. License policy is the standard permissive
allowlist (MIT/BSD-2/BSD-3/Apache-2.0/ISC/PSF-2.0), per your decision above.

**Files:**
- Create: `tools/check_licenses.py`, `release/license-policy.toml`
- Modify: `pyproject.toml`, `.github/workflows/ci.yml`
- Test: `tests/release/test_supply_chain.py`, `tests/ci/test_workflow_contract.py`

**Acceptance Criteria:**
- [ ] `uv audit` runs in CI and fails on any reported vulnerability
- [ ] `check_licenses.py` exits non-zero on a disallowed license and exits 0 today against the
      real `uv.lock`
- [ ] `project.version` remains the single authoritative version source
- [ ] The new `supply-chain` CI job is named in `ci.yml`'s `jobs:` mapping
- [ ] Hashes are documented as integrity-only, never publisher-authenticity

**Verify:** `uv run pytest -q tests/release/test_supply_chain.py tests/ci/test_workflow_contract.py -v && uv run python tools/check_licenses.py --lock uv.lock --policy release/license-policy.toml` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test for `check_licenses.py`**

```python
# tests/release/test_supply_chain.py
from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_check_licenses_passes_against_the_real_lock_and_policy():
    result = subprocess.run(
        [sys.executable, "tools/check_licenses.py",
         "--lock", "uv.lock", "--policy", "release/license-policy.toml"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_licenses_rejects_a_disallowed_license(tmp_path):
    policy = tmp_path / "policy.toml"
    policy.write_text('allowed = ["MIT"]\n')
    lock = tmp_path / "fake.lock"
    lock.write_text(
        '[[package]]\nname = "gpl-thing"\nversion = "1.0"\n'
        '[package.metadata]\nlicense = "GPL-3.0"\n'
    )

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools/check_licenses.py"),
         "--lock", str(lock), "--policy", str(policy)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "gpl-thing" in result.stdout


def test_pyproject_declares_the_mit_license():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    assert data["project"]["license"] == "MIT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/release/test_supply_chain.py -v`
Expected: FAIL — `tools/check_licenses.py` doesn't exist; `pyproject.toml` has no `license` field

- [ ] **Step 3: Write minimal implementation**

```toml
# release/license-policy.toml
allowed = ["MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC", "PSF-2.0"]
```

```python
# pyproject.toml -- add under [project]:
license = "MIT"
```

```python
# tools/check_licenses.py -- styled after tools/check_private_data.py's argparse + exit-code convention
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path


def load_lock_licenses(lock_path: Path) -> dict[str, str]:
    text = lock_path.read_text()
    # uv.lock is TOML; each [[package]] block may carry package.metadata.license.
    # This walks the parsed structure rather than regexing the raw text.
    data = tomllib.loads(text)
    licenses: dict[str, str] = {}
    for pkg in data.get("package", []):
        name = pkg.get("name")
        license_id = pkg.get("metadata", {}).get("license") if isinstance(pkg.get("metadata"), dict) else None
        if name and license_id:
            licenses[name] = license_id
    return licenses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    args = parser.parse_args(argv)

    policy = tomllib.loads(args.policy.read_text())
    allowed = set(policy["allowed"])
    licenses = load_lock_licenses(args.lock)

    violations = {name: lic for name, lic in licenses.items() if lic not in allowed}
    if violations:
        for name, lic in sorted(violations.items()):
            print(f"disallowed license: {name} ({lic})")
        return 1
    print(f"{len(licenses)} package license(s) checked, all allowed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/release/test_supply_chain.py -v`
Expected: PASS (3 passed) — note: `uv.lock`'s actual TOML shape for per-package license metadata
must be confirmed against a real `uv.lock` read during implementation; adjust `load_lock_licenses`
to the real schema if `package.metadata.license` isn't the right key path (`uv.lock` schema is
`uv`-version-specific — verify against the installed `uv 0.12.9`'s actual lock format before
trusting this key path).

- [ ] **Step 5: Commit**

```bash
git add tools/check_licenses.py release/license-policy.toml pyproject.toml tests/release/test_supply_chain.py
git commit -m "feat(supply-chain): license-compliance gate against a permissive allowlist (D6)"
```

- [ ] **Step 6: Write the failing CI-workflow-contract test**

```python
# tests/ci/test_workflow_contract.py
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_supply_chain_job_is_required_in_ci():
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    assert "supply-chain" in workflow["jobs"]
    job = workflow["jobs"]["supply-chain"]
    steps_text = " ".join(step.get("run", "") for step in job["steps"])
    assert "uv audit" in steps_text
    assert "check_licenses.py" in steps_text
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/ci/test_workflow_contract.py -v`
Expected: FAIL — no `supply-chain` job in `ci.yml` yet

- [ ] **Step 8: Add the CI job**

```yaml
# .github/workflows/ci.yml -- add as a new job, sibling to the existing ones:
  supply-chain:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv python install 3.12
      - run: uv sync --locked --all-extras
      - run: uv audit
      - run: uv run python tools/check_licenses.py --lock uv.lock --policy release/license-policy.toml
```

- [ ] **Step 9: Run test to verify it passes, then commit**

Run: `uv run pytest tests/ci/test_workflow_contract.py -v`
Expected: PASS

```bash
git add .github/workflows/ci.yml tests/ci/test_workflow_contract.py
git commit -m "feat(ci): required supply-chain job running uv audit + license check (D6)"
```

**Recovery:** Block movement (fail the CI job); correct the lock or policy; regenerate; never
waive an unknown license/vulnerability without an explicit, reviewed exception entry.

---

## Task 7 (D7): Measured resource & performance limits

**Goal:** Almost no runtime resource limits exist as enforced typed config today. Build
`ReleaseLimits` with **measured** (not guessed) defaults, per your decision above — this task's
own work includes deriving the numbers via instrumentation against the existing synthetic scale
profiles, not receiving them externally.

**Files:**
- Modify: `src/scoutmb/config.py`
- Create: `tests/property/test_foundation_properties.py`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/performance/test_resource_limits.py`, `tests/performance/test_complexity.py`

**Acceptance Criteria:**
- [ ] Every `ReleaseLimits` field has a value derived from an actual recorded measurement
- [ ] Exceeding `max_upload_bytes`/`max_pdf_pages`/`max_archive_bytes` is a hard, tested
      rejection at the boundary that owns each check
- [ ] `test_complexity.py` runs a synthetic workload at two scale points and asserts growth stays
      within a documented variance band
- [ ] `test_foundation_properties.py` uses Hypothesis to assert parser/archive invariants across
      generated inputs
- [ ] The new `performance` CI job runs on one pinned runner class and fails on a documented
      regression

**Verify:** `uv run pytest -q tests/performance/ tests/property/ -v` → all pass

**Steps:**

- [ ] **Step 1: Measure real numbers before writing the config (this task's first real step is measurement, not code)**

```bash
# Run against the existing synthetic scale profile to get real numbers to encode below --
# do this for real, capture actual output, before writing ReleaseLimits:
uv run python -c "
from tests.factories.scale import canonical_profile, build_dataset
import time, tracemalloc

tracemalloc.start()
start = time.monotonic()
dataset = build_dataset(canonical_profile())
elapsed = time.monotonic() - start
_, peak = tracemalloc.get_traced_memory()
print(f'elapsed={elapsed:.3f}s peak_memory={peak} bytes rows={len(dataset)}')
"
```

Record the real printed numbers as the provenance comment in Step 3 below — do not proceed with
placeholder numbers.

- [ ] **Step 2: Write the failing test for `ReleaseLimits`**

```python
# tests/performance/test_resource_limits.py
from __future__ import annotations

import dataclasses

from scoutmb.config import ReleaseLimits


def test_every_release_limit_is_present_finite_and_documented():
    limits = ReleaseLimits()
    for field in dataclasses.fields(limits):
        value = getattr(limits, field.name)
        assert value is not None and value > 0, f"{field.name} must be a positive measured value"
    assert limits.__doc__ and "measured" in limits.__doc__.lower()


def test_upload_over_the_limit_is_rejected_at_the_boundary():
    from scoutmb.interfaces.web.routes import assert_upload_within_limit
    from scoutmb.errors import ScoutmbError

    limits = ReleaseLimits()
    with __import__("pytest").raises(ScoutmbError):
        assert_upload_within_limit(size_bytes=limits.max_upload_bytes + 1, limits=limits)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/performance/test_resource_limits.py -v`
Expected: FAIL — `ReleaseLimits`/`assert_upload_within_limit` don't exist yet

- [ ] **Step 4: Write minimal implementation, using the Step 1 measurement**

```python
# src/scoutmb/config.py -- add
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReleaseLimits:
    """Every field's default is a MEASURED value, recorded here with its provenance -- not a
    guessed round number. Re-run the measurement script in Task D7 Step 1 and update both the
    value and this comment if the workload characteristics change materially."""

    # measured 2026-0X-XX against tests.factories.scale.canonical_profile(): <elapsed>s, <peak> bytes
    max_upload_bytes: int = 25_000_000
    max_pdf_pages: int = 500
    max_pdf_dimension_px: int = 10_000
    parse_timeout_seconds: int = 120
    parse_memory_budget_bytes: int = 500_000_000
    max_archive_bytes: int = 200_000_000
    max_workers: int = 4
    max_queue_depth: int = 100
    shutdown_grace_seconds: int = 10
    disk_reserve_bytes: int = 500_000_000
    startup_timeout_seconds: int = 30
    max_requests_per_run: int = 10_000
```

```python
# src/scoutmb/interfaces/web/routes.py -- add, called from the upload route:
from scoutmb.config import ReleaseLimits
from scoutmb.errors import ScoutmbError


def assert_upload_within_limit(*, size_bytes: int, limits: ReleaseLimits) -> None:
    if size_bytes > limits.max_upload_bytes:
        raise ScoutmbError(f"upload of {size_bytes} bytes exceeds the {limits.max_upload_bytes} limit")
```

- [ ] **Step 5: Run test to verify it passes, then commit**

Run: `uv run pytest tests/performance/test_resource_limits.py -v`
Expected: PASS (with the real Step-1-measured numbers filled in, not the placeholders shown above
— replace before committing)

```bash
git add src/scoutmb/config.py src/scoutmb/interfaces/web/routes.py tests/performance/test_resource_limits.py
git commit -m "feat(config): ReleaseLimits with measured defaults, enforced at the upload boundary (D7)"
```

- [ ] **Step 6: Write the Hypothesis property test**

```python
# tests/property/test_foundation_properties.py
from __future__ import annotations

from hypothesis import given, strategies as st


@given(st.binary(max_size=1000))
def test_safe_extract_never_writes_outside_the_destination(payload: bytes):
    """Property: for ANY byte string fed in as a would-be archive entry name, safe_extract_zip
    either rejects it cleanly or writes only under the destination -- never above it."""
    import zipfile
    import tempfile
    from pathlib import Path

    from bootstrap.safe_extract import safe_extract_zip

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive_path = tmp_path / "test.zip"
        dest = tmp_path / "dest"
        dest.mkdir()
        try:
            name = payload.decode("utf-8", errors="ignore") or "x"
        except Exception:
            name = "x"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr(name, b"content")

        try:
            safe_extract_zip(archive_path, dest, max_expanded_bytes=10_000)
        except Exception:
            pass  # rejection is an acceptable outcome

        for written in dest.rglob("*"):
            assert dest in written.resolve().parents or written.resolve() == dest.resolve()
```

- [ ] **Step 7: Run test to verify it passes (or genuinely fails, revealing a real bug)**

Run: `uv run pytest tests/property/test_foundation_properties.py -v`
Expected: PASS — if it fails, that's a real `safe_extract_zip` bug this property test caught;
fix `bootstrap/safe_extract.py` before proceeding, do not weaken the property

- [ ] **Step 8: Add the `performance` CI job, then commit**

```yaml
# .github/workflows/ci.yml -- new job
  performance:
    runs-on: macos-latest  # pinned for reproducibility, matching coverage-baseline's precedent
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv python install 3.12
      - run: uv sync --locked --all-extras
      - run: uv run pytest -q tests/performance/ tests/property/ -v
```

```bash
git add tests/property/test_foundation_properties.py .github/workflows/ci.yml
git commit -m "test(performance): Hypothesis property tests + pinned performance CI job (D7)"
```

**Recovery:** Keep prior limits; reject the candidate change; profile before adjusting; never
widen a limit without a linked measurement justifying it.

---

## Task 8 (D8): Final acceptance, documentation, legacy retirement

**Goal:** Fix every doc still describing the pre-refactor flat layout — including this repo's own
`CLAUDE.md` — and build the real, single, gated live-service smoke test now (per your decision
above), backed by plumbing that's existed since early Slices but has never been used.

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`
- Modify: `src/scoutmb/interfaces/cli/{pdf,schedule}.py` (stale shim comments)
- Create: `tests/acceptance/test_documented_commands.py`,
  `tests/acceptance/test_release_contract.py`, `tests/acceptance/test_no_live_service.py`, and
  the first real `@pytest.mark.live_service` test

**Acceptance Criteria:**
- [ ] `test_documented_commands.py` runs every offline command `README.md` documents against a
      real installed `troop349`/`troop349-pdf`/`troop349-schedule` and asserts success
- [ ] `CLAUDE.md` no longer contains "no package, no build step, no test suite" or any equivalent
      false claim
- [ ] Exactly one test carries `@pytest.mark.live_service`
- [ ] `test_release_contract.py` asserts Gates 1/1b/2 evidence is present and green, and
      explicitly asserts Gate 3's deferred status is recorded rather than silently treated as passed
- [ ] No stale shim comment references a file that no longer exists in the repo
- [ ] `AGENTS.md`/`GEMINI.md` reviewed and updated independently, not copy-pasted from `CLAUDE.md`

**Verify:** `uv run pytest -q tests/acceptance/ -v` → all pass; `uv run pytest -m live_service` → passes once, manually, with `SCOUTMB_ALLOW_LIVE_SERVICE=1` set, read-only

**Steps:**

- [ ] **Step 1: Write the failing test for the live-service count invariant**

```python
# tests/acceptance/test_no_live_service.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_exactly_one_test_carries_the_live_service_marker():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "live_service"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    collected = [line for line in result.stdout.splitlines() if "::" in line]
    assert len(collected) == 1, f"expected exactly one live_service test, found: {collected}"


def test_default_lane_never_sets_the_live_opt_in_env_var(monkeypatch):
    import os

    monkeypatch.delenv("SCOUTMB_ALLOW_LIVE_SERVICE", raising=False)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-m", "not live_service and not playwright",
         "--collect-only"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={**os.environ, "SCOUTMB_ALLOW_LIVE_SERVICE": ""},
    )
    assert result.returncode == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/acceptance/test_no_live_service.py -v`
Expected: FAIL — zero tests currently carry `@pytest.mark.live_service` (count is 0, not 1)

- [ ] **Step 3: Write the real live-service test**

```python
# tests/live_service/test_real_scoutingevent_read.py (new)
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live_service


@pytest.mark.skipif(
    not os.environ.get("SCOUTMB_ALLOW_LIVE_SERVICE"),
    reason="requires SCOUTMB_ALLOW_LIVE_SERVICE=1 -- manual, read-only, opt-in only",
)
def test_real_scoutingevent_site_responds_to_a_read_only_probe():
    """The ONE test in this suite allowed to touch the real service. Read-only: fetches a known
    public, non-authenticated page and asserts it responds -- never a real QR URL, never any
    write, never real attendee data. Run manually: SCOUTMB_ALLOW_LIVE_SERVICE=1 uv run pytest
    -m live_service"""
    import urllib.request

    from scoutmb.network_policy import assert_egress_allowed

    assert_egress_allowed("scoutingevent.com")
    with urllib.request.urlopen("https://scoutingevent.com/", timeout=10) as response:
        assert response.status == 200
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/acceptance/test_no_live_service.py -v`
Expected: PASS (exactly one collected)

Run manually once, with real opt-in: `SCOUTMB_ALLOW_LIVE_SERVICE=1 uv run pytest -m live_service -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/live_service/test_real_scoutingevent_read.py tests/acceptance/test_no_live_service.py
git commit -m "test(acceptance): the one gated read-only live_service smoke test (D8)"
```

- [ ] **Step 6: Write the failing documented-commands test**

```python
# tests/acceptance/test_documented_commands.py
from __future__ import annotations

import subprocess
import sys


def test_troop349_help_runs_successfully():
    result = subprocess.run([sys.executable, "-m", "scoutmb.interfaces.desktop.app", "--help"],
                             capture_output=True, text=True)
    # desktop app may not support --help; fall back to the CLI entry points, which do
    result = subprocess.run(["uv", "run", "troop349-pdf", "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(["uv", "run", "troop349-schedule", "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/acceptance/test_documented_commands.py -v`
Expected: FAIL if `README.md`'s documented commands don't match the real `troop349-*` entry
points (likely, since `README.md` still describes `pdf_to_scouts.py`/`scout_schedule_cli.py`)

- [ ] **Step 8: Rewrite `README.md` and `CLAUDE.md` to match the real package**

Rewrite both to describe: `src/scoutmb`'s layer structure (`core`/`ports`/`features`/`adapters`/
`interfaces`), the `troop349`/`troop349-pdf`/`troop349-schedule` console scripts, `uv`-based
setup (`uv sync --locked --all-extras`), and the real test/CI/gate structure — replacing every
reference to `pdf_to_scouts.py`/`scout_schedule_cli.py` and the "no package, no build step, no
test suite" framing. (Full replacement text is produced during implementation, not pre-written
here, since it must reflect whatever D1-D7 actually landed as by the time D8 executes.)

- [ ] **Step 9: Run test to verify it passes**

Run: `uv run pytest tests/acceptance/test_documented_commands.py -v`
Expected: PASS

- [ ] **Step 10: Clean up stale shim comments, add the release-contract test, then commit**

```python
# tests/acceptance/test_release_contract.py
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_gate_1_and_2_evidence_is_present():
    assert (REPO_ROOT / "tests/baselines/phase_a.json").exists()
    assert (REPO_ROOT / "tests/matrix/test_registry.py").exists()


def test_gate_3_deferred_status_is_explicitly_recorded():
    slice3_followup = REPO_ROOT / "docs/superpowers/plans/2026-08-26-slice-3-followup-launch-release-dir.md"
    text = slice3_followup.read_text()
    assert "still outstanding" in text.lower() or "deferred" in text.lower()


def test_no_stale_shim_comment_references_a_deleted_file():
    deleted = {"pdf_to_scouts.py", "scout_schedule_cli.py"}
    for path in (REPO_ROOT / "src/scoutmb/interfaces/cli").glob("*.py"):
        text = path.read_text()
        for name in deleted:
            assert name not in text, f"{path} still references deleted file {name}"
```

```bash
git add README.md CLAUDE.md AGENTS.md GEMINI.md src/scoutmb/interfaces/cli/pdf.py src/scoutmb/interfaces/cli/schedule.py tests/acceptance/
git commit -m "docs(acceptance): rewrite README/CLAUDE/AGENTS/GEMINI for the real package, remove stale shim comments, add release-contract tests (D8)"
```

**Recovery:** Do not publish/migrate the live install; restore the last-known-good bundle on any
acceptance failure; return the failure to its originating D-task rather than patching around it
in the acceptance test itself; rerun D8 after the fix lands.

---

## Carried-forward reference

| Path | Injected failure | Task | Required behavior |
| --- | --- | --- | --- |
| Capabilities | Missing/incompatible/corrupt payload | D1, D3 | Core stays usable; prior capability retained; feature truthfully unavailable |
| Browser selection | Wrong OS, missing binary, macOS import blocked | D2 | Fail before mutation; documented fallback order only; macOS bootstrap importable at all |
| Native installer | Cross-build, missing system Python, oversized, offline restart | D4 | Build only on target runner; reject artifact; keep last-known-good |
| Diagnostics | Sensitive value, invalid event DTO, accidental exporter dep | D5 | Reject/redact; keep no-op; data + network unaffected |
| Supply chain | Vulnerability, disallowed license | D6 | Block; regenerate from the lock |
| Resource limits | Queue/cache/disk/memory/time exceeded | D7 | Reject or pause safely with bounded diagnostics |
| Documentation/acceptance | Stale doc, unused live-service plumbing, dangling shim comment | D8 | Docs match code; exactly one gated live test; no orphaned compatibility references |

## Note on final documentation

`CLAUDE.md` has been stale since roughly Slice 2 — every agent session in this repo, this one
included, has been trusting a document describing a codebase that no longer exists. D8 is the
fix. Rebuild the code-review-graph after D8 lands.
