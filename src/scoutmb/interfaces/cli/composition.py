"""The ONLY module under interfaces/cli permitted to import an adapter.

Named by convention so the architecture test can enforce it: "a module whose sole job is
wiring" is not a property a linter can evaluate, so the filename carries the rule
(tests/architecture's test_adapter_imports_confined_to_composition_roots).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from scoutmb.adapters.files.tabular import TabularAttendeeSource
from scoutmb.adapters.pdf.pages import extract_pdf as _extract_pdf
from scoutmb.core.models import ExtractedAttendee, ExtractionError
from scoutmb.features.ingest.service import IngestService


def build_ingest_service(
    *, sheet_name: str = "Scouts Only", include_adults: bool = False
) -> IngestService:
    return IngestService(
        sources=(TabularAttendeeSource(sheet_name=sheet_name),), include_adults=include_adults
    )


class PdfExtractor(Protocol):
    """The callable shape interfaces/cli/pdf.py needs from the PDF extraction adapter.

    A plain ``Callable[[...], ...]`` type erases parameter names, so mypy rejects main()'s
    keyword call (``extract_pdf(pdf_path=..., dpis=..., ...)``) against it -- this Protocol's
    ``__call__`` keeps the names so the keyword call type-checks against the real
    ``adapters.pdf.pages.extract_pdf`` it is structurally satisfied by.
    """

    def __call__(
        self,
        pdf_path: Path,
        dpis: Sequence[int],
        normalize_case: bool,
        debug_dir: Path | None,
    ) -> tuple[list[ExtractedAttendee], list[ExtractionError]]: ...


def build_pdf_extractor() -> PdfExtractor:
    """Return the PDF page-extraction function, wired to the real fitz/cv2 adapter.

    interfaces/cli/pdf.py obtains its extractor through here rather than importing
    scoutmb.adapters.pdf.pages directly, keeping every adapter import in this file.
    """
    return _extract_pdf
