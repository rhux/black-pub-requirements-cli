from __future__ import annotations

import dataclasses

import pytest

from scoutmb.config import ReleaseLimits


def test_every_release_limit_is_present_finite_and_documented():
    limits = ReleaseLimits()
    for field in dataclasses.fields(limits):
        value = getattr(limits, field.name)
        assert value is not None and value > 0, f"{field.name} must be a positive measured value"
    assert limits.__doc__ and "measured" in limits.__doc__.lower()


def test_upload_over_the_limit_is_rejected_at_the_boundary():
    from scoutmb.errors import ScoutmbError
    from scoutmb.interfaces.web.routes import assert_upload_within_limit

    limits = ReleaseLimits()
    with pytest.raises(ScoutmbError):
        assert_upload_within_limit(size_bytes=limits.max_upload_bytes + 1, limits=limits)

    assert_upload_within_limit(size_bytes=limits.max_upload_bytes, limits=limits)  # must not raise


def test_pdf_over_the_page_limit_is_rejected_before_any_page_is_processed(tmp_path):
    """An oversized PDF is rejected by reading only its page COUNT (fitz.open is lazy about
    page content) and reported as one ExtractionError -- the same graceful-degradation shape
    as this function's existing "could not open PDF" case, never a raised exception that would
    crash an entire multi-file batch over one oversized input."""
    import fitz

    from scoutmb.adapters.pdf.pages import extract_pdf
    from scoutmb.config import ReleaseLimits

    limits = ReleaseLimits()
    oversized = tmp_path / "oversized.pdf"
    document = fitz.open()
    try:
        for _ in range(limits.max_pdf_pages + 1):
            document.new_page()
        document.save(oversized)
    finally:
        document.close()

    attendees, errors = extract_pdf(oversized, dpis=(144,), normalize_case=False, debug_dir=None)

    assert attendees == []
    assert len(errors) == 1
    assert "page" in errors[0].error.lower()


def test_render_page_over_the_dimension_limit_is_rejected():
    from scoutmb.adapters.pdf import extract as extract_module
    from scoutmb.errors import ScoutmbError

    class _FakePixmap:
        width = 99999
        height = 99999
        n = 3
        samples = b""

    class _FakePage:
        def get_pixmap(self, dpi, alpha):
            return _FakePixmap()

    with pytest.raises(ScoutmbError, match="dimension"):
        extract_module.render_page(_FakePage(), dpi=400)
