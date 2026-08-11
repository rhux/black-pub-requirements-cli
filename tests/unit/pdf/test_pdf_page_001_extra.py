"""PDF-PAGE-001's dedicated matrix-marker test.

tests/vertical/test_legacy_flows.py's ``test_flow_success_001_five_stage_end_to_end`` already
exercises this exact behavior (a two-page PDF's attendees coming back in ascending page order)
as part of its stage 2 assertions, but that test already carries a DIFFERENT matrix_case marker
(``FLOW-SUCCESS-001``). pytest_plugins/matrix_gate.py's ``_item_key`` reads only ONE
``matrix_case`` marker per test item via ``item.get_closest_marker``, so a second, stacked
``matrix_case(case_id="PDF-PAGE-001", ...)`` marker on that same function would silently never be
seen by the gate. This is therefore an independent, real test of the same real production
function (``scoutmb.adapters.pdf.pages.extract_pdf``) that carries PDF-PAGE-001's own marker.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.factories.pdf_builder import build_pdf
from tests.matrix.cases.pdf_cases import NAME_A, NAME_B, URL_A, URL_B, PdfPageSpec

from scoutmb.adapters.pdf.pages import extract_pdf


@pytest.mark.matrix_case(case_id="PDF-PAGE-001", context_id="extract", lane="default")
def test_pdf_page_001_multipage_attendees_in_ascending_page_order(tmp_path: Path) -> None:
    pdf_path = build_pdf(
        tmp_path / "PDF-PAGE-001.pdf",
        (
            PdfPageSpec(NAME_A, "Youth", URL_A, "embedded"),
            PdfPageSpec(NAME_B, "Youth", URL_B, "embedded"),
        ),
    )

    attendees, errors = extract_pdf(
        pdf_path, dpis=(144, 200, 300, 400), normalize_case=True, debug_dir=None
    )

    assert errors == []
    assert [a.attendee_name for a in attendees] == [NAME_A, NAME_B]
    assert [a.pdf_page for a in attendees] == [1, 2]
    assert [a.qr_data for a in attendees] == [URL_A, URL_B]
    assert [a.source_pdf for a in attendees] == ["PDF-PAGE-001.pdf", "PDF-PAGE-001.pdf"]
