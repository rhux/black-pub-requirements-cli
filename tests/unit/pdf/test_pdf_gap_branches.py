"""Direct unit tests migrated from tests/characterization/test_phase_a_gap_closure.py (retired
in Slice 2b B10.4) for pdf_to_scouts.py's real coverage gaps, repointed at their package
equivalents now that the flat module is gone. Each one pins one specific branch the domain
matrix catalogs never needed to exercise -- see that retired file's own module docstring for the
original discovery method (real ``coverage --branch`` over the scoped Phase A areas).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from tests.factories.pdf_builder import build_corrupt_pdf, build_multi_qr_image, build_pdf
from tests.matrix.cases.pdf_cases import PdfPageSpec

from scoutmb.adapters.pdf.extract import (
    add_quiet_zone,
    choose_qr_value,
    decode_rendered_qr,
    decode_variants,
    render_page,
)
from scoutmb.adapters.pdf.extract import decode_embedded_qr_from_page as decode_embedded_qr
from scoutmb.adapters.pdf.pages import extract_pdf, value_after_label
from scoutmb.features.ingest.pdf_extract import expand_pdf_inputs
from scoutmb.interfaces.cli.pdf import main as pdf_main

pytestmark = pytest.mark.filterwarnings("ignore")


# =================================================================================================
# expand_pdf_inputs: a glob pattern that matches a directory
# =================================================================================================


def test_expand_pdf_inputs_glob_matching_a_directory_recurses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two glob matches that are BOTH directories, so the `for match in matches:` loop returns to
    # its top after taking the directory branch at least once, regardless of the filesystem's
    # own (unspecified) glob match ordering.
    suba = tmp_path / "suba"
    subb = tmp_path / "subb"
    suba.mkdir()
    subb.mkdir()
    (suba / "a.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    (subb / "b.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    monkeypatch.chdir(tmp_path)
    result = expand_pdf_inputs(["sub*"], recursive=False)
    assert sorted(p.name for p in result) == ["a.pdf", "b.pdf"]


def test_expand_pdf_inputs_ignores_a_literal_non_pdf_file(tmp_path: Path) -> None:
    """A directly-named file that exists but isn't a .pdf takes the `expanded.is_file()` branch
    and then skips the append -- the `if expanded.suffix.lower() == ".pdf":` FALSE arm."""
    non_pdf = tmp_path / "notes.txt"
    non_pdf.write_text("not a pdf")
    result = expand_pdf_inputs([str(non_pdf)], recursive=False)
    assert result == []


def test_expand_pdf_inputs_accepts_a_literal_directory_path(tmp_path: Path) -> None:
    """A directory named directly (not via a glob pattern) takes the `expanded.is_dir()`
    branch, not the Windows-glob fallback the sibling glob-matching-a-directory test covers."""
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    (tmp_path / "not-a-pdf.txt").write_bytes(b"ignored")
    result = expand_pdf_inputs([str(tmp_path)], recursive=False)
    assert [p.name for p in result] == ["a.pdf"]


def test_expand_pdf_inputs_glob_matching_a_single_pdf_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A glob pattern that resolves to a single PDF FILE (not a directory) takes the
    `path.is_file()` branch inside the Windows-glob fallback loop."""
    (tmp_path / "only.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    monkeypatch.chdir(tmp_path)
    result = expand_pdf_inputs(["only.*"], recursive=False)
    assert [p.name for p in result] == ["only.pdf"]


def test_expand_pdf_inputs_deduplicates_a_path_discovered_twice(tmp_path: Path) -> None:
    """The same PDF reachable through two distinct input values (a direct file path and the
    directory containing it) must appear exactly once -- exercising the dedup loop's
    already-seen skip, not just its first-time-append path."""
    pdf_path = tmp_path / "shared.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    result = expand_pdf_inputs([str(pdf_path), str(tmp_path)], recursive=False)
    assert [p.name for p in result] == ["shared.pdf"]


def test_value_after_label_skips_blank_candidates_and_headers_without_a_value() -> None:
    # All lines after the label are blank -- the inner loop exhausts every candidate and the
    # outer loop keeps scanning past the label line itself without a match.
    lines = ["Attendee Information", "  ", " "]
    assert value_after_label(lines, "Attendee Information") == ""


# =================================================================================================
# add_quiet_zone / decode_variants pure-function edge branches
# =================================================================================================


def test_add_quiet_zone_converts_a_3_channel_image_to_grayscale_first() -> None:
    image = np.zeros((40, 40, 3), dtype=np.uint8)
    result = add_quiet_zone(image)
    assert result.ndim == 2


def test_decode_variants_returns_empty_for_a_none_image() -> None:
    detector = cv2.QRCodeDetector()
    assert decode_variants(None, detector) == []


def test_decode_variants_returns_empty_for_an_empty_image() -> None:
    detector = cv2.QRCodeDetector()
    assert decode_variants(np.zeros((0, 0), dtype=np.uint8), detector) == []


def test_decode_variants_recovers_from_otsu_threshold_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: object, **kwargs: object):
        raise cv2.error("otsu boom")

    monkeypatch.setattr(cv2, "threshold", boom)
    detector = cv2.QRCodeDetector()
    image = np.zeros((40, 40), dtype=np.uint8)
    assert decode_variants(image, detector) == []


