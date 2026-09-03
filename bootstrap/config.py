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
# python.org release artifacts are immutable per version -- captured 2026-09-03 via a direct
# HTTPS fetch of PYTHON_EMBED_URL and a local sha256sum. Re-derive both whenever PYTHON_VERSION
# changes; never guess or carry forward the old value.
PYTHON_EMBED_SHA256 = "8d3f33be9eb810f23c102f08475af2854e50484b8e4e06275e937be61ce3d2fb"
PYTHON_EMBED_SIZE_BYTES = 11_094_114
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

WEBVIEW2_BOOTSTRAPPER_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
WEBVIEW2_CLIENT_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

# Modules that must import cleanly in the app-local Python for the
# environment to be considered valid (see marker.py).
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

MARKER_SCHEMA_VERSION = 1

LOCK_STALE_SECONDS = 30 * 60

# Bumped whenever scoutmb.core.run_state.RUN_STATE_VERSION,
# scoutmb.ports.checkpoint_store.CHECKPOINT_VERSION, or bootstrap.marker.MARKER_SCHEMA_VERSION
# changes -- the single aggregate durable-state generation a release manifest declares support
# for (see bootstrap/release_manifest.py, bootstrap/activation.py).
DURABLE_STATE_SCHEMA_VERSION = 1
