# tests/unit/test_errors.py
from __future__ import annotations

from scoutmb.errors import CapabilityUnavailable, ScoutmbError


def test_capability_error_names_capability_distributions_and_remedy() -> None:
    exc = CapabilityUnavailable(capability="pdf", distributions=("PyMuPDF", "opencv-python-headless"), extra="pdf")
    text = str(exc)
    assert "pdf" in text
    assert "PyMuPDF" in text
    assert "opencv-python-headless" in text
    assert "pip install 'scoutmb[pdf]'" in text


def test_capability_error_is_a_scoutmb_error() -> None:
    exc = CapabilityUnavailable(capability="pdf", distributions=("PyMuPDF",), extra="pdf")
    assert isinstance(exc, ScoutmbError)
    assert isinstance(exc, Exception)


def test_error_message_is_not_decorated_with_class_name() -> None:
    """errors.csv and the web layer pass the message through verbatim (ART-SCHEMA-004,
    UI-ROUTE-025). A wrapper that prefixes the class name changes a pinned surface."""
    exc = ScoutmbError("boom")
    assert str(exc) == "boom"
