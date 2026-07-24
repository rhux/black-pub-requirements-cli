from tests.matrix.boundaries import BranchExclusion, CoverageAreaSpec
from tools.check_phase_a_coverage import (
    AreaCoverage,
    check_floors,
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


def test_floor_check_tolerates_baseline_rounding_precision_noise():
    """REGRESSION: tests/baselines/phase_a.json stores floors rounded to 2 decimal places (e.g.
    99.7), but the current run's raw coverage.py percentage is full precision (e.g.
    99.69604863221885) -- fractionally below 99.7 even though it rounds to the exact same
    displayed value. A strict `current < floor` comparison at mismatched precision made this a
    false floor breach for a coverage state that is, in fact, identical to what produced the
    baseline. check_floors must round the current value to the same 2-decimal precision as the
    stored floor before comparing, so this is a PASS, not a breach."""
    coverage_by_area = {
        "pdf": AreaCoverage(
            area_id="pdf",
            statement_pct=99.69604863221885,  # rounds to 99.70, but is < 99.7 at full precision
            branch_pct=98.53001,  # rounds to 98.53, but is < 98.53 at full precision
            missing_statements=frozenset(),
            missing_branches=frozenset(),
        ),
    }
    floors = {"pdf": (99.7, 98.53)}  # the rounded-2-decimal floor as stored in the baseline file

    assert check_floors(coverage_by_area, floors) == []


def test_floor_check_still_catches_a_genuine_regression():
    """A current value that rounds to a LOWER 2-decimal percentage than the floor must still be
    reported as a real floor breach -- the rounding tolerance must not mask actual regressions."""
    coverage_by_area = {
        "pdf": AreaCoverage(
            area_id="pdf",
            statement_pct=99.694,  # rounds to 99.69, genuinely below a 99.70 floor
            branch_pct=98.53,
            missing_statements=frozenset(),
            missing_branches=frozenset(),
        ),
    }
    floors = {"pdf": (99.7, 98.53)}

    problems = check_floors(coverage_by_area, floors)
    assert problems == ["floor breach: pdf statement coverage 99.69% < floor 99.70%"]
