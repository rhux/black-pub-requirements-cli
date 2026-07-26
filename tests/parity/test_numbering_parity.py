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
    """`legacy.requirement_path is requirement_path` (see test above), so this only proves
    the re-export is still wired up, not that the parsing logic is correct — that's the job
    of `test_requirement_path_hardcoded_expected_values` below and the frozen characterization
    suite."""
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
    """`legacy.choice_requirement_count is choice_requirement_count` (see test above), so
    this only proves the re-export is still wired up, not that the count-extraction logic
    is correct — that's `test_choice_requirement_count_hardcoded_expected_values` below."""
    assert choice_requirement_count(description) == legacy.choice_requirement_count(description)


@pytest.mark.parametrize(
    ("number", "top", "expected"),
    [
        # Plain top-level + child letter: leading digit token becomes the new top-level.
        ("3b", None, (("3", "b"), "3")),
        # A numeric top-level in the number always overrides an incoming current_top_level.
        ("3b", "7", (("3", "b"), "3")),
        # Malformed "(c)" with no leading digit: parens are stripped by the tokenizer, and
        # the passed-in top-level is prepended so the row still nests under "7".
        ("(c)", "7", (("7", "c"), "7")),
        # The "#(c)" variant from real ScoutingEvent data behaves identically to "(c)".
        ("#(c)", "7", (("7", "c"), "7")),
        # Same malformed shape with no prior top-level to fall back on: no digit to prepend.
        ("#(c)", None, (("c",), None)),
        # Bare top-level number: becomes the new current_top_level.
        ("12", None, (("12",), "12")),
        # Blank input short-circuits before any top-level tracking happens.
        ("", "7", ((), "7")),
    ],
)
def test_requirement_path_hardcoded_expected_values(
    number: str, top: str | None, expected: tuple[tuple[str, ...], str | None]
) -> None:
    """Independent regression coverage: hardcoded expected paths verified by hand-tracing
    `requirement_path` (tokenize into letter/digit runs; a leading digit token sets/overrides
    the top-level; otherwise prepend the current top-level, if any), not derived from or
    compared against the legacy module. Complements, but does not replace, the frozen
    characterization suite for numbering."""
    assert requirement_path(number, top) == expected


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Do TWO of the following.", 2),
        ("Complete any 3 of the following requirements", 3),
        ("Choose ONE of the following", 1),
        ("Select twelve of the following", 12),
        ("No choice wording here at all", None),
        ("", None),
    ],
)
def test_choice_requirement_count_hardcoded_expected_values(
    description: str, expected: int | None
) -> None:
    """Independent regression coverage: hardcoded expected counts verified by hand-tracing
    `choice_requirement_count`'s regex (word or digit count between "do/complete/choose/
    select/perform [any] " and "of the following"), not derived from or compared against the
    legacy module."""
    assert choice_requirement_count(description) == expected


@given(st.text(max_size=60))
def test_requirement_path_never_raises(value: str) -> None:
    path, _ = requirement_path(value, None)
    assert isinstance(path, tuple)
