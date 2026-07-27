#!/usr/bin/env python3
"""Compatibility shim. The implementation lives in scoutmb.interfaces.cli.pdf and its
supporting modules (scoutmb.adapters.pdf.pages, scoutmb.adapters.pdf.extract,
scoutmb.features.ingest.pdf_extract, scoutmb.core.models).

Kept so existing invocations and the Slice 1b characterization runners keep working; retired
in Slice 2b together with its runners.
"""

from __future__ import annotations

# Re-export EVERY symbol the frozen characterization suite touches. Verified with:
#   rg -n 'pdf_to_scouts\.[a-zA-Z_]+' tests/
# tests/characterization/test_phase_a_gap_closure.py reaches decode_variants, add_quiet_zone
# and the cv2 MODULE OBJECT (pdf_to_scouts.cv2.QRCodeDetector(), monkeypatch.setattr on
# pdf_to_scouts.cv2), so the module binding is part of the surface, not an implementation
# detail -- patching an attribute on this module object patches the SAME object the adapter's
# _import_pdf_stack() returns, since both are the one entry cached in sys.modules.
import cv2  # noqa: F401 - legacy public surface: tests call pdf_to_scouts.cv2.QRCodeDetector()
import numpy as np  # noqa: F401 - same
from scoutmb.adapters.pdf.extract import (  # noqa: F401 - legacy public surface
    SCOUTINGEVENT_PREFIX,
    add_quiet_zone,
    choose_qr_value,
    decode_embedded_qr_from_page as decode_embedded_qr,
    decode_rendered_qr,
    decode_variants,
    page_regions,
    render_page,
)
from scoutmb.adapters.pdf.pages import (  # noqa: F401 - legacy public surface
    extract_page_identity,
    extract_pdf,
    normalize_obvious_case,
    normalized_label,
    value_after_label,
)
from scoutmb.core.models import ExtractedAttendee, ExtractionError  # noqa: F401
from scoutmb.features.ingest.pdf_extract import (  # noqa: F401
    atomic_write_text,
    expand_pdf_inputs,
    write_attendees_csv,
    write_errors_csv,
)
from scoutmb.interfaces.cli.pdf import main, parse_args  # noqa: F401

if __name__ == "__main__":
    raise SystemExit(main())
