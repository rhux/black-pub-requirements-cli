"""Exact field sets, not substring scans.

A substring scan for "90000001" passes if the ID moves to a field the scan does not know
about. Field-set equality fails when ANY unexpected key appears.
"""

from __future__ import annotations

import json
import re
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

# Only the two the 2a record shape can actually carry; see tests/goldens/fixture.py for why
# session/raw-payload sentinels are 2b's, not ours.
from tests.goldens.fixture import SENTINEL_QR_TOKEN, SENTINEL_UPSTREAM_ID

from scoutmb.core.models import ClassRecord, RequirementRecord

SENTINELS = {"upstream_id": SENTINEL_UPSTREAM_ID, "qr_token": SENTINEL_QR_TOKEN}

_EXPECTED_CLASS = [f.name for f in fields(ClassRecord) if f.name != "attendee_id"] + ["output_id"]
_EXPECTED_REQ = [f.name for f in fields(RequirementRecord) if f.name != "attendee_id"] + [
    "output_id"
]


def _embedded(report_html: str) -> dict:
    match = re.search(r'<script id="report-data"[^>]*>(.*?)</script>', report_html, re.S)
    assert match, "report-data block not found"
    return json.loads(match.group(1))


@pytest.fixture()
def rendered(tmp_path: Path) -> dict:
    """Render the SENTINEL fixture, not the clean golden fixture."""
    import scout_schedule_cli as legacy
    from tests.goldens.fixture import sentinel_results

    legacy.write_outputs(
        tmp_path,
        sentinel_results(),
        generate_html=True,
        generate_email_report=True,
        run_identity=legacy.RunIdentity(),
    )
    return _embedded((tmp_path / "report.html").read_text(encoding="utf-8"))


def test_class_rows_have_exactly_the_shareable_field_set(rendered: dict) -> None:
    for row in rendered["classes"]:
        assert sorted(row) == sorted(_EXPECTED_CLASS)


_EXPECTED_SCOUT = ["name", "output_id", "class_count", "requirement_count", "error_count"]
_EXPECTED_ERROR = ["scout_name", "output_id", "error"]
# annotate_requirement_statuses adds these display-only keys to requirement rows.
_INFERENCE_KEYS = {
    "requirement_path",
    "parent_requirement_number",
    "calculated_status",
    "calculated_status_reason",
    "completed_subrequirements",
    "total_subrequirements",
    "choice_required_count",
}


def test_scout_rows_have_exactly_the_shareable_field_set(rendered: dict) -> None:
    for row in rendered["scouts"]:
        assert list(row) == _EXPECTED_SCOUT


def test_error_rows_have_exactly_the_shareable_field_set(rendered: dict) -> None:
    for row in rendered["errors"]:
        assert list(row) == _EXPECTED_ERROR


def test_requirement_rows_have_exactly_the_shareable_field_set(rendered: dict) -> None:
    """Exact, not a subset: a subset check passes when a leaked field is ADDED, which is the
    only direction that matters here."""
    for row in rendered["requirements"]:
        assert set(row) - _INFERENCE_KEYS == set(_EXPECTED_REQ), sorted(
            set(row) - _INFERENCE_KEYS ^ set(_EXPECTED_REQ)
        )


def test_no_sentinel_reaches_the_shareable_report(rendered: dict) -> None:
    """Only meaningful because sentinel_results() PLACES each sentinel in the corresponding
    forbidden position. Asserting the absence of a value the fixture never contained is a
    test that cannot fail."""
    text = json.dumps(rendered)
    for name, sentinel in SENTINELS.items():
        assert sentinel not in text, f"{name} leaked into report.html"


def test_unresolved_attempt_carries_null_output_id(rendered: dict) -> None:
    unreached = [s for s in rendered["scouts"] if s["name"] == "Morgan Unreached"]
    assert len(unreached) == 1
    assert unreached[0]["output_id"] is None


def test_two_unresolved_attempts_do_not_merge(tmp_path: Path) -> None:
    """Null identity must not become a grouping key: two unreached attendees stay two rows."""
    import scout_schedule_cli as legacy

    from scoutmb.core.models import ScoutResult

    results = [
        ScoutResult(
            name="A Unreached", qr_url="https://x.invalid/a", attendee_id="", errors=("t",)
        ),
        ScoutResult(
            name="B Unreached", qr_url="https://x.invalid/b", attendee_id="", errors=("t",)
        ),
    ]
    legacy.write_outputs(tmp_path, results, generate_html=True, run_identity=legacy.RunIdentity())
    rows = _embedded((tmp_path / "report.html").read_text(encoding="utf-8"))["scouts"]

    assert len(rows) == 2
    assert all(row["output_id"] is None for row in rows)
    assert {row["name"] for row in rows} == {"A Unreached", "B Unreached"}


