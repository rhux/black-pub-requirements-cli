# PyInstaller spec for the self-bootstrapping installer.
# Build from the repo root with: pyinstaller --noconfirm bootstrap/build.spec
# Output: dist/ScoutingMeritBadgesSetup(.exe|.app) depending on the native runner.

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))


def app_src(*parts: str) -> str:
    return os.path.join(REPO_ROOT, *parts)


datas = [
    (app_src("requirements.txt"), "app_src"),
    (app_src("src", "scoutmb"), os.path.join("app_src", "scoutmb")),
    (app_src("bootstrap", "probe_msedge.py"), os.path.join("app_src", "_bootstrap_support")),
    (app_src("bootstrap", "probe_chrome_macos.py"), os.path.join("app_src", "_bootstrap_support")),
    (app_src("bootstrap", "probe_safari.py"), os.path.join("app_src", "_bootstrap_support")),
    (app_src("bootstrap", "probe_readiness.py"), os.path.join("app_src", "_bootstrap_support")),
]

hiddenimports = [
    "bootstrap.main",
    "bootstrap.ui",
    "bootstrap.config",
    "bootstrap.paths",
    "bootstrap.downloader",
    "bootstrap.python_env",
    "bootstrap.marker",
    "bootstrap.source_sync",
    "bootstrap.browser_setup",
    "bootstrap.webview2",  # importable on every platform since D2 (winreg import is deferred)
]
if sys.platform == "win32":
    # winreg is a real stdlib module only on Windows -- PyInstaller's Analysis would fail trying
    # to resolve it by this name on macOS/Linux if listed unconditionally.
    hiddenimports += ["winreg"]

a = Analysis(
    [app_src("bootstrap", "entry.py")],
    pathex=[REPO_ROOT],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ScoutingMeritBadgesSetup",
    console=False,
)