class _BoomingDetector:
    def detectAndDecode(self, image):
        raise cv2.error("decode boom")

    def detectAndDecodeMulti(self, image):
        raise ValueError("multi boom")


def test_decode_variants_recovers_from_detector_errors() -> None:
    image = np.zeros((40, 40), dtype=np.uint8)
    assert decode_variants(image, _BoomingDetector()) == []


def test_decode_variants_finds_a_second_symbol_via_multi_decode() -> None:
    """A stitched two-symbol image: single-shot detectAndDecode can resolve at most one QR, so
    the second distinct value can only come from the detectAndDecodeMulti branch."""
    image = build_multi_qr_image(("MULTI-VALUE-ONE", "MULTI-VALUE-TWO"))
    detector = cv2.QRCodeDetector()
    values = decode_variants(image, detector)
    assert set(values) == {"MULTI-VALUE-ONE", "MULTI-VALUE-TWO"}


def test_choose_qr_value_falls_back_to_first_non_prefixed_candidate() -> None:
    values = ["https://example.com/other-a", "https://example.com/other-b"]
    assert choose_qr_value(values) == "https://example.com/other-a"


class _QrPixmap:
    def __init__(self, image: np.ndarray) -> None:
        rgb = np.stack([image, image, image], axis=-1)
        self.height, self.width = image.shape
        self.n = 3
        self.samples = rgb.tobytes()


class _FakeRect:
    """US Letter in points -- comfortably under max_pdf_dimension_px at every DPI these tests
    use, since render_page now checks the projected pixel size from page.rect before ever
    calling get_pixmap (Slice 4, D7)."""

    width = 612.0
    height = 792.0


class _QrRenderPage:
    rect = _FakeRect()

    def __init__(self, image: np.ndarray) -> None:
        self._image = image

    def get_pixmap(self, dpi: int, alpha: bool = False):
        return _QrPixmap(self._image)


def test_decode_rendered_qr_returns_on_first_successful_region_decode() -> None:
    image = build_multi_qr_image(("RENDERED-VALUE",))
    page = _QrRenderPage(image)
    detector = cv2.QRCodeDetector()
    value, method, rendered_image = decode_rendered_qr(page, detector, dpis=(144,))
    assert value == "RENDERED-VALUE"
    assert method == "rendered:144dpi:full-page"
    assert rendered_image is not None


# =================================================================================================
# decode_embedded_qr: duplicate xref skip and non-square/oversize filtering
# =================================================================================================


class _FakeDocument:
    def __init__(self, images: dict[int, bytes] | None = None) -> None:
        self._images = images or {}

    def extract_image(self, xref: int):
        return {"image": self._images[xref]}  # KeyError for any xref not seeded


class _FakePage:
    def __init__(self, images: list[tuple]) -> None:
        self._images = images

    def get_images(self, full: bool = True) -> list[tuple]:
        return self._images


