from __future__ import annotations

from dataclasses import dataclass

from tests.matrix.model import Domain


@dataclass(frozen=True, slots=True)
class AxisSpec:
    axis_id: str
    domain: Domain
    members: frozenset[str]
    min_focused_cases: int
    interactions: frozenset[str]
    boundaries: frozenset[str]


# Domain axes are declared by later slices (Tasks 17-21). Task 16 ships the type only.
AXES: tuple[AxisSpec, ...] = ()
