"""Domain case rows: the single registration point the lane gate (``tests/plugins/matrix_gate.py``)
reads to compute required execution keys for ``--matrix-lane``.

Wired for real as of Task 22's Gate (Slice 1b Phase A): every domain catalog from Tasks 17-21
plus Task 22's own scale/flow catalogs is concatenated into ``ALL_CASES`` below. Before this,
``ALL_CASES`` stayed intentionally empty so ``--matrix-lane default`` would not demand every
domain key while catalogs were still being built up slice by slice; every domain's own
characterization test module already validated its own catalog directly in the meantime (e.g.
``tests/characterization/test_input_matrix.py``).
"""

from __future__ import annotations

from tests.matrix.cases.acquisition_cases import ALL_ACQUISITION_METADATA
from tests.matrix.cases.artifact_cases import ALL_ARTIFACT_METADATA
from tests.matrix.cases.bootstrap_cases import ALL_BOOTSTRAP_METADATA
from tests.matrix.cases.cli_cases import ALL_CLI_METADATA
from tests.matrix.cases.desktop_cases import ALL_DESKTOP_METADATA
from tests.matrix.cases.input_cases import INPUT_CASES
from tests.matrix.cases.interface_cases import ALL_INTERFACE_METADATA
from tests.matrix.cases.pdf_cases import PDF_CASES
from tests.matrix.cases.platform_cases import ALL_PLATFORM_METADATA
from tests.matrix.cases.requirement_cases import ALL_REQUIREMENT_METADATA
from tests.matrix.cases.scale_cases import ALL_FLOW_METADATA, ALL_SCALE_METADATA
from tests.matrix.model import CaseMetadata

ALL_INPUT_METADATA: tuple[CaseMetadata, ...] = tuple(case.meta for case in INPUT_CASES)
ALL_PDF_METADATA: tuple[CaseMetadata, ...] = tuple(case.meta for case in PDF_CASES)

ALL_CASES: tuple[CaseMetadata, ...] = (
    ALL_INPUT_METADATA
    + ALL_PDF_METADATA
    + ALL_ACQUISITION_METADATA
    + ALL_REQUIREMENT_METADATA
    + ALL_ARTIFACT_METADATA
    + ALL_PLATFORM_METADATA
    + ALL_INTERFACE_METADATA
    + ALL_CLI_METADATA
    + ALL_DESKTOP_METADATA
    + ALL_BOOTSTRAP_METADATA
    + ALL_SCALE_METADATA
    + ALL_FLOW_METADATA
)