def test_two_blank_identity_attendees_with_requirements_fail_loudly(tmp_path: Path) -> None:
    """The real merge-risk path, not the `scouts` summary list.

    test_two_unresolved_attempts_do_not_merge (above) only proves two blank-identity
    ScoutResults stay two rows in the `scouts` summary -- that list is built via unconditional
    `.append()` in ReportingService._report_data and was never at risk of merging regardless of
    identity. The actual risk lives in _annotate_requirement_statuses/_build_missing_requirements,
    which group requirement rows by _attendee_key_for's `f"name:{scout_name}"` fallback when both
    output_id and attendee_id are blank. This test does NOT exercise that merge path directly --
    ReportingService.publish's `_assert_blank_identity_has_no_records(results)` guard is the
    first statement in `publish` and raises before _annotate_requirement_statuses/
    _build_missing_requirements ever run, so this test only proves the guard fires and blocks
    the write BEFORE those functions execute (and that nothing is partially written). It is a
    regression test for the guard itself, not a demonstration of the merge it prevents.
    """
    import scout_schedule_cli as legacy

    from scoutmb.core.models import RequirementRecord, ScoutResult

    def _requirement(number: str) -> RequirementRecord:
        return RequirementRecord(
            scout_name="Same Name",
            attendee_id="",
            class_number="26MB1",
            class_p4_id="2000001",
            merit_badge_name="Chess",
            requirement_id=f"r-{number}",
            requirement_type_id="1",
            requirement_number=number,
            description=f"Requirement {number} description.",
            completed_requirement=False,
            completed_class=False,
            requirement_on_event=True,
            present_days="MoTuWeTh",
        )

    results = [
        ScoutResult(
            name="Same Name",
            qr_url="https://x.invalid/a",
            attendee_id="",
            requirements=(_requirement("1"),),
            errors=("t",),
        ),
        ScoutResult(
            name="Same Name",
            qr_url="https://x.invalid/b",
            attendee_id="",
            requirements=(_requirement("2"),),
            errors=("t",),
        ),
    ]

    with pytest.raises(AssertionError, match="blank attendee_id"):
        legacy.write_outputs(
            tmp_path, results, generate_html=True, run_identity=legacy.RunIdentity()
        )

    # Nothing partially written: the assertion fires before any file is created.
    assert not (tmp_path / "report.html").exists()


def test_two_blank_identity_scout_dicts_fail_loudly_via_legacy_write_email_reports(
    tmp_path: Path,
) -> None:
    """Reproduces the actual live gap this round closes: ui/server.py's
    `POST /api/runs/{run_id}/generate-emails` calls `scout_schedule_cli.write_email_reports`
    directly with `scouts` loaded straight off disk from a prior run's scouts.json (which may
    have been written by pre-fix code, or hand-edited) -- it never goes through
    ReportingService.publish, so that guard never runs on this path. `write_email_reports` ->
    `build_missing_requirements` operates on the nested dict shape (not ScoutResult objects),
    so it needed its own guard (`_assert_blank_identity_scouts_have_no_records`) rather than
    reusing `ReportingService.publish`'s. This test drives the REAL `write_email_reports`
    directly (the same call ui/server.py makes) with two same-named blank-attendee_id scout
    dicts that each carry a real requirement record, and proves it now fails loudly instead of
    silently merging them under `_attendee_key_for`'s `f"name:{scout_name}"` fallback.
    """
    import scout_schedule_cli as legacy

    def _scout(requirement_number: str) -> dict[str, Any]:
        return {
            "name": "Same Name",
            "attendee_id": "",
            "classes": [],
            "requirements": [
                {
                    "scout_name": "Same Name",
                    "attendee_id": "",
                    "class_number": "26MB1",
                    "class_p4_id": "2000001",
                    "merit_badge_name": "Chess",
                    "requirement_id": f"r-{requirement_number}",
                    "requirement_type_id": "1",
                    "requirement_number": requirement_number,
                    "description": f"Requirement {requirement_number} description.",
                    "completed_requirement": False,
                    "completed_class": False,
                    "requirement_on_event": True,
                    "present_days": "MoTuWeTh",
                }
            ],
            "errors": ["t"],
        }

    scouts = [_scout("1"), _scout("2")]

    with pytest.raises(AssertionError, match="blank attendee_id"):
        legacy.write_email_reports(tmp_path, scouts)

    # No email content written: the guard fires inside build_missing_requirements, before any
    # per-scout .txt/.html or the combined missing_requirements.csv is produced. (write_email_
    # reports does create the empty `emails/` directory itself before calling
    # build_missing_requirements -- that bare mkdir carries no scout data, so it is not the
    # silent-merge risk this test guards against.)
    assert not (tmp_path / "emails" / "missing_requirements.csv").exists()
    assert list((tmp_path / "emails").glob("*.txt")) == []
    assert list((tmp_path / "emails").glob("*.html")) == []
