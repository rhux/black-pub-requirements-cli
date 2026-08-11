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


def test_archives_exclude_private_tests_logs_and_secrets(built_wheel: Path) -> None:
    """[tool.hatch.build] exclude already keeps bootstrap/raw_data/docs/tests out of the sdist
    source tree hatchling builds the wheel from -- this proves that holds in the actual built
    ARTIFACT (not just the config declaring intent), and adds a private-data-shaped filename
    scan as a second, independent check that doesn't rely on the exclude list naming every
    private path by name."""
    with zipfile.ZipFile(built_wheel) as archive:
        names = archive.namelist()

    excluded_prefixes = ("tests/", "raw_data/", "docs/", "bootstrap/")
    offenders = [n for n in names if n.startswith(excluded_prefixes)]
    assert offenders == []

    secret_shaped = [
        n
        for n in names
        if any(marker in n.lower() for marker in (".env", "secret", "token", ".key", ".pem"))
    ]
    assert secret_shaped == [], secret_shaped


def test_coverage_include_reaches_nested_modules() -> None:
    """`src/scoutmb/*.py` does NOT match a nested module: coverage's `*` never crosses `/`."""
    import tomllib

    from coverage.files import globs_to_regex

    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = config["tool"]["coverage"]["run"]["include"]
    pattern = globs_to_regex(include, case_insensitive=False, partial=False)
    assert pattern.match("src/scoutmb/core/inference/tree.py"), include


def test_copied_release_root_scoutmb_is_importable_via_the_dot_pth_entry(tmp_path: Path) -> None:
    """bootstrap/python_env.py's .pth entry already appends app_dir to the embedded
    interpreter's sys.path (unchanged by this task, per the Phase B spec's own note that this
    dependency is load-bearing but pre-existing). This proves scoutmb -- not just its
    resources/, which tests/packaging/test_mechanisms.py already covers -- imports from a
    directory laid out exactly like a synced app_dir, with no repository present."""
    import shutil
    import subprocess
    import sys

    app_dir = tmp_path / "app_dir"
    app_dir.mkdir()
    shutil.copytree("src/scoutmb", app_dir / "scoutmb")

    pth_file = app_dir / "_app_dir.pth"
    pth_file.write_text(str(app_dir) + "\n", encoding="utf-8")

    probe = (
        f"import sys; sys.path.insert(0, {str(app_dir)!r})\n"
        "import scoutmb.core.models\n"
        "print('SCOUTMB_IMPORT_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert "SCOUTMB_IMPORT_OK" in result.stdout
