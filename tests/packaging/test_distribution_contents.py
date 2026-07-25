"""The wheel must carry py.typed and package data; coverage must reach nested modules.

These are packaging facts that are invisible until something installs the wheel somewhere
else, which is exactly when they are expensive to discover.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        [sys.executable, "-m", "uv", "build", "--wheel", "--out-dir", str(out)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    wheels = list(out.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"
    return wheels[0]


def test_wheel_contains_py_typed(built_wheel: Path) -> None:
    with zipfile.ZipFile(built_wheel) as archive:
        names = set(archive.namelist())
    assert "scoutmb/py.typed" in names, sorted(n for n in names if n.startswith("scoutmb/"))


def test_coverage_include_reaches_nested_modules() -> None:
    """`src/scoutmb/*.py` does NOT match a nested module: coverage's `*` never crosses `/`."""
    import tomllib

    from coverage.files import globs_to_regex

    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = config["tool"]["coverage"]["run"]["include"]
    pattern = globs_to_regex(include, case_insensitive=False, partial=False)
    assert pattern.match("src/scoutmb/core/inference/tree.py"), include
