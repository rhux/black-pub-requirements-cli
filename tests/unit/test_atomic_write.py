import os

import pytest
from scout_schedule_cli import atomic_write_text


def test_success_replaces_and_roundtrips_encoding(tmp_path):
    p = tmp_path / "scouts.csv"
    p.write_text("old", encoding="utf-8-sig")
    atomic_write_text(p, "new")  # default encoding is utf-8-sig
    assert p.read_text(encoding="utf-8-sig") == "new"  # read with the SAME codec
    assert list(tmp_path.glob("*.tmp")) == []


def test_plain_utf8_roundtrips(tmp_path):
    p = tmp_path / "report.html"
    atomic_write_text(p, "<html>x</html>", encoding="utf-8")
    assert p.read_text(encoding="utf-8") == "<html>x</html>"


def test_failure_during_replace_preserves_original(tmp_path, monkeypatch):
    p = tmp_path / "scouts.csv"
    p.write_text("irreplaceable", encoding="utf-8-sig")

    def boom(_src, _dst):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError):
        atomic_write_text(p, "new content that must not land")
    assert p.read_text(encoding="utf-8-sig") == "irreplaceable"  # original intact
    assert list(tmp_path.glob("*.tmp")) == []  # temp cleaned up


def test_write_attendees_csv_header_unchanged_after_atomic_routing(tmp_path):
    import csv

    from pdf_to_scouts import ExtractedAttendee, write_attendees_csv

    a = ExtractedAttendee(
        attendee_name="Avery Archer",
        name_as_printed="Avery Archer",
        registrant_type="Youth",
        qr_data="https://example.invalid/?t=TESTTOKEN0001",
        source_pdf="s.pdf",
        pdf_page=1,
        qr_decode_method="embedded",
    )
    out = tmp_path / "scouts.csv"
    write_attendees_csv(out, [a])
    with out.open(encoding="utf-8-sig", newline="") as fh:
        header = next(csv.reader(fh))
    assert header == [
        "Attendee Name",
        "Registrant Type",
        "QR Code Contents",
        "Name as Printed",
        "Source PDF",
        "PDF Page",
        "QR Decode Method",
    ]
