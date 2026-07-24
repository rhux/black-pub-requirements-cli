"""Scoped coverage-area gate for Phase A (Task 22, step 8).

Reads a ``coverage json -o <path>`` report and, for each ``CoverageAreaSpec`` in
``tests.matrix.boundaries.COVERAGE_AREAS``, computes an aggregate statement-coverage percent
and branch-coverage percent across that area's files, then checks two independent things:

1. Every currently-missing statement (a line in a file's ``missing_lines``) and every
   currently-missing branch arc (a pair in a file's ``missing_branches``) must be matched by an
   exact, reviewed ``BranchExclusion`` (``branch_to=None`` for a statement, an int for one
   specific branch arc) -- unless ``--require-complete`` is omitted, in which case unexplained
   gaps are only reported, not a hard failure (used for ad-hoc local inspection; every real CI
   invocation passes ``--require-complete``).
2. Every exclusion in that list still corresponds to something ACTUALLY missing right now --
   a "stale" exclusion (its line/arc is already covered) is itself a failure, so exclusions
   cannot silently accumulate as coverage improves.

``--baseline PATH`` additionally loads a captured ``tests/baselines/phase_a.json`` and fails if
either area percent has dropped below its checked-in floor.

This tool never reads ``raw_data/`` and never needs it: every check here is purely a function of
the coverage JSON plus the checked-in exclusion list / baseline file.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


@dataclass(frozen=True, slots=True)
class AreaCoverage:
    area_id: str
    statement_pct: float
    branch_pct: float
    missing_statements: frozenset[tuple[str, int]]  # (file, line)
    missing_branches: frozenset[tuple[str, int, int]]  # (file, line, branch_to)


def _load_boundaries_module(path: Path) -> ModuleType:
    """Loads a boundaries.py-shaped module by real dotted import (not an isolated file-spec
    exec), because tests.matrix.boundaries itself does ``from tests.matrix.model import
    Domain`` -- it is only importable as part of the real ``tests`` package, not standalone."""
    resolved = path.resolve()
    repo_root = Path.cwd().resolve()
    try:
        relative = resolved.relative_to(repo_root)
    except ValueError as exc:
        raise SystemExit(
            f"--exclusions must be a path under the current working directory ({repo_root}); "
            f"got {resolved}"
        ) from exc
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    dotted = ".".join(relative.with_suffix("").parts)
    return importlib.import_module(dotted)


def load_exclusions(path: Path) -> tuple[tuple, tuple]:
    """Returns (COVERAGE_AREAS, EXCLUSIONS) from a boundaries.py-shaped module file."""
    module = _load_boundaries_module(path)
    return tuple(module.COVERAGE_AREAS), tuple(module.EXCLUSIONS)


def compute_area_coverage(coverage_data: dict, areas: tuple) -> dict[str, AreaCoverage]:
    results: dict[str, AreaCoverage] = {}
    files = coverage_data.get("files", {})
    for area in areas:
        total_statements = 0
        covered_statements = 0
        total_branches = 0
        covered_branches = 0
        missing_statements: set[tuple[str, int]] = set()
        missing_branches: set[tuple[str, int, int]] = set()
        for file_name in area.files:
            file_data = files.get(file_name)
            if file_data is None:
                continue
            summary = file_data.get("summary", {})
            total_statements += summary.get("num_statements", 0)
            covered_statements += summary.get("covered_lines", 0)
            total_branches += summary.get("num_branches", 0)
            covered_branches += summary.get("covered_branches", 0)
            for line in file_data.get("missing_lines", []):
                missing_statements.add((file_name, line))
            for pair in file_data.get("missing_branches", []):
                missing_branches.add((file_name, pair[0], pair[1]))
        statement_pct = 100.0 * covered_statements / total_statements if total_statements else 100.0
        branch_pct = 100.0 * covered_branches / total_branches if total_branches else 100.0
        results[area.area_id] = AreaCoverage(
            area_id=area.area_id,
            statement_pct=statement_pct,
            branch_pct=branch_pct,
            missing_statements=frozenset(missing_statements),
            missing_branches=frozenset(missing_branches),
        )
    return results


def _area_for_file(areas: tuple, file_name: str) -> str | None:
    for area in areas:
        if file_name in area.files:
            return area.area_id
    return None


def check_unexplained_gaps(
    areas: tuple, exclusions: tuple, coverage_by_area: dict[str, AreaCoverage]
) -> list[str]:
    """Missing statements/branches with no matching exclusion. Gated by --require-complete."""
    problems: list[str] = []

    exclusion_statements: dict[tuple[str, int], object] = {}
    exclusion_branches: dict[tuple[str, int, int], object] = {}
    for exclusion in exclusions:
        if exclusion.branch_to is None:
            exclusion_statements[(exclusion.file, exclusion.line)] = exclusion
        else:
            exclusion_branches[(exclusion.file, exclusion.line, exclusion.branch_to)] = exclusion

    for area in areas:
        coverage = coverage_by_area.get(area.area_id)
        if coverage is None:
            continue
        for stmt_key in sorted(coverage.missing_statements):
            if stmt_key not in exclusion_statements:
                problems.append(
                    f"unexplained missing statement: {stmt_key[0]}:{stmt_key[1]} "
                    f"(area={area.area_id})"
                )
        for branch_key in sorted(coverage.missing_branches):
            if branch_key not in exclusion_branches:
                problems.append(
                    f"unexplained missing branch: {branch_key[0]}:{branch_key[1]}->"
                    f"{branch_key[2]} (area={area.area_id})"
                )
    return sorted(problems)


def check_stale_exclusions(
    exclusions: tuple, coverage_by_area: dict[str, AreaCoverage]
) -> list[str]:
    """Exclusions that no longer match anything actually missing. ALWAYS enforced -- an
    exclusion must never silently accumulate past the moment its gap gets closed."""
    problems: list[str] = []
    all_missing_statements: set[tuple[str, int]] = set()
    all_missing_branches: set[tuple[str, int, int]] = set()
    for coverage in coverage_by_area.values():
        all_missing_statements |= coverage.missing_statements
        all_missing_branches |= coverage.missing_branches

    for exclusion in exclusions:
        if exclusion.branch_to is None:
            key_stmt = (exclusion.file, exclusion.line)
            if key_stmt not in all_missing_statements:
                problems.append(
                    f"stale exclusion {exclusion.exclusion_id}: "
                    f"{exclusion.file}:{exclusion.line} is no longer a missing statement"
                )
        else:
            key_branch = (exclusion.file, exclusion.line, exclusion.branch_to)
            if key_branch not in all_missing_branches:
                problems.append(
                    f"stale exclusion {exclusion.exclusion_id}: "
                    f"{exclusion.file}:{exclusion.line}->{exclusion.branch_to} "
                    "is no longer a missing branch"
                )
    return sorted(problems)


def check_floors(
    coverage_by_area: dict[str, AreaCoverage],
    floors: dict[str, tuple[float, float]],
) -> list[str]:
    problems: list[str] = []
    for area_id, (min_statement, min_branch) in sorted(floors.items()):
        coverage = coverage_by_area.get(area_id)
        if coverage is None:
            problems.append(f"floor check: area {area_id} not present in coverage data")
            continue
        if coverage.statement_pct < min_statement:
            problems.append(
                f"floor breach: {area_id} statement coverage {coverage.statement_pct:.2f}% "
                f"< floor {min_statement:.2f}%"
            )
        if coverage.branch_pct < min_branch:
            problems.append(
                f"floor breach: {area_id} branch coverage {coverage.branch_pct:.2f}% "
                f"< floor {min_branch:.2f}%"
            )
    return sorted(problems)


def _floors_from_baseline(baseline_path: Path) -> dict[str, tuple[float, float]]:
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    areas = payload.get("coverage_areas", {})
    floors: dict[str, tuple[float, float]] = {}
    for area_id, values in areas.items():
        floors[area_id] = (
            float(values.get("statement_pct", 0.0)),
            float(values.get("branch_pct", 0.0)),
        )
    return floors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-json", required=True, type=Path)
    parser.add_argument(
        "--exclusions",
        type=Path,
        help="Path to tests/matrix/boundaries.py (or an equivalent module) exposing "
        "COVERAGE_AREAS and EXCLUSIONS.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Path to a captured tests/baselines/phase_a.json; ALSO checks per-area floors.",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail if any missing statement/branch is not matched by an exact exclusion.",
    )
    parser.add_argument(
        "--min-statement-pct",
        type=float,
        default=95.0,
        help="Placeholder floor used only when --baseline is not given; the real per-area "
        "floors come from tests/baselines/phase_a.json via --baseline.",
    )
    parser.add_argument(
        "--min-branch-pct",
        type=float,
        default=80.0,
        help="Placeholder floor used only when --baseline is not given; the real per-area "
        "floors come from tests/baselines/phase_a.json via --baseline.",
    )
    args = parser.parse_args(argv)

    if args.exclusions is None and args.baseline is None:
        parser.error("at least one of --exclusions or --baseline is required")

    coverage_data = json.loads(args.coverage_json.read_text(encoding="utf-8"))

    if args.exclusions is not None:
        areas, exclusions = load_exclusions(args.exclusions)
    else:
        # --baseline alone still needs COVERAGE_AREAS to know which files to aggregate; load it
        # from the repo's own boundaries module by default.
        default_boundaries = Path(__file__).resolve().parent.parent / "tests/matrix/boundaries.py"
        areas, exclusions = load_exclusions(default_boundaries)

    coverage_by_area = compute_area_coverage(coverage_data, areas)

    for area_id in sorted(coverage_by_area):
        coverage = coverage_by_area[area_id]
        print(
            f"area {area_id}: statements={coverage.statement_pct:.2f}% "
            f"branches={coverage.branch_pct:.2f}%"
        )

    # ALWAYS enforced: a stale exclusion (its gap already closed) is a failure regardless of
    # --require-complete, so exclusions never silently accumulate as coverage improves.
    hard_problems = check_stale_exclusions(exclusions, coverage_by_area)

    if args.baseline is not None:
        floors = _floors_from_baseline(args.baseline)
    else:
        floors = {area.area_id: (args.min_statement_pct, args.min_branch_pct) for area in areas}
    hard_problems += check_floors(coverage_by_area, floors)

    # Gated by --require-complete: an unexplained gap is reported always, but only fails the
    # run when the caller asked for a complete-coverage check (real CI/Gate 1b invocations do).
    soft_problems = check_unexplained_gaps(areas, exclusions, coverage_by_area)

    for problem in sorted(hard_problems):
        print(f"FAIL: {problem}")
    for problem in soft_problems:
        marker = (
            "FAIL" if args.require_complete else "NOTE (not enforced, --require-complete not set)"
        )
        print(f"{marker}: {problem}")

    if hard_problems or (args.require_complete and soft_problems):
        return 1

    if not hard_problems and not soft_problems:
        print("phase-a coverage: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
