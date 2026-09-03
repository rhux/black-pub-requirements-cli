"""Choose and provision a browser for Playwright: prefer the system's
Microsoft Edge (near-zero extra download), fall back to Playwright's own
bundled Chromium only if that doesn't work.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Callable

from bootstrap import capability_cache
from bootstrap.paths import AppPaths
from bootstrap.python_env import python_exe

ProgressFn = Callable[[str], None]

PROBE_TIMEOUT_SECONDS = 20
CHROMIUM_INSTALL_TIMEOUT_SECONDS = 20 * 60

# Chromium is acquired via `playwright install chromium` (install_chromium_fallback), which
# manages its own download internally -- we don't control a URL or hash to pin against, so this
# is a supported-platform-set check, not a hash-pinned-payload check like python_env.py's.
SUPPORTED_CHROMIUM_PLATFORMS = frozenset({"Windows", "Darwin", "Linux"})


def _log(log: ProgressFn | None, message: str) -> None:
    if log is not None:
        log(message)


def probe_msedge_channel(paths: AppPaths) -> bool:
    if os.environ.get("SCOUTMB_FORCE_CHROMIUM_FALLBACK"):
        return False  # test-only escape hatch, inert unless explicitly set

    probe_path = paths.app_dir / "_bootstrap_support" / "probe_msedge.py"
    try:
        result = subprocess.run(
            [str(python_exe(paths)), str(probe_path)],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def probe_chrome_macos(paths: AppPaths) -> bool:
    if os.environ.get("SCOUTMB_FORCE_CHROMIUM_FALLBACK"):
        return False  # test-only escape hatch, inert unless explicitly set

    probe_path = paths.app_dir / "_bootstrap_support" / "probe_chrome_macos.py"
    try:
        result = subprocess.run(
            [str(python_exe(paths)), str(probe_path)],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def install_chromium_fallback(paths: AppPaths, log: ProgressFn | None = None) -> None:
    _log(log, "Downloading browser (this can take a few minutes)...")
    result = subprocess.run(
        [str(python_exe(paths)), "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=CHROMIUM_INSTALL_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Chromium install failed:\n{result.stdout}\n{result.stderr}")


def resolve_browser_channel(paths: AppPaths, release_version: str, log: ProgressFn | None = None) -> str | None:
    """Returns the Playwright channel to use, or None to use bundled Chromium. Safari is never
    returned here -- it is reachable only through the separate, explicit
    resolve_experimental_safari() opt-in."""
    _log(log, "Checking browser...")
    if platform.system() == "Darwin":
        if probe_chrome_macos(paths):
            return "chrome"
        install_chromium_capability(paths, release_version=release_version, log=log)
        return None
    if probe_msedge_channel(paths):
        return "msedge"
    install_chromium_capability(paths, release_version=release_version, log=log)
    return None


async def verify_readiness(channel: str | None, url: str) -> bool:
    """Launches the selected engine and completes one real navigation against a loopback URL
    before the caller may consider it ready. Never falls back / switches engines on failure --
    that decision belongs to whatever called resolve_browser_channel, not to this check."""
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as playwright:
            launch_kwargs: dict[str, object] = {"headless": True}
            if channel is not None:
                launch_kwargs["channel"] = channel
            browser = await playwright.chromium.launch(**launch_kwargs)
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=5_000)
            finally:
                await browser.close()
        return True
    except Exception:
        return False


def resolve_experimental_safari() -> tuple[str, str]:
    """Never called from resolve_browser_channel -- only reachable via an explicit opt-in the
    caller must invoke deliberately (e.g. a --experimental-safari CLI flag)."""
    return "safari", (
        "Safari support is experimental and may not correctly render the ScoutingEvent "
        "mobile UI. Use at your own risk."
    )


def _ms_playwright_cache_dir() -> Path:
    """Mirrors Playwright's own default browsers-path resolution (PLAYWRIGHT_BROWSERS_PATH
    override, else the OS-conventional user cache dir) -- used only to discover which Chromium
    revision `playwright install` actually left behind, never to control where it installs."""
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override:
        return Path(override)
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", str(home))) / "ms-playwright"
    if system == "Darwin":
        return home / "Library" / "Caches" / "ms-playwright"
    return home / ".cache" / "ms-playwright"


def _discover_chromium_revision() -> str:
    cache_root = _ms_playwright_cache_dir()
    candidates = (
        sorted(p.name for p in cache_root.iterdir() if p.is_dir() and p.name.startswith("chromium-"))
        if cache_root.is_dir()
        else []
    )
    if not candidates:
        raise RuntimeError(
            f"chromium install reported success but no chromium-* directory was found "
            f"under {cache_root}"
        )
    return candidates[-1].removeprefix("chromium-")


def install_chromium_capability(
    paths: AppPaths, *, release_version: str, log: ProgressFn | None = None
) -> None:
    current_platform = platform.system()
    if current_platform not in SUPPORTED_CHROMIUM_PLATFORMS:
        raise RuntimeError(
            f"platform mismatch: chromium install is not supported on {current_platform!r} "
            f"(supported: {sorted(SUPPORTED_CHROMIUM_PLATFORMS)})"
        )
    install_chromium_fallback(paths, log)
    revision = _discover_chromium_revision()
    capability_cache.record_and_persist(
        paths.capability_cache_dir, payload_id="chromium", release_version=release_version
    )
    _log(log, f"Chromium revision {revision} ready.")


def write_browser_channel_marker(paths: AppPaths, channel: str | None) -> None:
    paths.browser_channel_path.write_text(json.dumps({"channel": channel}), encoding="utf-8")


def read_browser_channel_marker(paths: AppPaths) -> str | None:
    try:
        data = json.loads(paths.browser_channel_path.read_text(encoding="utf-8"))
        return data.get("channel")
    except (OSError, json.JSONDecodeError):
        return None
