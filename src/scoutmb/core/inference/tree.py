"""Parent/child reconstruction for one (scout, class) requirement group.

Index-based by construction: every link is a position in the input sequence, never an object
identity. That is what lets build_missing_requirements stop keying on id().
"""

from __future__ import annotations

from dataclasses import dataclass

from scoutmb.core.inference.numbering import requirement_path


@dataclass(frozen=True, slots=True)
class GroupTree:
    paths: tuple[tuple[str, ...], ...]
    parent_index: tuple[int | None, ...]
    children: tuple[tuple[int, ...], ...]


def build_group_tree(numbers: tuple[str, ...], type_ids: tuple[str, ...]) -> GroupTree:
    """Derive paths and parent/child links for one group, in row order.

    Two linking strategies, in the legacy order:
      1. longest registered path prefix (the ordinary case);
      2. nearest prior TYPE-3 header with a shallower path (the malformed-numbering fallback).
    """
    current_top_level: str | None = None
    paths: list[tuple[str, ...]] = []
    for number in numbers:
        path, current_top_level = requirement_path(number, current_top_level)
        paths.append(path)

    children: list[list[int]] = [[] for _ in numbers]
    parents: list[int | None] = [None] * len(numbers)
    prior_path_indexes: dict[tuple[str, ...], int] = {}
    header_stack: list[tuple[int, int]] = []

    for index, path in enumerate(paths):
        parent_index: int | None = None
        if len(path) > 1:
            for depth in range(len(path) - 1, 0, -1):
                candidate = path[:depth]
                if candidate in prior_path_indexes:
                    parent_index = prior_path_indexes[candidate]
                    break

        if parent_index is None and len(path) > 1:
            for candidate_index, candidate_depth in reversed(header_stack):
                if candidate_depth < len(path):
                    parent_index = candidate_index
                    break

        if parent_index is not None:
            children[parent_index].append(index)
            parents[index] = parent_index

        if path:
            prior_path_indexes[path] = index
        if type_ids[index] == "3":
            while header_stack and header_stack[-1][1] >= len(path):
                header_stack.pop()
            header_stack.append((index, len(path)))

    return GroupTree(
        paths=tuple(paths),
        parent_index=tuple(parents),
        children=tuple(tuple(group) for group in children),
    )
