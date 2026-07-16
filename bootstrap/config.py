"""Constants for the self-bootstrapping installer.

Bump PYTHON_VERSION when a newer 3.12.x embeddable build should be used —
this is independent of whatever Python built the bootstrapper exe itself.
"""

from __future__ import annotations

APP_NAME = "ScoutingMeritBadges"

PYTHON_VERSION = "3.12.8"
PYTHON_EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-amd64.zip"
)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

WEBVIEW2_BOOTSTRAPPER_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
WEBVIEW2_CLIENT_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

# Modules that must import cleanly in the app-local Python for the
# environment to be considered valid (see marker.py).
SMOKE_TEST_IMPORTS = [
    "fastapi",
    "playwright",
    "webview",
    "cv2",
    "fitz",
    "openpyxl",
    "uvicorn",
    "multipart",
]

MARKER_SCHEMA_VERSION = 1

LOCK_STALE_SECONDS = 30 * 60
