from __future__ import annotations

from dataclasses import dataclass

from tests.matrix.model import SurfaceClass


@dataclass(frozen=True, slots=True)
class SurfacePolicy:
    surface_id: str
    surface_class: SurfaceClass
    allowed_fields: frozenset[str]
    forbidden_sentinels: frozenset[str]


# Populated by later slices; Task 16 ships the type only.
POLICIES: tuple[SurfacePolicy, ...] = ()
