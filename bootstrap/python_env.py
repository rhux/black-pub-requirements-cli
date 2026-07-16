"""Provision an isolated, embeddable Python 3.12 environment.

Never touches any existing/global Python installation, PATH, or registry —
everything lives under paths.python_dir.
"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path
from typing import Callable

from bootstrap.config import GET_PIP_URL, PYTHON_EMBED_URL, PYTHON_VERSION
from bootstrap.downloader import download
from bootstrap.paths import AppPaths

PTH_FILENAME = "python" + "".join(PYTHON_VERSION.split(".")[:2]) + "._pth"

ProgressFn = Callable[[str], None]


def _log(log: ProgressFn | None, message: str) -> None:
    if log is not None:
        log(message)


def python_exe(paths: AppPaths) -> Path:
    return paths.python_dir / "python.exe"


def pythonw_exe(paths: AppPaths) -> Path:
    return paths.python_dir / "pythonw.exe"


def _download_and_extract_python(paths: AppPaths, log: ProgressFn | None) -> None:
    _log(log, "Downloading Python runtime...")
    zip_path = paths.state_dir / "python-embed.zip"
    download(PYTHON_EMBED_URL, zip_path)

    _log(log, "Extracting Python runtime...")
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(paths.python_dir)
    zip_path.unlink(missing_ok=True)


def _patch_pth_file(paths: AppPaths, log: ProgressFn | None) -> None:
    _log(log, "Configuring Python runtime...")
    pth_path = paths.python_dir / PTH_FILENAME
    if not pth_path.exists():
        raise RuntimeError(f"Expected {PTH_FILENAME} not found in extracted Python runtime")

    text = pth_path.read_text(encoding="utf-8")
    text = text.replace("#import site", "import site")
    if "Lib\\site-packages" not in text and "Lib/site-packages" not in text:
        if not text.endswith("\n"):
            text += "\n"
        text += "Lib\\site-packages\n"
    # The embeddable distribution's isolated path mode does NOT auto-add the
    # launched script's own directory to sys.path (unlike a normal Python
    # install), so run_app.py's `from ui import server` would otherwise fail.
    app_dir_str = str(paths.app_dir)
    if app_dir_str not in text:
        if not text.endswith("\n"):
            text += "\n"
        text += app_dir_str + "\n"
    pth_path.write_text(text, encoding="utf-8")

    (paths.python_dir / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)


def _bootstrap_pip(paths: AppPaths, log: ProgressFn | None) -> None:
    _log(log, "Installing pip...")
    get_pip_path = paths.state_dir / "get-pip.py"
    download(GET_PIP_URL, get_pip_path)

    result = subprocess.run(
        [
            str(python_exe(paths)),
            str(get_pip_path),
            "--no-warn-script-location",
            "setuptools",
            "wheel",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pip bootstrap failed:\n{result.stdout}\n{result.stderr}")

    check = subprocess.run(
        [str(python_exe(paths)), "-m", "pip", "--version"],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        raise RuntimeError(f"pip self-check failed:\n{check.stdout}\n{check.stderr}")


def _install_requirements(paths: AppPaths, requirements_path: Path, log: ProgressFn | None) -> None:
    _log(log, "Installing dependencies (this can take a few minutes)...")
    result = subprocess.run(
        [
            str(python_exe(paths)),
            "-m",
            "pip",
            "install",
            "--no-warn-script-location",
            "-r",
            str(requirements_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Dependency install failed:\n{result.stdout}\n{result.stderr}")


def provision_python(paths: AppPaths, requirements_path: Path, log: ProgressFn | None = None) -> None:
    """Full provisioning sequence: download, extract, enable pip, install deps."""
    _download_and_extract_python(paths, log)
    _patch_pth_file(paths, log)
    _bootstrap_pip(paths, log)
    _install_requirements(paths, requirements_path, log)


def smoke_test(paths: AppPaths, imports: list[str]) -> bool:
    exe = python_exe(paths)
    if not exe.exists():
        return False
    code = "import " + ", ".join(imports)
    result = subprocess.run([str(exe), "-c", code], capture_output=True, text=True)
    return result.returncode == 0
