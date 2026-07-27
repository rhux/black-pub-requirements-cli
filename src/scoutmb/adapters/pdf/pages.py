"""PDF page-text identity extraction, plus the per-PDF extraction loop.

``extract_page_identity``/``normalize_obvious_case``/``value_after_label`` are pure text parsing
against an already-opened ``fitz.Page`` -- no capability guard needed, since nothing here
imports fitz/cv2 itself.

``extract_pdf`` ties one PDF's pages to the decode tiers in ``adapters/pdf/extract.py``
(embedded image first, rendered-page fallback second) plus this module's identity extraction.
It is adapter-layer, not features-layer, because it needs ``cv2.QRCodeDetector()`` and
``fitz.open()`` directly (for the debug-PNG write and to open the document) in addition to the
decode functions -- routing that through a features-layer function would mean features either
importing an adapter directly (which ``tests/architecture`` forbids) or accepting an injected
port for a single caller, which is more machinery than this seam earns. It reuses Task 16's
``_import_pdf_stack()`` guard so a missing PyMuPDF/OpenCV install surfaces as
``CapabilityUnavailable`` here too, not a bare ImportError.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scoutmb.adapters.pdf.extract import (
    _import_pdf_stack,
    decode_embedded_qr_from_page,
    decode_rendered_qr,
    render_page,
)
from scoutmb.core.models import ExtractedAttendee, ExtractionError


def normalized_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def value_after_label(lines: list[str], label: str) -> str:
    wanted = normalized_label(label)
    for index, line in enumerate(lines):
        if normalized_label(line) != wanted:
            continue
        for candidate in lines[index + 1 :]:
            candidate = candidate.strip()
            if candidate:
                return candidate
    return ""


def extract_page_identity(page: Any) -> tuple[str, str]:
    lines = [line.strip() for line in page.get_text("text").splitlines() if line.strip()]
    attendee_name = value_after_label(lines, "Attendee Information")
    registrant_type = value_after_label(lines, "Registrant")
    return attendee_name, registrant_type


def normalize_obvious_case(name: str) -> str:
    """Fix a narrow class of obvious OCR/source typos without title-casing valid names.

    Example: MIles -> Miles. Names such as McDonald, DeMarco, O'Neil, and AJ remain unchanged.
    """

    def normalize_token(match: re.Match[str]) -> str:
        token = match.group(0)
        if len(token) >= 3 and token[0].isupper() and token[1].isupper() and token[2:].islower():
            return token[0] + token[1:].lower()
        return token

    return re.sub(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", normalize_token, name)


def extract_pdf(
    pdf_path: Path,
    dpis: Sequence[int],
    normalize_case: bool,
    debug_dir: Path | None,
) -> tuple[list[ExtractedAttendee], list[ExtractionError]]:
    cv2, fitz, _np = _import_pdf_stack()

    attendees: list[ExtractedAttendee] = []
    errors: list[ExtractionError] = []
    detector = cv2.QRCodeDetector()

    try:
        document = fitz.open(pdf_path)
    except Exception as exc:  # PyMuPDF raises several exception types for malformed PDFs.
        return [], [ExtractionError(pdf_path.name, 0, "", "", f"Could not open PDF: {exc}")]

    with document:
        for page_index, page in enumerate(document, start=1):
            printed_name, registrant_type = extract_page_identity(page)
            attendee_name = normalize_obvious_case(printed_name) if normalize_case else printed_name

            qr_data, decode_method = decode_embedded_qr_from_page(document, page, detector)
            failed_render: Any | None = None
            if not qr_data:
                qr_data, decode_method, failed_render = decode_rendered_qr(page, detector, dpis)

            missing: list[str] = []
            if not printed_name:
                missing.append("attendee name")
            if not registrant_type:
                missing.append("registrant type")
            if not qr_data:
                missing.append("QR code")

            if missing:
                errors.append(
                    ExtractionError(
                        source_pdf=pdf_path.name,
                        pdf_page=page_index,
                        attendee_name=attendee_name,
                        registrant_type=registrant_type,
                        error="Missing " + ", ".join(missing),
                    )
                )
                if debug_dir is not None and not qr_data:
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    if failed_render is None:
                        failed_render = render_page(page, max(dpis))
                    debug_name = f"{pdf_path.stem}-page-{page_index:03d}.png"
                    cv2.imwrite(str(debug_dir / debug_name), failed_render)

            if printed_name or registrant_type or qr_data:
                attendees.append(
                    ExtractedAttendee(
                        attendee_name=attendee_name,
                        name_as_printed=printed_name,
                        registrant_type=registrant_type,
                        qr_data=qr_data,
                        source_pdf=pdf_path.name,
                        pdf_page=page_index,
                        qr_decode_method=decode_method,
                    )
                )

    return attendees, errors
