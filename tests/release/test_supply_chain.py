from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.release  # makes a real network call to pypi.org, per-package -- not free/instant
def test_check_licenses_passes_against_the_real_lock_and_policy():
    result = subprocess.run(
        [
            sys.executable,
            "tools/check_licenses.py",
            "--lock",
            "uv.lock",
            "--policy",
            "release/license-policy.toml",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_licenses_rejects_a_disallowed_license(tmp_path, monkeypatch):
    import tools.check_licenses as check_licenses

    monkeypatch.setattr(check_licenses, "resolve_license", lambda name, version: "GPL-3.0")

    policy = tmp_path / "policy.toml"
    policy.write_text('allowed = ["MIT"]\n[overrides]\n')
    lock = tmp_path / "fake.lock"
    lock.write_text('[[package]]\nname = "gpl-thing"\nversion = "1.0"\n')

    result = check_licenses.main(["--lock", str(lock), "--policy", str(policy)])

    assert result != 0


def test_check_licenses_treats_unresolvable_license_as_a_failure_not_a_silent_pass(
    tmp_path, monkeypatch
):
    import tools.check_licenses as check_licenses

    monkeypatch.setattr(check_licenses, "resolve_license", lambda name, version: None)

    policy = tmp_path / "policy.toml"
    policy.write_text('allowed = ["MIT"]\n[overrides]\n')
    lock = tmp_path / "fake.lock"
    lock.write_text('[[package]]\nname = "mystery-thing"\nversion = "1.0"\n')

    result = check_licenses.main(["--lock", str(lock), "--policy", str(policy)])

    assert result != 0


def test_check_licenses_respects_a_hand_maintained_override(tmp_path, monkeypatch):
    import tools.check_licenses as check_licenses

    def fail_if_called(name, version):
        raise AssertionError("resolve_license should never run for an overridden package")

    monkeypatch.setattr(check_licenses, "resolve_license", fail_if_called)

    policy = tmp_path / "policy.toml"
    policy.write_text('allowed = ["MIT"]\n[overrides]\n"weird-thing" = "MIT"\n')
    lock = tmp_path / "fake.lock"
    lock.write_text('[[package]]\nname = "weird-thing"\nversion = "1.0"\n')

    result = check_licenses.main(["--lock", str(lock), "--policy", str(policy)])

    assert result == 0


def test_pyproject_declares_the_mit_license():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    assert data["project"]["license"] == "MIT"
