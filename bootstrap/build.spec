# PyInstaller spec for the self-bootstrapping installer.
# Build from the repo root with: pyinstaller --noconfirm bootstrap/build.spec
# Output: dist/ScoutingMeritBadgesSetup.exe

import os

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))


def app_src(*parts: str) -> str:
    return os.path.join(REPO_ROOT, *parts)


datas = [
    (app_src("run_app.py"), "app_src"),
    (app_src("pdf_to_scouts.py"), "app_src"),
    (app_src("scout_schedule_cli.py"), "app_src"),
    (app_src("requirements.txt"), "app_src"),
    (app_src("ui", "__init__.py"), os.path.join("app_src", "ui")),
    (app_src("ui", "server.py"), os.path.join("app_src", "ui")),
    (app_src("ui", "static"), os.path.join("app_src", "ui", "static")),
    (app_src("bootstrap", "probe_msedge.py"), os.path.join("app_src", "_bootstrap_support")),
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
    "bootstrap.webview2",
    "winreg",
]

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
