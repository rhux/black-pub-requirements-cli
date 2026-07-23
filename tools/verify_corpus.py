"""Reproduce the design spec's corpus counts. Aggregate output only — never PII.

The raw payloads mix two row species that share a ``data`` array: schedule-class rows
and requirement rows. The verifier classifies each row with named schema predicates
(exact field-name match) rather than the completion-flag pair alone, because 103 schedule
rows carry ``(COMPLETED_REQ_FLAG, COMPLETED_CLASS_FLAG) == (None, None)`` and would otherwise
be miscounted as requirements. Marginals (flags/types/shapes/note/empty) are computed over
requirement rows only. No private value is ever emitted — only counts and schema field names.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Any

# The two stable upstream schemas, matched by exact field-name set.
SCHEDULE_FIELDS = frozenset(
    {
        "CLASS_COMPLETED",
        "CLASS_NAME",
        "CLASS_NAME_ONLY",
        "CLASS_NBR",
        "CLASS_STIME",
        "HAS_REQ",
        "LOCATION_ROOM_NAME",
        "PERIOD_NAME",
        "SES_LKP_PERIOD_TYPE_ID",
        "STIME",
        "classP4ID",
    }
)
REQUIREMENT_FIELDS = frozenset(
    {
        "COMPLETED_CLASS_FLAG",
        "COMPLETED_REQ_FLAG",
        "MDM_LKP_BADGE_REQ_ID",
        "MDM_LKP_BADGE_REQ_TYPE_ID",
        "MERIT_BADGE_NAME",
        "PRESENT_DAYS",
        "REQ_DESCR",
        "REQ_NBR",
        "REQ_NBR_WEB_DISPLAY",
        "REQ_ON_EVENT",
    }
)
_KNOWN_FIELDS = SCHEDULE_FIELDS | REQUIREMENT_FIELDS


def number_shape(value: str) -> str:
    shaped = re.sub(r"[A-Z]", "A", str(value))
    shaped = re.sub(r"[a-z]", "a", shaped)
    return re.sub(r"[0-9]+", "N", shaped)


def is_schedule_row(row: object) -> bool:
    return isinstance(row, dict) and frozenset(row) == SCHEDULE_FIELDS


def is_requirement_row(row: object) -> bool:
    return isinstance(row, dict) and frozenset(row) == REQUIREMENT_FIELDS


def classify_row(row: object) -> str:
    if not isinstance(row, dict):
        return "unrecognized"
    schedule = is_schedule_row(row)
    requirement = is_requirement_row(row)
    if schedule == requirement:
        return "unrecognized"
    return "schedule" if schedule else "requirement"


def unrecognized_reason(row: object) -> str:
    """A redacted reason string — never echoes a row value or an unknown field name."""
    if not isinstance(row, dict):
        return f"non-mapping data row (type={type(row).__name__})"
    known = sorted(f for f in row if f in _KNOWN_FIELDS)
    extra = sum(1 for f in row if f not in _KNOWN_FIELDS)
    return f"mapping row not matching one schema (known_fields={known}, extra_field_count={extra})"


def _empty_summary() -> dict[str, Any]:
    return {
        "raw_payloads": 0,
        "unreadable_payloads": 0,
        "schedule_payloads": 0,
        "requirement_payloads": 0,
        "data_rows": 0,
        "schedule_rows": 0,
        "requirement_rows": 0,
        "unrecognized_rows": 0,
        "deduped_classes": 0,
        "empty_display_rows": 0,
        "note_rows": 0,
        "flag_combos": {},
        "type_marginals": {},
        "number_shapes": {},
        "requirement_schemas": 0,
        "unrecognized_reasons": [],
    }


def summarize_run(run_dir: Path) -> dict[str, Any]:
    raw = run_dir / "raw"
    payloads = sorted(raw.glob("*.json")) if raw.is_dir() else []
    unreadable = 0
    schedule_payloads = requirement_payloads = 0
    data_rows = schedule_rows = requirement_rows = unrecognized_rows = 0
    deduped_classes = empty_display_rows = note_rows = 0
    flags: collections.Counter[str] = collections.Counter()
    types: collections.Counter[str] = collections.Counter()
    shapes: collections.Counter[str] = collections.Counter()
    requirement_schema_seen = False
    reasons: list[str] = []
    for p in payloads:
        try:
            data = json.loads(p.read_text(encoding="utf-8")).get("data") or []
        except (OSError, json.JSONDecodeError):
            unreadable += 1
            continue
        payload_class_ids: set[Any] = set()
        payload_has_schedule = payload_has_requirement = False
        for row in data:
            data_rows += 1
            kind = classify_row(row)
            if kind == "schedule":
                schedule_rows += 1
                payload_has_schedule = True
                payload_class_ids.add(row.get("classP4ID"))
            elif kind == "requirement":
                requirement_rows += 1
                payload_has_requirement = True
                requirement_schema_seen = True
                flags[str((row.get("COMPLETED_REQ_FLAG"), row.get("COMPLETED_CLASS_FLAG")))] += 1
                types[str(row.get("MDM_LKP_BADGE_REQ_TYPE_ID"))] += 1
                display = row.get("REQ_NBR_WEB_DISPLAY") or ""
                shapes[number_shape(display)] += 1
                if display == "":
                    empty_display_rows += 1
                elif display == "Note.":
                    note_rows += 1
            else:
                unrecognized_rows += 1
                reasons.append(unrecognized_reason(row))
        deduped_classes += len(payload_class_ids)
        if payload_has_schedule:
            schedule_payloads += 1
        if payload_has_requirement:
            requirement_payloads += 1
    return {
        "raw_payloads": len(payloads),
        "unreadable_payloads": unreadable,
        "schedule_payloads": schedule_payloads,
        "requirement_payloads": requirement_payloads,
        "data_rows": data_rows,
        "schedule_rows": schedule_rows,
        "requirement_rows": requirement_rows,
        "unrecognized_rows": unrecognized_rows,
        "deduped_classes": deduped_classes,
        "empty_display_rows": empty_display_rows,
        "note_rows": note_rows,
        "flag_combos": dict(flags),
        "type_marginals": dict(types),
        "number_shapes": dict(shapes),
        "requirement_schemas": 1 if requirement_schema_seen else 0,
        "unrecognized_reasons": reasons,
    }


def _merge(acc: dict[str, Any], one: dict[str, Any]) -> None:
    for key in (
        "raw_payloads",
        "unreadable_payloads",
        "schedule_payloads",
        "requirement_payloads",
        "data_rows",
        "schedule_rows",
        "requirement_rows",
        "unrecognized_rows",
        "deduped_classes",
        "empty_display_rows",
        "note_rows",
    ):
        acc[key] += one[key]
    for key in ("flag_combos", "type_marginals", "number_shapes"):
        merged = collections.Counter(acc[key])
        merged.update(one[key])
        acc[key] = dict(merged)
    acc["requirement_schemas"] = max(acc["requirement_schemas"], one["requirement_schemas"])
    acc["unrecognized_reasons"] = acc["unrecognized_reasons"] + one["unrecognized_reasons"]


def aggregate_corpus(corpus_dir: Path) -> dict[str, Any]:
    """Sum ``summarize_run`` over every run directory (a child holding a ``raw/`` subdir)."""
    acc = _empty_summary()
    for run in sorted(p for p in corpus_dir.iterdir() if p.is_dir()):
        if not (run / "raw").is_dir():
            continue
        _merge(acc, summarize_run(run))
    return acc


def _print_summary(summary: dict[str, Any]) -> None:
    # Aggregate counts and schema names only — never a path, run name, or private value.
    for key in (
        "raw_payloads",
        "schedule_payloads",
        "requirement_payloads",
        "data_rows",
        "schedule_rows",
        "requirement_rows",
        "unrecognized_rows",
        "deduped_classes",
        "empty_display_rows",
        "note_rows",
        "requirement_schemas",
    ):
        print(f"{key}: {summary[key]}")
    print(f"schedule_schema_fields: {sorted(SCHEDULE_FIELDS)}")
    print(f"requirement_schema_fields: {sorted(REQUIREMENT_FIELDS)}")
    for combo, n in sorted(summary["flag_combos"].items()):
        print(f"    flags {combo}: {n}")
    for type_id, n in sorted(summary["type_marginals"].items()):
        print(f"    type {type_id}: {n}")
    for shape, n in sorted(summary["number_shapes"].items(), key=lambda kv: -kv[1]):
        print(f"    shape {shape!r}: {n}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument(
        "--require-known-schema",
        action="store_true",
        help="Exit non-zero if any data row matches neither schedule nor requirement schema.",
    )
    args = parser.parse_args(argv)
    if not args.corpus.is_dir():
        print("error: corpus directory not found", file=sys.stderr)  # bounded, no path echoed
        return 2
    summary = aggregate_corpus(args.corpus)
    _print_summary(summary)
    if args.require_known_schema and summary["unrecognized_rows"]:
        # Redacted reasons only (schema field names + counts) — never a private value.
        for reason in summary["unrecognized_reasons"]:
            print(f"error: {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
