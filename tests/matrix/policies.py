from __future__ import annotations

from dataclasses import dataclass

from tests.matrix.model import SurfaceClass


@dataclass(frozen=True, slots=True)
class SurfacePolicy:
    surface_id: str
    surface_class: SurfaceClass
    allowed_fields: frozenset[str]
    forbidden_sentinels: frozenset[str]


# Task 19: the raw/ acquisition-audit filename surface. attendee_filename_stem builds
# "<name-slug>-<run-uuid-hex>" specifically so the bearer-token attendee_id never appears in a
# filename that might be shared for troubleshooting; this policy pins that contract so a future
# change cannot silently reintroduce the attendee_id into a filename.
_ACQUISITION_POLICIES: tuple[SurfacePolicy, ...] = (
    SurfacePolicy(
        surface_id="acq-raw-filename",
        surface_class=SurfaceClass.OPERATIONAL_PRIVATE,
        allowed_fields=frozenset({"scout_name_slug", "run_output_uuid", "class_number_slug"}),
        forbidden_sentinels=frozenset({"attendee_id"}),
    ),
)

# Populated by later slices; Task 16 ships the type only, Task 19 adds the raw-filename surface.
POLICIES: tuple[SurfacePolicy, ...] = _ACQUISITION_POLICIES
