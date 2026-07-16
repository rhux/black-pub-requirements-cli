"""Detect and, if missing, silently install Microsoft's WebView2 Runtime.

pywebview's native window cannot appear without it. This is the one
legitimate exception to "nothing global" — it's a small, Microsoft-signed
system component, not something specific to this app.
"""

from __future__ import annotations

import subprocess
import tempfile
import winreg
from pathlib import Path
from typing import Callable

from bootstrap.config import WEBVIEW2_BOOTSTRAPPER_URL, WEBVIEW2_CLIENT_GUID
from bootstrap.downloader import download

ProgressFn = Callable[[str], None]

_CANDIDATES = [
    (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
    (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
    (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
]


def is_webview2_installed() -> bool:
    for hive, subkey in _CANDIDATES:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0":
                    return True
        except FileNotFoundError:
            continue
        except OSError:
            continue
    return False


def install_webview2(log: ProgressFn | None = None) -> None:
    if log is not None:
        log("Installing a required Microsoft component (WebView2)...")
    with tempfile.TemporaryDirectory(prefix="scoutmb-webview2-") as tmp_dir:
        installer_path = Path(tmp_dir) / "MicrosoftEdgeWebview2Setup.exe"
        download(WEBVIEW2_BOOTSTRAPPER_URL, installer_path)
        subprocess.run([str(installer_path), "/silent", "/install"], check=True)


def ensure_webview2(log: ProgressFn | None = None) -> None:
    if not is_webview2_installed():
        install_webview2(log)
