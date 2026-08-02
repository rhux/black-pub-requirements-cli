from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(*args: str, seed: str | None = None) -> subprocess.CompletedProcess[str]:
    env = None
    if seed is not None:
        import os

        env = {**os.environ, "PYTHONHASHSEED": seed}
    return subprocess.run(
        [sys.executable, "tools/check_case_digest.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_preserve_case_expectations_are_unchanged() -> None:
    result = _run()
    assert result.returncode == 0, result.stdout


def test_digest_is_stable_across_hash_seeds() -> None:
    """The guard against the repr() trap: differing PYTHONHASHSEED must not change the digest.

    Without canonical serialization this fails intermittently in CI and looks like real
    oracle drift, which is the worst possible failure mode for this particular gate.
    """
    first = _run("--print", seed="0")
    second = _run("--print", seed="12345")
    assert first.stdout == second.stdout != ""
