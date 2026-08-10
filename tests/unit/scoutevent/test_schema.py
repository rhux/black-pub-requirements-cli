"""ACQ-REQ-004: a requirement row missing an identity field fails closed instead of being
silently coerced to blanks. Every other field keeps today's coercion, INCLUDING HTML cleaning of
the description via clean_html_description -- dropping that would regress every ACQ-REQ-* case
that carries HTML in REQ_DESCR."""

from __future__ import annotations

import pytest

from scoutmb.adapters.scoutevent.schema import (
    ScoutingEventSchemaDrift,
    validate_requirement_row,
)


def test_missing_identity_fields_raises_schema_drift() -> None:
    with pytest.raises(ScoutingEventSchemaDrift) as exc_info:
        validate_requirement_row({"MERIT_BADGE_NAME": "Chess"})

    err = exc_info.value
    assert err.profile == "requirement_row"
    assert set(err.missing_fields) == {"requirement_id", "requirement_number"}
    assert len(err.sample) <= 300


def test_well_formed_row_validates() -> None:
    row = {
        "MERIT_BADGE_NAME": "Chess",
        "MDM_LKP_BADGE_REQ_ID": "77",
        "MDM_LKP_BADGE_REQ_TYPE_ID": "2",
        "REQ_NBR_WEB_DISPLAY": "#1",
        "REQ_DESCR": "Do the thing<br>Line two",
        "COMPLETED_REQ_FLAG": "1",
    }
    validated = validate_requirement_row(row)
    assert validated["requirement_id"] == "77"
    assert validated["requirement_number"] == "#1"
    assert validated["description"] == "Do the thing\nLine two"


def test_req_nbr_fallback_satisfies_the_requirement_number_field() -> None:
    """Legacy prefers REQ_NBR_WEB_DISPLAY but falls back to REQ_NBR -- that fallback is NOT
    drift, it's a known dual representation, so either one present must validate."""
    row = {"MDM_LKP_BADGE_REQ_ID": "77", "REQ_NBR": "#2"}
    validated = validate_requirement_row(row)
    assert validated["requirement_number"] == "#2"


def test_sample_redacts_known_sensitive_key_names() -> None:
    with pytest.raises(ScoutingEventSchemaDrift) as exc_info:
        validate_requirement_row({"SESSION_COOKIE": "s3cr3t-value-should-not-leak"})
    assert "s3cr3t-value-should-not-leak" not in exc_info.value.sample
    assert "REDACTED" in exc_info.value.sample


def test_sample_stays_bounded_even_when_huge() -> None:
    huge_description = "x" * 5000
    with pytest.raises(ScoutingEventSchemaDrift) as exc_info:
        validate_requirement_row({"REQ_DESCR": huge_description})
    assert len(exc_info.value.sample) <= 300
