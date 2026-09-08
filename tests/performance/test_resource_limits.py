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


def test_render_page_over_the_dimension_limit_is_rejected_without_ever_rendering():
    """The check must happen BEFORE get_pixmap() -- get_pixmap allocates the full-size buffer
    itself, so checking only after calling it would let a hostile/oversized page trigger exactly
    the expensive allocation the limit exists to prevent."""

    class _FakeRect:
        width = 20_000.0  # points -- at 400 DPI this projects to ~111,000px, well over the limit
        height = 20_000.0

    class _FakePage:
        rect = _FakeRect()

        def get_pixmap(self, dpi, alpha):
            raise AssertionError("get_pixmap must never be called for an over-limit page")

    from scoutmb.adapters.pdf import extract as extract_module
    from scoutmb.errors import ScoutmbError

    with pytest.raises(ScoutmbError, match="exceeding"):
        extract_module.render_page(_FakePage(), dpi=400)


async def test_oversized_upload_is_rejected_mid_stream_and_leaves_no_partial_file(tmp_path):
    """Full-route integration test: the upload handler must reject an oversized file by reading
    and checking it incrementally, never by buffering the whole thing in memory first (that would
    defeat the entire point of the limit), and must never leave a partial file behind on disk."""
    import httpx

    from scoutmb.config import ReleaseLimits, UiSettings
    from scoutmb.interfaces.web.app import create_app

    settings = UiSettings(data_root=tmp_path)
    app = create_app(settings)
    limits = ReleaseLimits()
    oversized_body = b"%PDF-1.4\n" + b"x" * limits.max_upload_bytes

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/pdf-extract",
                files={"files": ("big.pdf", oversized_body, "application/pdf")},
            )

    assert response.status_code == 413
    assert list(settings.pdf_uploads_dir.iterdir()) == []
