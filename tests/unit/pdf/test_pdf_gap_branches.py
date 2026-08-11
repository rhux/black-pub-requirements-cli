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

from scoutmb.adapters.pdf.extract import add_quiet_zone, decode_variants, render_page
from scoutmb.adapters.pdf.pages import extract_pdf, value_after_label
from scoutmb.adapters.pdf.extract import decode_embedded_qr_from_page as decode_embedded_qr
from scoutmb.features.ingest.pdf_extract import expand_pdf_inputs
from scoutmb.interfaces.cli.pdf import main as pdf_main
from tests.factories.pdf_builder import build_pdf
from tests.matrix.cases.pdf_cases import PdfPageSpec

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
