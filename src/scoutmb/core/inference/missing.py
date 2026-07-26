"""Actionable-leaf selection and the ancestor walk that gives a leaf its context.

The legacy implementation kept bookkeeping in a dict keyed on id(item), which cannot survive
frozen records. This is the index-based re-expression.

CRITICAL: the ancestor lookup is BY NUMBER through a last-wins map, not through the tree's
positional parent link. When one group holds two rows with the same requirement_number those
two disagree, and REQ-DUP-002 pins which one the legacy code picks. Substituting
tree.parent_index here is the obvious refactor and it is WRONG.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


def is_not_used(description: str) -> bool:
    return "(not used)" in description.lower()


def select_actionable(
    rows: Sequence[Mapping[str, Any]],
    *,
    attendee_key_of: Any,
    cleaned_description_of: Any,
) -> dict[int, bool]:
    """Return {row index: is_leaf} for every row an email should mention.

    A row is selected when it is an actionable leaf, or when it is a still-incomplete ancestor
    of one (so "3b" is never shown without whatever "3" asked for).
    """
    by_key: dict[tuple[str, str, str], int] = {}
    for index, row in enumerate(rows):
        key = (
            attendee_key_of(row),
            str(row.get("class_p4_id") or ""),
            str(row.get("requirement_number") or ""),
        )
        by_key[key] = index  # last wins, exactly as the legacy dict comprehension did

    def actionable_leaf(row: Mapping[str, Any]) -> bool:
        return (
            row.get("calculated_status") == "incomplete"
            and "total_subrequirements" not in row
            and str(row.get("requirement_type_id") or "") != "3"
            and not is_not_used(cleaned_description_of(str(row.get("description") or "")))
        )

    selected: dict[int, bool] = {}
    for index, row in enumerate(rows):
        if not actionable_leaf(row):
            continue
        current: int | None = index
        is_leaf = True
        while current is not None and current not in selected:
            selected[current] = is_leaf
            is_leaf = False
            parent_number = rows[current].get("parent_requirement_number")
            if parent_number is None:
                break
            parent_key = (
                attendee_key_of(rows[current]),
                str(rows[current].get("class_p4_id") or ""),
                str(parent_number),
            )
            parent_index = by_key.get(parent_key)
            if parent_index is None:
                break
            if rows[parent_index].get("calculated_status") in {"complete", "complete_check"}:
                break
            current = parent_index

    return selected


def group_missing_requirements(
    rows: Sequence[Mapping[str, Any]],
    *,
    attendee_key_of: Callable[[Mapping[str, Any]], str],
    clean_description: Callable[[str], str],
) -> dict[str, dict[str, Any]]:
    """Select actionable rows and group them by attendee, then by merit badge.

    The public façade: it owns both halves of the legacy behavior (selection AND grouping) so
    the legacy function reduces to `annotate -> delegate` and the parity runner has a single
    package entry point to drive.
    """
    selected = select_actionable(
        rows, attendee_key_of=attendee_key_of, cleaned_description_of=clean_description
    )

    grouped: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(rows):
        if index not in selected:
            continue
        description = clean_description(str(item.get("description") or ""))
        if is_not_used(description):
            continue

        entry = {
            "requirement_number": str(item.get("requirement_number") or ""),
            "description": description,
            "is_prereq": "(pre-req)" in description.lower(),
            "is_leaf": selected[index],
            "depth": max(len(item.get("requirement_path") or []) - 1, 0),
        }
        bucket = grouped.setdefault(
            attendee_key_of(item),
            {"display_name": str(item.get("scout_name") or ""), "badges": {}},
        )
        bucket["badges"].setdefault(str(item.get("merit_badge_name") or ""), []).append(entry)

    return grouped
