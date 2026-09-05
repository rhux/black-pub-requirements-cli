"""PDF page extraction and QR decoding.

The heavy wheels are imported INSIDE _import_pdf_stack, never at module scope: features/ingest
chooses between this adapter and the tabular one, so a module-scope import here would make a
core-only import impossible.

One implementation, two entry points: ``decode_embedded_qr_from_page(document, page, detector)``
holds the candidate-filter/sort/decode logic and operates on objects a caller already opened --
it is re-exported back into ``pdf_to_scouts.py`` AS ``decode_embedded_qr`` so the frozen
characterization suite (``test_phase_a_gap_closure.py``, ``test_pdf_matrix.py``) keeps calling
the exact same logic through the exact same name. ``decode_embedded_qr(pdf_path)`` defined below
is the guarded public entry point that takes only a path -- it opens the document itself and
delegates to ``decode_embedded_qr_from_page`` per page. It is the shape a future adapter
consumer (features/ingest) will actually call.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from scoutmb.config import ReleaseLimits
from scoutmb.core.models import SCOUTINGEVENT_PREFIX
from scoutmb.errors import CapabilityUnavailable, ScoutmbError

_PDF_DISTRIBUTIONS = ("PyMuPDF", "opencv-python-headless", "numpy")


def _import_pdf_stack() -> tuple[Any, Any, Any]:
    """Return (cv2, fitz, numpy) or raise CapabilityUnavailable.

    A bare ImportError escaping here hands the user a traceback naming a wheel they have never
    heard of, instead of the one command that fixes it.
    """
    try:
        import cv2
        import fitz
        import numpy
    except ImportError as exc:  # noqa: TRY003 - the message IS the feature
        raise CapabilityUnavailable(
            capability="pdf", distributions=_PDF_DISTRIBUTIONS, extra="pdf"
        ) from exc
    return cv2, fitz, numpy


def add_quiet_zone(image: Any, border: int | None = None) -> Any:
    cv2, _, _ = _import_pdf_stack()
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    border_size = border if border is not None else max(12, min(image.shape[:2]) // 8)
    return cv2.copyMakeBorder(
        image,
        border_size,
        border_size,
        border_size,
        border_size,
        cv2.BORDER_CONSTANT,
        value=255,
    )


def decode_variants(image: Any, detector: Any) -> list[str]:
    cv2, _, np = _import_pdf_stack()
    if image is None or image.size == 0:
        return []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    gray = np.ascontiguousarray(gray)
    variants: list[Any] = [gray]

    try:
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(otsu)
    except cv2.error:
        pass

    decoded: list[str] = []
    seen: set[str] = set()

    for variant in variants:
        with_border = add_quiet_zone(variant)
        for scale in (1, 2, 4, 6):
            candidate = (
                with_border
                if scale == 1
                else cv2.resize(
                    with_border,
                    None,
                    fx=scale,
                    fy=scale,
                    interpolation=cv2.INTER_NEAREST,
                )
            )

            try:
                value, _, _ = detector.detectAndDecode(candidate)
                if value and value not in seen:
                    decoded.append(value)
                    seen.add(value)
            except cv2.error:
                pass

            # Detect multiple symbols where supported. This also helps on rendered full pages.
            try:
                ok, values, _, _ = detector.detectAndDecodeMulti(candidate)
                if ok:
                    for value in values:
                        if value and value not in seen:
                            decoded.append(value)
                            seen.add(value)
            except (cv2.error, ValueError):
                pass

            if decoded:
                return decoded

    return decoded


def choose_qr_value(values: Iterable[str]) -> str:
    """Pure string selection -- no cv2/fitz/numpy needed, so no capability guard here."""
    candidates = [value.strip() for value in values if value and value.strip()]
    if not candidates:
        return ""
    for value in candidates:
        if value.startswith(SCOUTINGEVENT_PREFIX):
            return value
    return candidates[0]


def page_regions(image: Any) -> list[tuple[str, Any]]:
    """Pure slicing of an already-decoded array -- no cv2/fitz/numpy call, so no guard here."""
    height, width = image.shape[:2]
    regions: list[tuple[str, Any]] = [("full-page", image)]

    # Schedules typically place the QR in the upper-right, but include every quadrant.
    regions.extend(
        [
            ("upper-right", image[0 : int(height * 0.45), int(width * 0.55) : width]),
            ("upper-left", image[0 : int(height * 0.45), 0 : int(width * 0.45)]),
            ("lower-right", image[int(height * 0.50) : height, int(width * 0.50) : width]),
            ("lower-left", image[int(height * 0.50) : height, 0 : int(width * 0.50)]),
        ]
    )
    return regions


def render_page(page: Any, dpi: int) -> Any:
    cv2, _, np = _import_pdf_stack()
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    limits = ReleaseLimits()
    if pixmap.width > limits.max_pdf_dimension_px or pixmap.height > limits.max_pdf_dimension_px:
        raise ScoutmbError(
            f"rendered page dimension {pixmap.width}x{pixmap.height} exceeds the "
            f"{limits.max_pdf_dimension_px}px limit"
        )
    image = np.frombuffer(pixmap.samples, dtype=np.uint8)
    image = image.reshape(pixmap.height, pixmap.width, pixmap.n)
    if pixmap.n == 4:
        return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
    if pixmap.n == 3:
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image


def decode_rendered_qr(
    page: Any,
    detector: Any,
    dpis: Sequence[int],
) -> tuple[str, str, Any | None]:
    last_render: Any | None = None
    for dpi in dpis:
        image = render_page(page, dpi)
        last_render = image
        for region_name, region in page_regions(image):
            values = decode_variants(region, detector)
            selected = choose_qr_value(values)
            if selected:
                return selected, f"rendered:{dpi}dpi:{region_name}", image
    return "", "", last_render


def decode_embedded_qr_from_page(
    document: Any,
    page: Any,
    detector: Any,
) -> tuple[str, str]:
    """Decode the first QR value found among one page's embedded images.

    This is the legacy ``pdf_to_scouts.decode_embedded_qr(document, page, detector)`` body,
    unchanged, moved here and re-exported back into ``pdf_to_scouts.py`` under its original name
    -- the frozen characterization suite (``test_phase_a_gap_closure.py``, ``test_pdf_matrix.py``)
    keeps calling the exact same logic through the exact same name. It operates on an
    already-opened ``fitz.Document``/``fitz.Page`` and a caller-supplied
    ``cv2.QRCodeDetector``; callers who only have a path should use ``decode_embedded_qr(pdf_path)``
    below, which opens the document itself and delegates here per page.
    """
    cv2, _, np = _import_pdf_stack()
    candidates: list[tuple[int, int, int]] = []
    seen_xrefs: set[int] = set()

    for image_info in page.get_images(full=True):
        xref = int(image_info[0])
        width = int(image_info[2])
        height = int(image_info[3])
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)

        # QR codes are normally square. Allow some tolerance for unusual encoders.
        if min(width, height) < 70 or max(width, height) > 2500:
            continue
        if abs(width - height) > max(12, int(max(width, height) * 0.12)):
            continue
        candidates.append((xref, width, height))

    # Smaller, square monochrome images are usually the QR rather than page artwork.
    candidates.sort(key=lambda item: (abs(item[1] - item[2]), item[1] * item[2]))

    for xref, _, _ in candidates:
        try:
            extracted = document.extract_image(xref)
            raw = np.frombuffer(extracted["image"], dtype=np.uint8)
            image = cv2.imdecode(raw, cv2.IMREAD_UNCHANGED)
        except (KeyError, ValueError, cv2.error):
            continue

        values = decode_variants(image, detector)
        selected = choose_qr_value(values)
        if selected:
            return selected, f"embedded-image:xref-{xref}"

    return "", ""


def decode_embedded_qr(pdf_path: Any) -> str:
    """Decode the first QR value found among a PDF's embedded page images.

    The public capability-gated entry point: callers pass only a path, never an already-opened
    fitz.Document/Page or cv2.QRCodeDetector. ``_import_pdf_stack()`` runs before anything else
    touches the file, so a missing wheel surfaces as CapabilityUnavailable, not a bare
    ImportError deep inside PyMuPDF or OpenCV. Opens the document itself and delegates the
    per-page candidate-filter/sort/decode logic to ``decode_embedded_qr_from_page``.
    """
    cv2, fitz, _np = _import_pdf_stack()
    detector = cv2.QRCodeDetector()
    with fitz.open(pdf_path) as document:
        for page in document:
            value, _method = decode_embedded_qr_from_page(document, page, detector)
            if value:
                return value

    return ""
