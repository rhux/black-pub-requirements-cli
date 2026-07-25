"""Mechanism probes. The Phase B spec marks these plan-verified: they are claims about how
Python and this build behave, and earlier spec drafts got two of them wrong.

If one fails, amend the named spec section -- do not work around it in a later task.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE = "probe-token-do-not-remove"
READ_PROBE = (
    "from importlib.resources import files;"
    "print(files('scoutmb.resources').joinpath('templates/_probe.txt').read_text().strip())"
)


def test_asdict_preserves_tuple_type() -> None:
    """Spec: 'Frozen records and collection types'. asdict reconstructs via type(obj)(...),
    so a tuple stays a tuple; normalization to list is the serializer's job."""

    @dataclasses.dataclass(frozen=True, slots=True)
    class Record:
        items: tuple[int, ...]

    value = dataclasses.asdict(Record((1, 2)))
    assert isinstance(value["items"], tuple), (
        "asdict changed behavior; amend 'Frozen records and collection types'"
    )


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out)],
        cwd=REPO_ROOT, check=True, capture_output=True,
    )
    return next(out.glob("*.whl"))


def test_resources_readable_from_installed_wheel(wheel: Path, tmp_path: Path) -> None:
    """A REAL venv: the parent's editable install must not be able to satisfy this."""
    venv = tmp_path / "venv"
    subprocess.run(["uv", "venv", str(venv)], check=True, capture_output=True)
    python = venv / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        check=True, capture_output=True,
    )
    result = subprocess.run(
        [str(python), "-c", READ_PROBE],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    assert result.stdout.strip() == PROBE


def test_resources_readable_from_copied_release_root(tmp_path: Path) -> None:
    """The release root is a COPIED DIRECTORY, not an installed distribution.

    sys.path is set INSIDE the executed code: `python -I` implies -E and would discard a
    PYTHONPATH we set in the environment, silently falling back to the repo's editable
    install and passing for the wrong reason.

    `-I` alone is not enough here: it disables the *user* site-packages directory and
    PYTHONPATH, but ``sys.executable`` in this test run is the repo's own dev venv
    interpreter, which has `scoutmb` editable-installed in *its own* (non-user)
    site-packages -- a directory `-I` does not strip. `-S` (skip all site
    initialization) closes that gap; verified empirically against
    ``test_copied_root_probe_cannot_be_satisfied_by_the_repo_install`` below, which fails
    without `-S` (returncode 0 with an empty app dir) and passes with it.
    """
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    shutil.copytree(REPO_ROOT / "src" / "scoutmb", app_dir / "scoutmb")

    code = f"import sys; sys.path.insert(0, {str(app_dir)!r});" + READ_PROBE
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    assert result.stdout.strip() == PROBE, (
        "importlib.resources cannot read templates from a copied directory root; "
        "amend 'No __file__ in the package' before Task 21"
    )


def test_copied_root_probe_cannot_be_satisfied_by_the_repo_install(tmp_path: Path) -> None:
    """Guard the guard: if the probe passes with an EMPTY app dir, it is reading the parent's
    editable scoutmb and proves nothing.

    Requires the same `-I -S` combination as the test above -- `-I` alone leaves the dev
    venv's own site-packages (where `scoutmb` is editable-installed) on sys.path, so an
    empty app dir would still resolve `scoutmb` there and this guard would never trip.
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    code = f"import sys; sys.path.insert(0, {str(empty)!r});" + READ_PROBE
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode != 0, "the copied-root probe is not isolated"
