from tests.matrix.boundaries import BranchExclusion, CoverageAreaSpec
from tools.check_phase_a_coverage import (
    check_missing_files,
    check_stale_exclusions,
    check_unexplained_gaps,
    compute_area_coverage,
)


def _file_summary(missing_lines=(), missing_branches=(), num_statements=10, num_branches=2):
    covered_lines = num_statements - len(missing_lines)
    covered_branches = num_branches - len(missing_branches)
    return {
        "summary": {
            "num_statements": num_statements,
            "covered_lines": covered_lines,
            "num_branches": num_branches,
            "covered_branches": covered_branches,
        },
        "missing_lines": list(missing_lines),
        "missing_branches": [list(pair) for pair in missing_branches],
    }


def test_missing_file_never_in_coverage_report_fails_loudly():
    """CORE BUG: a file that's never imported/executed by any test never appears in the
    coverage JSON's files dict at all (coverage.py `include=` behavior) -- compute_area_coverage
    must not silently treat that as 100% covered, and check_missing_files must catch it."""
    area = CoverageAreaSpec(area_id="a", files=("missing_file.py",))
    coverage_data = {"files": {}}

    coverage = compute_area_coverage(coverage_data, (area,))["a"]
    assert coverage.statement_pct == 100.0  # the silent-100% behavior this test locks a check on

    problems = check_missing_files((area,), coverage_data)
    assert problems == [
        "file never appears in coverage report: missing_file.py (area=a) "
        "-- it was likely never imported/executed by any test"
    ]


def test_fully_covered_area_no_exclusions_needed():
    area = CoverageAreaSpec(area_id="a", files=("clean.py",))
    coverage_data = {"files": {"clean.py": _file_summary()}}

    coverage_by_area = compute_area_coverage(coverage_data, (area,))
    assert coverage_by_area["a"].statement_pct == 100.0
    assert coverage_by_area["a"].branch_pct == 100.0
    assert check_missing_files((area,), coverage_data) == []
    assert check_stale_exclusions((), coverage_by_area) == []
    assert check_unexplained_gaps((area,), (), coverage_by_area) == []


def test_gap_correctly_matched_by_valid_exclusion():
    area = CoverageAreaSpec(area_id="a", files=("gappy.py",))
    coverage_data = {"files": {"gappy.py": _file_summary(missing_lines=[5])}}
    exclusion = BranchExclusion(
        exclusion_id="EX-1",
        area_id="a",
        file="gappy.py",
        line=5,
        branch_to=None,
        rationale="unreachable defensive branch",
        review_reference="PR#1",
    )

    coverage_by_area = compute_area_coverage(coverage_data, (area,))
    assert check_stale_exclusions((exclusion,), coverage_by_area) == []
    assert check_unexplained_gaps((area,), (exclusion,), coverage_by_area) == []


def test_stale_exclusion_correctly_detected_and_fails():
    area = CoverageAreaSpec(area_id="a", files=("fixed.py",))
    coverage_data = {"files": {"fixed.py": _file_summary()}}  # gap is now fully covered
    exclusion = BranchExclusion(
        exclusion_id="EX-2",
        area_id="a",
        file="fixed.py",
        line=5,
        branch_to=None,
        rationale="was unreachable",
        review_reference="PR#2",
    )

    coverage_by_area = compute_area_coverage(coverage_data, (area,))
    problems = check_stale_exclusions((exclusion,), coverage_by_area)
    assert problems == ["stale exclusion EX-2: fixed.py:5 is no longer a missing statement"]
