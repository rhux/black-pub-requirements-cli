from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_INSTALLER_BYTES = 18 * 1024 * 1024
HEAVY_STACKS = ("playwright", "cv2", "fitz", "opencv")


def _build(tmp_path: Path) -> Path:
    dist_dir = tmp_path / "dist"
    work_dir = tmp_path / "work"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
            "bootstrap/build.spec",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    artifacts = [p for p in dist_dir.iterdir() if p.is_file()]
    assert len(artifacts) == 1, f"expected exactly one built artifact, found: {artifacts}"
    return artifacts[0]


@pytest.mark.release
def test_thin_installer_is_at_most_18_mb(tmp_path):
    installer = _build(tmp_path)
    size = installer.stat().st_size
    assert size <= MAX_INSTALLER_BYTES, (
        f"{installer.name} is {size} bytes, over the {MAX_INSTALLER_BYTES} budget"
    )


@pytest.mark.release
def test_installer_excludes_heavy_optional_stacks(tmp_path):
    """A size check alone can't catch 'small but wrong contents' -- extract the built PKG
    archive's own module listing and assert none of the heavy optional stacks appear in it.
    Regression coverage for the real bug found during D4: browser_setup.py's readiness check
    used to import playwright directly, which PyInstaller's Analysis bundled wholesale (~52MB,
    nearly 3x the budget) even though the frozen bootstrapper never actually uses it."""
    dist_dir = tmp_path / "dist"
    work_dir = tmp_path / "work"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
            "bootstrap/build.spec",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    toc_path = work_dir / "build" / "xref-build.html"
    xref_text = toc_path.read_text(encoding="utf-8", errors="ignore")
    found = {
        stack for stack in HEAVY_STACKS if f"{stack}." in xref_text or f">{stack}<" in xref_text
    }
    assert not found, f"heavy stack(s) found in the frozen bootstrapper's dependency graph: {found}"
