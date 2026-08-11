from __future__ import annotations

from scoutmb.features.acquisition.service import _days_from_class_name


def test_days_from_class_name_without_separator_is_empty() -> None:
    """Migrated from tests/characterization/test_phase_a_gap_closure.py (retired in Slice 2b
    B10.4)."""
    assert _days_from_class_name("Chess") == ""
