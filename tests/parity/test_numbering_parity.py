from __future__ import annotations

import pytest
import scout_schedule_cli as legacy
from hypothesis import given
from hypothesis import strategies as st
from tests.factories.payloads import REQUIREMENT_NUMBER_SHAPES

from scoutmb.core.inference.numbering import choice_requirement_count, requirement_path


def test_legacy_names_are_the_package_objects() -> None:
    assert legacy.requirement_path is requirement_path
    assert legacy.choice_requirement_count is choice_requirement_count


@pytest.mark.parametrize("shape", REQUIREMENT_NUMBER_SHAPES)
@pytest.mark.parametrize("top", [None, "7"])
def test_all_observed_shapes_parse_identically(shape: str, top: str | None) -> None:
    assert requirement_path(shape, top) == legacy.requirement_path(shape, top)


@pytest.mark.parametrize(
    "description",
    [
        "Do TWO of the following.",
        "Complete any 3 of the following requirements",
        "Choose ONE of the following",
        "Select twelve of the following",
        "No choice wording here at all",
        "",
    ],
)
def test_choice_counts_match_legacy(description: str) -> None:
    assert choice_requirement_count(description) == legacy.choice_requirement_count(description)


@given(st.text(max_size=60))
def test_requirement_path_never_raises(value: str) -> None:
    path, _ = requirement_path(value, None)
    assert isinstance(path, tuple)
