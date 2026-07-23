"""Domain case rows. Populated by later slices (Tasks 17-21); empty in Task 16.

``ALL_CASES`` is the single registration point the lane gate reads to compute required
execution keys. It stays empty until a domain slice appends its cases.
"""

from __future__ import annotations

from tests.matrix.model import CaseMetadata

ALL_CASES: tuple[CaseMetadata, ...] = ()
