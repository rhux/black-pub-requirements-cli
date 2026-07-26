"""Recursive requirement status inference.

The status strings and reason sentences below are a SHIPPED SURFACE -- they render in the HTML
report. Changing their wording is a user-visible change, not a refactor.
"""

from __future__ import annotations

from dataclasses import dataclass

from scoutmb.core.inference.numbering import choice_requirement_count
from scoutmb.core.inference.tree import GroupTree

_SATISFIED = frozenset({"complete", "complete_check"})


@dataclass(frozen=True, slots=True)
class RowStatus:
    status: str
    reason: str
    completed_subrequirements: int | None = None
    total_subrequirements: int | None = None
    choice_required_count: int | None = None


def calculate_statuses(
    *,
    tree: GroupTree,
    completed: tuple[bool, ...],
    descriptions: tuple[str, ...],
) -> tuple[RowStatus, ...]:
    """Resolve every row's status, recursing into children.

    Rollup counts are None for rows WITHOUT children. The caller must omit the corresponding
    keys entirely rather than writing None: build_missing_requirements gates actionability on
    `"total_subrequirements" not in item`.
    """
    cache: dict[int, RowStatus] = {}

    def calculate(index: int) -> RowStatus:
        cached = cache.get(index)
        if cached is not None:
            return cached

        direct_children = tree.children[index]
        if completed[index]:
            result = RowStatus("complete", "Marked complete by ScoutingEvent.")
        elif direct_children:
            child_results = [calculate(child) for child in direct_children]
            satisfied_count = sum(1 for child in child_results if child.status in _SATISFIED)
            total_count = len(direct_children)
            choice_count = choice_requirement_count(descriptions[index])

            if total_count and satisfied_count == total_count:
                if any(child.status == "complete_check" for child in child_results):
                    status, reason = (
                        "complete_check",
                        f"All {total_count} subrequirements appear satisfied, but at least one was inferred from a choice requirement.",
                    )
                else:
                    status, reason = (
                        "complete",
                        f"All {total_count} subrequirements are complete.",
                    )
            elif choice_count is not None and satisfied_count >= choice_count:
                status, reason = (
                    "complete_check",
                    f"{satisfied_count} of {total_count} subrequirements appear complete; this meets the stated choice of {choice_count}, but should be verified.",
                )
            else:
                status, reason = (
                    "incomplete",
                    f"{satisfied_count} of {total_count} subrequirements are complete.",
                )

            result = RowStatus(
                status=status,
                reason=reason,
                completed_subrequirements=satisfied_count,
                total_subrequirements=total_count,
                choice_required_count=choice_count,
            )
        else:
            result = RowStatus("incomplete", "Not marked complete by ScoutingEvent.")

        cache[index] = result
        return result

    return tuple(calculate(index) for index in range(len(tree.paths)))
