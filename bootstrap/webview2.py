"""Detect and, if missing, silently install Microsoft's WebView2 Runtime.

pywebview's native window cannot appear without it. This is the one
legitimate exception to "nothing global" — it's a small, Microsoft-signed
system component, not something specific to this app.

Windows-only: WebView2 doesn't exist on macOS/Linux (pywebview uses WKWebView/
GTK-WebKit there instead), so `winreg` is imported lazily inside the functions
that need it -- keeping this module importable on every platform, which
bootstrap.main (imported unconditionally by every entry point) requires.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from bootstrap.config import WEBVIEW2_BOOTSTRAPPER_URL, WEBVIEW2_CLIENT_GUID

ProgressFn = Callable[[str], None]

_CANDIDATE_KEYS = [
    ("HKEY_LOCAL_MACHINE", rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
    ("HKEY_LOCAL_MACHINE", rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
    ("HKEY_CURRENT_USER", rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
]


def is_webview2_installed() -> bool:
    import winreg  # deferred: this module must stay importable on non-Windows platforms

    for hive_name, subkey in _CANDIDATE_KEYS:
        hive = getattr(winreg, hive_name)
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
    from bootstrap.downloader import download

    if log is not None:
        log("Installing a required Microsoft component (WebView2)...")
    with tempfile.TemporaryDirectory(prefix="scoutmb-webview2-") as tmp_dir:
        installer_path = Path(tmp_dir) / "MicrosoftEdgeWebview2Setup.exe"
        download(WEBVIEW2_BOOTSTRAPPER_URL, installer_path)
        subprocess.run([str(installer_path), "/silent", "/install"], check=True)


def ensure_webview2(log: ProgressFn | None = None) -> None:
    if not is_webview2_installed():
        install_webview2(log)
