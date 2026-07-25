"""Requirement-number parsing. Pure: no I/O, no imports outside the standard library.

ScoutingEvent emits 26 distinct display-number shapes, including malformed ones like "#(c)"
that omit the top-level number. The current_top_level thread is how those still group.
"""

from __future__ import annotations

import re

CHOICE_COUNT_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def requirement_path(
    number: str, current_top_level: str | None
) -> tuple[tuple[str, ...], str | None]:
    """Return a comparable requirement path and the current top-level number.

    ScoutingEvent occasionally emits malformed display numbers such as ``#(c)``
    where the leading top-level number is omitted. In that case, retain the most
    recently observed numeric top-level requirement so nested rows still group
    correctly in the HTML report.
    """
    text = str(number or "").strip()
    tokens = [token.lower() for token in re.findall(r"[A-Za-z]+|\d+", text)]
    if not tokens:
        return (), current_top_level

    if tokens[0].isdigit():
        current_top_level = tokens[0]
        return tuple(tokens), current_top_level

    if current_top_level:
        return (current_top_level, *tokens), current_top_level

    return tuple(tokens), current_top_level


def choice_requirement_count(description: str) -> int | None:
    """Extract X from wording such as 'Do TWO of the following'."""
    text = re.sub(r"\s+", " ", str(description or "")).strip().lower()
    words = "|".join(CHOICE_COUNT_WORDS)
    match = re.search(
        rf"\b(?:do|complete|choose|select|perform)\s+(?:any\s+)?(?P<count>\d+|{words})\s+of\s+the\s+following\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    value = match.group("count").lower()
    return int(value) if value.isdigit() else CHOICE_COUNT_WORDS.get(value)
