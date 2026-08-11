"""ART-FORMULA-001..006: write_csv (scoutmb.adapters.files.atomic.write_csv) writes a
spreadsheet-formula-injection-prefixed field through csv.DictWriter with NO escaping,
quoting-only defense, or leading-apostrophe defusing -- the raw prefix survives into the
written CSV bytes unchanged. This pins the CURRENT (unmitigated) behavior; no fix is implied.

Six prefixes are characterized, matching the six kinds spreadsheet formula-injection guidance
warns about: '=', '+', '-', '@', a leading tab, and a leading carriage return (both used to
smuggle a formula past naive leading-character-only defenses).
"""

from __future__ import annotations

import csv

import pytest

from scoutmb.adapters.files.atomic import write_csv
from scoutmb.core.models import ClassRecord

_FIELDNAMES = [field.name for field in ClassRecord.__dataclass_fields__.values()]


def _class_record(scout_name: str) -> ClassRecord:
    return ClassRecord(
        scout_name=scout_name,
        attendee_id="90000001",
        class_number="26MB1",
        class_p4_id="2000001",
        class_name="Chess",
        days="MoTuWeTh",
        period_name="A Block",
        start_time="09:00 AM",
        start_time_24h="09:00:00",
        location="Pavilion",
        has_requirements=True,
        class_completed=False,
        raw_class_name="MoTuWeTh - Chess - 26MB1 (Pavilion)",
    )


def _assert_prefix_survives_unchanged(tmp_path, value: str) -> None:
    path = tmp_path / "classes.csv"
    write_csv(path, [_class_record(value)], _FIELDNAMES)

    raw_bytes = path.read_bytes()
    # No leading-apostrophe defusing, no escaping: the raw prefix byte sequence appears
    # verbatim somewhere in the written file.
    assert value.encode("utf-8") in raw_bytes

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["scout_name"] == value  # round-trips to the EXACT unmitigated original


@pytest.mark.matrix_case(case_id="ART-FORMULA-001", context_id="formula", lane="default")
def test_art_formula_001_eq_prefix(tmp_path):
    _assert_prefix_survives_unchanged(tmp_path, "=SUM(A1:A9)")


@pytest.mark.matrix_case(case_id="ART-FORMULA-002", context_id="formula", lane="default")
def test_art_formula_002_plus_prefix(tmp_path):
    _assert_prefix_survives_unchanged(tmp_path, "+1+1")


@pytest.mark.matrix_case(case_id="ART-FORMULA-003", context_id="formula", lane="default")
def test_art_formula_003_minus_prefix(tmp_path):
    _assert_prefix_survives_unchanged(tmp_path, "-1-1")


@pytest.mark.matrix_case(case_id="ART-FORMULA-004", context_id="formula", lane="default")
def test_art_formula_004_at_prefix(tmp_path):
    _assert_prefix_survives_unchanged(tmp_path, "@SUM(A1:A9)")


@pytest.mark.matrix_case(case_id="ART-FORMULA-005", context_id="formula", lane="default")
def test_art_formula_005_tab_prefix(tmp_path):
    _assert_prefix_survives_unchanged(tmp_path, "\t=cmd|'/c calc'!A1")


@pytest.mark.matrix_case(case_id="ART-FORMULA-006", context_id="formula", lane="default")
def test_art_formula_006_cr_prefix(tmp_path):
    _assert_prefix_survives_unchanged(tmp_path, "\r=cmd|'/c calc'!A1")