def test_decode_embedded_qr_tries_the_next_candidate_when_one_decodes_to_nothing() -> None:
    """A real (blank, no-QR) image for one candidate must not stop the search: the ``if
    selected:`` false branch has to loop back and try the next candidate."""
    blank = np.full((100, 100), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", blank)
    assert ok
    images = [
        (1, 0, 100, 100, 8, "", "", "", "", 0),  # decodes cleanly but has no QR
        (5, 0, 120, 120, 8, "", "", "", "", 0),  # never seeded -> KeyError -> also continues
    ]
    page = _FakePage(images)
    detector = cv2.QRCodeDetector()
    document = _FakeDocument({1: encoded.tobytes()})
    value, method = decode_embedded_qr(document, page, detector)
    assert (value, method) == ("", "")


def test_decode_embedded_qr_skips_duplicate_xrefs_and_bad_sizes() -> None:
    # image_info tuple format (PyMuPDF's Page.get_images(full=True)): (xref, smask, width,
    # height, bpc, colorspace, ...) -- decode_embedded_qr reads width from index 2, height from
    # index 3.
    images = [
        (1, 0, 100, 100, 8, "", "", "", "", 0),  # square, real size -> a real candidate
        (1, 0, 100, 100, 8, "", "", "", "", 0),  # duplicate xref -> must be skipped
        (2, 0, 20, 20, 8, "", "", "", "", 0),  # too small -> filtered
        (3, 0, 2600, 2600, 8, "", "", "", "", 0),  # too large -> filtered
        (4, 0, 100, 400, 8, "", "", "", "", 0),  # not square enough -> filtered
    ]
    page = _FakePage(images)
    detector = cv2.QRCodeDetector()
    # xref 1 remains a real candidate; force its extraction to fail cleanly so this stays a pure
    # unit test of the filtering/dedup logic, not a real-image decode.
    document = _FakeDocument()
    value, method = decode_embedded_qr(document, page, detector)
    assert (value, method) == ("", "")


# =================================================================================================
# render_page's pixmap-channel-count branches
# =================================================================================================


class _FakePixmap:
    def __init__(self, n: int) -> None:
        self.n = n
        self.width = 4
        self.height = 4
        self.samples = bytes(4 * 4 * n)


class _FakeRenderPage:
    rect = _FakeRect()

    def __init__(self, n: int) -> None:
        self._n = n

    def get_pixmap(self, dpi: int, alpha: bool = False):
        return _FakePixmap(self._n)


def test_render_page_converts_rgba_pixmap_to_bgr() -> None:
    image = render_page(_FakeRenderPage(4), 144)
    assert image.shape == (4, 4, 3)


def test_render_page_returns_grayscale_pixmap_unchanged() -> None:
    image = render_page(_FakeRenderPage(1), 144)
    assert image.shape == (4, 4, 1) or image.shape == (4, 4)


# =================================================================================================
# extract_pdf renders a debug PNG using max(dpis) when decode_rendered_qr's own render never ran
# (an empty dpis sequence).
# =================================================================================================


def test_extract_pdf_debug_render_fallback_requires_a_non_empty_dpis(tmp_path: Path) -> None:
    """Characterizes the actual current behavior: with an empty ``dpis`` sequence,
    ``decode_rendered_qr`` never renders anything (so its own ``last_render`` stays ``None``),
    and the debug-PNG fallback then calls ``max(())``, which raises. The real CLI never passes an
    empty ``dpis`` (``parse_args`` defaults to 4 values and validates any override is non-empty
    via ``nargs="+"``), so this is reachable only through direct programmatic misuse -- but
    reaching that line (line coverage counts a statement as covered once execution starts it,
    even if it then raises) is exactly what closes this gap, so the honest fix is to pin the
    raise rather than to paper over it with a friendlier scenario that never actually exercises
    it.
    """
    pdf_path = build_pdf(tmp_path / "one.pdf", (PdfPageSpec("Avery Archer", "Youth", "", "none"),))
    debug_dir = tmp_path / "debug"
    with pytest.raises(ValueError, match="empty"):
        extract_pdf(pdf_path, dpis=(), normalize_case=True, debug_dir=debug_dir)
    assert debug_dir.is_dir()  # mkdir ran before the crash


def test_extract_pdf_records_a_bounded_error_for_an_unopenable_pdf(tmp_path: Path) -> None:
    pdf_path = build_corrupt_pdf(tmp_path / "corrupt.pdf")
    attendees, errors = extract_pdf(pdf_path, dpis=(144,), normalize_case=True, debug_dir=None)
    assert attendees == []
    assert len(errors) == 1
    assert errors[0].source_pdf == "corrupt.pdf"
    assert "Could not open PDF" in errors[0].error


def test_extract_pdf_records_missing_name_and_registrant_type(tmp_path: Path) -> None:
    pdf_path = build_pdf(tmp_path / "blank.pdf", (PdfPageSpec("", "", "", "none"),))
    _attendees, errors = extract_pdf(pdf_path, dpis=(144,), normalize_case=True, debug_dir=None)
    assert len(errors) == 1
    assert "attendee name" in errors[0].error
    assert "registrant type" in errors[0].error
    assert "QR code" in errors[0].error


def test_extract_pdf_writes_a_debug_png_when_the_qr_is_genuinely_missing(tmp_path: Path) -> None:
    pdf_path = build_pdf(tmp_path / "one.pdf", (PdfPageSpec("Avery Archer", "Youth", "", "none"),))
    debug_dir = tmp_path / "debug"
    extract_pdf(pdf_path, dpis=(100,), normalize_case=True, debug_dir=debug_dir)
    written = list(debug_dir.glob("*.png"))
    assert len(written) == 1
    assert written[0].stat().st_size > 0


# =================================================================================================
# main()'s progress_callback
# =================================================================================================


def test_pdf_main_invokes_progress_callback(tmp_path: Path) -> None:
    pdf_path = build_pdf(tmp_path / "one.pdf", (PdfPageSpec("Avery Archer", "Youth", "", "none"),))
    calls: list[tuple[int, int, Path]] = []

    def progress_callback(index: int, total: int, path: Path) -> None:
        calls.append((index, total, path))

    output = tmp_path / "scouts.csv"
    # A single small --render-dpi keeps this fast: the page has no QR at all, so without an
    # explicit override extract_pdf would try every one of the default 4 DPIs (up to 400) across
    # all 5 page regions and every decode_variants scale/threshold combination.
    pdf_main(
        [str(pdf_path), "-o", str(output), "--quiet", "--render-dpi", "100"],
        progress_callback=progress_callback,
    )
    assert calls == [(1, 1, pdf_path)]
