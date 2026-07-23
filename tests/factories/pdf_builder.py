"""Deterministic synthetic-PDF builder for the PDF extraction matrix (Task 18).

Every page is generated in-process from a :class:`PdfPageSpec`; the builder never reads a
source PDF and writes only at the supplied ``path`` (tests pass a location below pytest's
``tmp_path``). QR codes are produced two ways so the matrix can exercise both decode tiers of
``pdf_to_scouts``: ``embedded`` inserts a rasterized PNG image, ``vector`` paints the QR
modules as individual filled rectangles (no embedded image, forcing the render fallback), and
``none`` omits the QR entirely.

Only the runner/builder layer imports the optional PDF stack (``fitz``/``cv2``/``numpy``); the
frozen case data in ``tests/matrix/cases/pdf_cases.py`` stays import-clean.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np

from tests.matrix.cases.pdf_cases import PdfPageSpec


def _encode_qr(value: str) -> np.ndarray:
    """Return the QR matrix (uint8, 0=dark/255=light) for ``value``."""
    return cv2.QRCodeEncoder_create().encode(value)  # type: ignore[attr-defined]


# A non-empty, non-label filler line ends the identity block so the last *present* label does
# not grab an unrelated following line. ``extract_page_identity`` returns the first non-empty
# line after each label, so an absent field must be genuinely absent (its label omitted) rather
# than left blank — a blank value would otherwise let the next label line be read as the value.
_IDENTITY_FILLER = "Schedule of Classes"


def _identity_text(spec: PdfPageSpec) -> str:
    lines: list[str] = []
    if spec.name:
        lines += ["Attendee Information", spec.name]
    if spec.registrant_type:
        lines += ["Registrant", spec.registrant_type]
    lines.append(_IDENTITY_FILLER)
    return "\n".join(lines)


def build_pdf(path: Path, pages: tuple[PdfPageSpec, ...]) -> Path:
    """Write a multi-page PDF for ``pages`` at ``path`` and return ``path``."""
    document = fitz.open()
    try:
        for spec in pages:
            page = document.new_page(width=612, height=792)
            page.insert_textbox(
                fitz.Rect(54, 54, 360, 260),
                _identity_text(spec),
                fontsize=12,
            )
            if spec.qr_mode == "none":
                continue
            matrix = _encode_qr(spec.qr_value)
            if spec.qr_mode == "embedded":
                # Upscale to a comfortable pixel size so the embedded raster decodes cleanly.
                scale = max(1, 300 // matrix.shape[0])
                enlarged = cv2.resize(
                    matrix,
                    None,
                    fx=scale,
                    fy=scale,
                    interpolation=cv2.INTER_NEAREST,
                )
                ok, encoded = cv2.imencode(".png", enlarged)
                if not ok:
                    raise RuntimeError("synthetic QR encoding failed")
                page.insert_image(
                    fitz.Rect(400, 54, 560, 214), stream=encoded.tobytes()
                )
            else:  # "vector": paint modules directly so no image xref exists on the page.
                side = 150.0
                module = side / matrix.shape[0]
                for row, column in zip(*np.where(matrix == 0), strict=True):
                    x0 = 400 + column * module
                    y0 = 54 + row * module
                    page.draw_rect(
                        fitz.Rect(x0, y0, x0 + module, y0 + module),
                        color=(0, 0, 0),
                        fill=(0, 0, 0),
                        width=0,
                    )
        document.save(path)
    finally:
        document.close()
    return path


def build_multi_qr_image(values: tuple[str, ...]) -> np.ndarray:
    """Return one grayscale image with the QR symbols for ``values`` tiled left-to-right.

    Used to exercise ``decode_variants``' multi-symbol detection and value deduplication
    without an intervening PDF: the runner feeds this straight to the real decoder.
    """
    tiles: list[np.ndarray] = []
    for value in values:
        matrix = _encode_qr(value)
        # Upscale to a comfortable pixel size (as in build_pdf's embedded path) so cv2's
        # QRCodeDetector can resolve each symbol's finder patterns cleanly.
        scale = max(1, 200 // matrix.shape[0])
        tiles.append(
            cv2.resize(matrix, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        )
    height = max(tile.shape[0] for tile in tiles)
    # A wide light-colored gap between tiles keeps the two QR symbols visually separated so the
    # detector reports them as distinct candidates instead of merging their finder patterns.
    gap = np.full((height, 48), 255, dtype=np.uint8)
    padded: list[np.ndarray] = []
    for index, tile in enumerate(tiles):
        canvas = np.full((height, tile.shape[1]), 255, dtype=np.uint8)
        canvas[: tile.shape[0], :] = tile
        if index:
            padded.append(gap)
        padded.append(canvas)
    stitched = np.hstack(padded)
    return cv2.copyMakeBorder(
        stitched, 48, 48, 48, 48, cv2.BORDER_CONSTANT, value=255
    )


def build_corrupt_pdf(path: Path) -> Path:
    """Write bytes that are not a parseable PDF, to exercise the bounded open-error path."""
    path.write_bytes(b"%PDF-1.7\nnot actually a valid pdf body\n%%EOF\n")
    return path
