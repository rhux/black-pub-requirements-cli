"""Lane-accounting self-tests (REG-LANE-001..005) driven through pytester temp suites.

Each temp suite loads the real matrix_gate plugin and declares required execution keys via
the ``matrix_required_keys`` ini list, then proves the gate's exit code and its stable summary
line for the empty / deselected / skipped / duplicated / missing tripwires and a passing case.

Every nested pytest invocation runs in a REAL SUBPROCESS (``runpytest_subprocess``, never the
in-process ``runpytest``): the matrix_gate plugin module keeps its lane-accounting state in a
module-level global (``_CURRENT``), and an in-process nested run shares that same module
instance with the outer session -- its own ``pytest_collection_modifyitems``/
``pytest_sessionfinish`` calls would silently clobber the OUTER session's real
``--matrix-lane`` accounting (this is exactly how a real CI ``--matrix-lane default`` run could
have gone silently unenforced merely by having this file collected in the same session).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

_CONFTEST = 'pytest_plugins = ["tests.plugins.matrix_gate"]\n'

_MARK = 'import pytest\n@pytest.mark.matrix_case(case_id="CASE-001", context_id="legacy", lane="default")\n'

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _subprocess_can_import_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    # The nested subprocess's cwd is pytester's own tmp dir, not the repo root, so it needs
    # PYTHONPATH set explicitly to import "tests.plugins.matrix_gate" from its own conftest.
    existing = os.environ.get("PYTHONPATH", "")
    joined = str(_REPO_ROOT) if not existing else f"{_REPO_ROOT}{os.pathsep}{existing}"
    monkeypatch.setenv("PYTHONPATH", joined)


def _ini(required: str) -> str:
    return f"[pytest]\nmatrix_required_keys =\n    {required}\nasyncio_mode = auto\n"


def _make(pytester: pytest.Pytester, *, ini_required: str, test_body: str) -> None:
    pytester.makeconftest(_CONFTEST)
    pytester.makeini(_ini(ini_required))
    pytester.makepyfile(test_body)


# --- passing case -----------------------------------------------------------------------
def test_passing_case_accounts_and_exits_zero(pytester: pytest.Pytester) -> None:
    _make(
        pytester,
        ini_required="CASE-001::legacy::default",
        test_body=_MARK + "def test_case():\n    assert True\n",
    )
    result = pytester.runpytest_subprocess("--matrix-lane=default")
    result.stdout.fnmatch_lines(
        ["matrix lane default: required=1 passed=1 failed=0 skipped=0 missing=0 duplicated=0"]
    )
    assert result.ret == 0


# --- REG-LANE-001 empty required set ----------------------------------------------------
def test_empty_required_set_fails(pytester: pytest.Pytester) -> None:
    # A default lane run whose registry declares no keys must fail (nothing is being verified).
    # ``matrix_required_keys`` is set to one real key -- but for the "browser" lane, not
    # "default" -- so the ini-explicit path (not the real, now fully-wired
    # ``tests.matrix.cases.ALL_CASES`` fallback) legitimately yields an empty required set for
    # THIS lane, exactly the scenario this case pins.
    _make(
        pytester,
        ini_required="CASE-001::legacy::browser",
        test_body="def test_noop():\n    assert True\n",
    )
    result = pytester.runpytest_subprocess("--matrix-lane=default")
    result.stdout.fnmatch_lines(["matrix lane default: required=0 *"])
    assert result.ret != 0


# --- REG-LANE-002 deselected required key -----------------------------------------------
def test_deselected_key_fails(pytester: pytest.Pytester) -> None:
    _make(
        pytester,
        ini_required="CASE-001::legacy::default",
        test_body=_MARK + "def test_case():\n    assert True\n",
    )
    result = pytester.runpytest_subprocess("--matrix-lane=default", "-k", "nomatch")
    result.stdout.fnmatch_lines(
        ["matrix lane default: required=1 passed=0 failed=0 skipped=0 missing=1 duplicated=0"]
    )
    assert result.ret != 0


# --- REG-LANE-003 skipped required key --------------------------------------------------
def test_skipped_key_fails(pytester: pytest.Pytester) -> None:
    _make(
        pytester,
        ini_required="CASE-001::legacy::default",
        test_body=_MARK + "def test_case():\n    import pytest\n    pytest.skip('cap')\n",
    )
    result = pytester.runpytest_subprocess("--matrix-lane=default")
    result.stdout.fnmatch_lines(
        ["matrix lane default: required=1 passed=0 failed=0 skipped=1 missing=0 duplicated=0"]
    )
    assert result.ret != 0


# --- REG-LANE-004 duplicated required key -----------------------------------------------
def test_duplicated_key_fails(pytester: pytest.Pytester) -> None:
    body = (
        _MARK
        + "def test_case_a():\n    assert True\n"
        + _MARK
        + "def test_case_b():\n    assert True\n"
    )
    _make(pytester, ini_required="CASE-001::legacy::default", test_body=body)
    result = pytester.runpytest_subprocess("--matrix-lane=default")
    result.stdout.fnmatch_lines(
        ["matrix lane default: required=1 passed=0 failed=0 skipped=0 missing=0 duplicated=1"]
    )
    assert result.ret != 0


# --- REG-LANE-005 missing required key --------------------------------------------------
def test_missing_key_fails(pytester: pytest.Pytester) -> None:
    _make(
        pytester,
        ini_required="CASE-404::legacy::default",  # required but no item declares it
        test_body="def test_unrelated():\n    assert True\n",
    )
    result = pytester.runpytest_subprocess("--matrix-lane=default")
    result.stdout.fnmatch_lines(
        ["matrix lane default: required=1 passed=0 failed=0 skipped=0 missing=1 duplicated=0"]
    )
    assert result.ret != 0


# --- no lane => inert --------------------------------------------------------------------
def test_no_lane_is_inert(pytester: pytest.Pytester) -> None:
    _make(
        pytester,
        ini_required="CASE-001::legacy::default",
        test_body=_MARK + "def test_case():\n    assert True\n",
    )
    result = pytester.runpytest_subprocess()  # no --matrix-lane
    assert result.ret == 0
    result.stdout.no_fnmatch_line("matrix lane*")


# --- capability gating -------------------------------------------------------------------
def test_require_corpus_absent_is_usage_error(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nasyncio_mode = auto\n")
    pytester.makepyfile("def test_noop():\n    assert True\n")
    result = pytester.runpytest_subprocess(
        "--require-corpus", "--corpus-dir", str(pytester.path / "no-corpus")
    )
    assert result.ret == pytest.ExitCode.USAGE_ERROR


def test_require_corpus_present_runs(pytester: pytest.Pytester) -> None:
    corpus = pytester.path / "corpus"
    (corpus / "run-1" / "raw").mkdir(parents=True)
    (corpus / "run-1" / "raw" / "p.json").write_text('{"data": []}', encoding="utf-8")
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nasyncio_mode = auto\n")
    pytester.makepyfile("def test_noop():\n    assert True\n")
    result = pytester.runpytest_subprocess("--require-corpus", "--corpus-dir", str(corpus))
    assert result.ret == 0
