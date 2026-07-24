"""Phase A aggregate baseline capture/check (Task 22, step 10-11).

Writes/checks ``tests/baselines/phase_a.json``: a small, deterministic, AGGREGATE-ONLY
snapshot of (a) the full matrix-case registry's case ids, (b) request/row counts derived from
the canonical synthetic scale profile (``tests.factories.scale.canonical_profile`` /
``build_dataset`` -- never ``raw_data/``), (c) the scoped Phase A coverage percentages per area
(from a ``coverage json`` report), and (d) the reviewed branch-exclusion ids.

The written file NEVER contains: absolute paths, hostnames/usernames, timestamps, hashes of
private data, free-form descriptions, or any key outside the declared schema. ``--update`` is a
manual, explicit, reviewed action -- never run automatically by CI (CI only ever runs
``--check``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.check_phase_a_coverage import compute_area_coverage, load_exclusions  # noqa: E402

SCHEMA_VERSION = 1
_DECLARED_KEYS = frozenset(
    {
        "schema_version",
        "profile_version",
        "profile_id",
        "case_ids",
        "request_counts",
        "row_counts",
        "coverage_areas",
        "branch_exclusion_ids",
    }
)

# A loose "looks like something private/free-form" detector for the reject-list in the plan:
# absolute paths, hostnames/usernames, timestamps, hashes. Applied to every string leaf value.
_PATH_LIKE = re.compile(r"[\\/]")
_TIMESTAMP_LIKE = re.compile(r"\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2})?")
_HASH_LIKE = re.compile(r"^[0-9a-fA-F]{32,}$")
_AT_SIGN = re.compile(r"@")


def _assert_safe_string(value: str, where: str) -> None:
    if _PATH_LIKE.search(value):
        raise ValueError(f"{where}: looks like a path ({value!r})")
    if _TIMESTAMP_LIKE.search(value):
        raise ValueError(f"{where}: looks like a timestamp ({value!r})")
    if _HASH_LIKE.match(value):
        raise ValueError(f"{where}: looks like a hash ({value!r})")
    if _AT_SIGN.search(value):
        raise ValueError(f"{where}: looks like an email/hostname ({value!r})")


def _assert_aggregate_only(payload: dict, *, where: str = "$") -> None:
    """Recursively rejects anything that is not a plain aggregate-shaped value: numbers,
    sorted lists of strings/ids, or nested dicts of the same. Also rejects unknown top-level
    keys."""
    extra_keys = set(payload) - _DECLARED_KEYS
    if extra_keys:
        raise ValueError(f"unknown/undeclared key(s): {sorted(extra_keys)}")
    missing_keys = _DECLARED_KEYS - set(payload)
    if missing_keys:
        raise ValueError(f"missing declared key(s): {sorted(missing_keys)}")

    def walk(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, sub in sorted(value.items()):
                if not isinstance(key, str):
                    raise ValueError(f"{path}: non-string key {key!r}")
                _assert_safe_string(key, f"{path} key")
                walk(sub, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str):
            _assert_safe_string(value, path)
        elif isinstance(value, (int, float)):
            pass
        else:
            raise ValueError(f"{path}: unsupported value type {type(value).__name__}")

    walk(payload, where)


def _canonical_profile_and_dataset(profile_name: str):
    from tests.factories.scale import build_dataset, canonical_profile

    if profile_name != "canonical-22":
        raise SystemExit(f"unsupported --profile {profile_name!r} (only 'canonical-22' is wired)")
    scale_profile = canonical_profile()
    dataset = build_dataset(scale_profile)
    return scale_profile, dataset


def compute_baseline(profile_name: str, coverage_json_path: Path) -> dict:
    from tests.matrix.cases import ALL_CASES

    scale_profile, dataset = _canonical_profile_and_dataset(profile_name)

    schedule_requests = len(dataset.attendees)
    requirement_requests = len(dataset.deduped_class_ids)
    request_counts = {
        "schedule_requests": schedule_requests,
        "requirement_requests": requirement_requests,
        "total_requests": schedule_requests + requirement_requests,
    }
    row_counts = {
        "attendee_count": len(dataset.attendees),
        "raw_class_count": len(dataset.raw_class_rows),
        "deduplicated_class_count": len(dataset.deduped_class_ids),
        "requirement_count": len(dataset.requirement_rows),
    }

    default_boundaries = Path(__file__).resolve().parent.parent / "tests/matrix/boundaries.py"
    areas, exclusions = load_exclusions(default_boundaries)
    coverage_data = json.loads(coverage_json_path.read_text(encoding="utf-8"))
    coverage_by_area = compute_area_coverage(coverage_data, areas)
    coverage_areas = {
        area_id: {
            "statement_pct": round(coverage.statement_pct, 2),
            "branch_pct": round(coverage.branch_pct, 2),
        }
        for area_id, coverage in sorted(coverage_by_area.items())
    }

    case_ids = sorted({case.case_id for case in ALL_CASES})
    branch_exclusion_ids = sorted(exclusion.exclusion_id for exclusion in exclusions)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "profile_version": scale_profile.profile_version,
        "profile_id": profile_name,
        "case_ids": case_ids,
        "request_counts": request_counts,
        "row_counts": row_counts,
        "coverage_areas": coverage_areas,
        "branch_exclusion_ids": branch_exclusion_ids,
    }
    _assert_aggregate_only(payload)
    return payload


def _mismatches(computed: dict, stored: dict) -> list[str]:
    problems: list[str] = []
    all_keys = sorted(set(computed) | set(stored))
    for key in all_keys:
        if computed.get(key) != stored.get(key):
            problems.append(key)
    return sorted(problems)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="e.g. canonical-22")
    parser.add_argument("--coverage-json", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--update", type=Path, help="Write the captured baseline to this path.")
    mode.add_argument("--check", type=Path, help="Compare the captured baseline to this path.")
    args = parser.parse_args(argv)

    payload = compute_baseline(args.profile, args.coverage_json)

    if args.update is not None:
        args.update.parent.mkdir(parents=True, exist_ok=True)
        args.update.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"phase-a baseline: wrote {args.update}")
        return 0

    stored_path = args.check
    if not stored_path.exists():
        print(f"phase-a baseline: missing file {stored_path}")
        return 1
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    problems = _mismatches(payload, stored)
    if not problems:
        print("phase-a baseline: match")
        return 0
    for key in problems:
        print(f"mismatch: {key}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
