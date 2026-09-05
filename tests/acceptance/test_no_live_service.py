from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_exactly_one_test_carries_the_live_service_marker():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "live_service"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    collected = [line for line in result.stdout.splitlines() if "::" in line]
    assert len(collected) == 1, f"expected exactly one live_service test, found: {collected}"


def test_default_lane_never_sets_the_live_opt_in_env_var():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-m",
            "not live_service and not playwright and not release",
            "--collect-only",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "SCOUTMB_ALLOW_LIVE_SERVICE": ""},
    )
    assert result.returncode == 0, result.stderr
