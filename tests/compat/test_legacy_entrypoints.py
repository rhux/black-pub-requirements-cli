"""The console script must work from an installed wheel with no repository present.

Executed as SUBPROCESSES: calling main() in-process skips the generated wrapper, the
sys.argv[0] the parser sees, and the exit-code path -- most of what could actually differ.

Slice 2b B10.4: retired pdf_to_scouts.py, so this file's original "argv-identical to the flat
script it replaces" comparison (test_pdf_console_script_usage_matches_flat_script) no longer has
anything to compare against -- deleted, not migrated. The package-only tests below (proving the
installed console script genuinely works, and that the package never imports the flat module)
are unaffected and stay.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real venv with the wheel installed. Returns the scripts directory."""
    root = tmp_path_factory.mktemp("install")
    dist = root / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    wheel = next(dist.glob("*.whl"))
    venv = root / "venv"
    subprocess.run(["uv", "venv", str(venv)], check=True, capture_output=True)
    python = venv / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), f"{wheel}[pdf]"],
        check=True,
        capture_output=True,
    )
    return python.parent


def test_pdf_console_script_runs_with_no_repository_present(
    installed: Path, tmp_path: Path
) -> None:
    """cwd is outside the repo and the wheel is the only source of scoutmb."""
    result = subprocess.run(
        [
            str(installed / "troop349-pdf"),
            str(tmp_path / "absent.pdf"),
            "--output",
            str(tmp_path / "out.csv"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert "No PDF files matched the supplied inputs." in result.stderr
    assert result.returncode != 0


def test_package_never_imports_the_flat_pdf_module() -> None:
    offenders = subprocess.run(
        ["rg", "-n", r"\bimport pdf_to_scouts\b|\bfrom pdf_to_scouts\b", "src/scoutmb"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert offenders.stdout == "", offenders.stdout
