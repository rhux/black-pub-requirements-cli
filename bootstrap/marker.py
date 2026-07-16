"""Skip-if-already-bootstrapped detection.

The marker is written only as the last step of a fully successful bootstrap,
so "missing marker" and "invalid marker" are the only failure states that
matter — a crash mid-install can never produce one.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from bootstrap.config import MARKER_SCHEMA_VERSION, PYTHON_VERSION, SMOKE_TEST_IMPORTS
from bootstrap.paths import AppPaths
from bootstrap.python_env import smoke_test


def compute_requirements_hash(requirements_path: Path) -> str:
    return hashlib.sha256(requirements_path.read_bytes()).hexdigest()


def read_marker(paths: AppPaths) -> dict[str, Any] | None:
    try:
        return json.loads(paths.marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_marker(paths: AppPaths, *, requirements_hash: str, browser_channel: str | None) -> None:
    payload = {
        "schema_version": MARKER_SCHEMA_VERSION,
        "python_version": PYTHON_VERSION,
        "requirements_hash": requirements_hash,
        "browser_channel": browser_channel,
        "completed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    tmp_path = paths.marker_path.with_suffix(paths.marker_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp_path, paths.marker_path)


def is_environment_valid(paths: AppPaths, requirements_path: Path) -> bool:
    marker = read_marker(paths)
    if marker is None:
        return False
    if marker.get("schema_version") != MARKER_SCHEMA_VERSION:
        return False
    if marker.get("python_version") != PYTHON_VERSION:
        return False
    if marker.get("requirements_hash") != compute_requirements_hash(requirements_path):
        return False
    return smoke_test(paths, SMOKE_TEST_IMPORTS)
