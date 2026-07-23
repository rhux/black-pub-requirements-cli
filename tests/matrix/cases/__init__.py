"""Domain case rows. Populated by later slices (Tasks 17-21); empty in Task 16.

``ALL_CASES`` is the single registration point the lane gate reads to compute required
execution keys. It stays empty until a domain slice appends its cases.
"""

from __future__ import annotations

from tests.matrix.model import CaseMetadata

# Stays empty until Task 22's Gate promotes the domain catalogs into the lane-accounting
# registry. Wiring it earlier would make ``--matrix-lane default`` demand every domain key,
# which the kernel's own empty-registry self-tests (Task 16) rely on not happening yet.
# The Task 17 input catalog validates itself in tests/characterization/test_input_matrix.py.
ALL_CASES: tuple[CaseMetadata, ...] = ()
