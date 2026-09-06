from __future__ import annotations

import subprocess


def test_troop349_pdf_help_runs_successfully():
    result = subprocess.run(["uv", "run", "troop349-pdf", "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_troop349_schedule_help_runs_successfully():
    result = subprocess.run(
        ["uv", "run", "troop349-schedule", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_troop349_desktop_entry_point_is_installed_and_dispatches_argparse():
    """troop349 launches a native window/local server -- unsuitable to run headlessly here.
    --help still exercises real argument parsing without starting the app (argparse exits 0
    before create_app()/bind_loopback_socket() are ever reached)."""
    result = subprocess.run(["uv", "run", "troop349", "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_pdf_extraction_end_to_end_against_a_real_synthetic_pdf(tmp_path):
    """README's Step 1 command against a real PDF (synthesized, not a fixture file -- no real
    scout data is ever read from or written to this repo)."""
    from tests.factories.pdf_builder import build_pdf
    from tests.matrix.cases.pdf_cases import PdfPageSpec

    pdf_path = tmp_path / "schedule.pdf"
    build_pdf(
        pdf_path,
        (
            PdfPageSpec(
                name="Test Scout",
                registrant_type="Youth",
                qr_value="https://scoutingevent.com/mobile/abc123?t=xyz",
                qr_mode="embedded",
            ),
        ),
    )
    output_csv = tmp_path / "scouts.csv"

    result = subprocess.run(
        ["uv", "run", "troop349-pdf", str(pdf_path), "--output", str(output_csv), "--strict"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output_csv.exists()
    csv_text = output_csv.read_text(encoding="utf-8-sig")
    assert "Test Scout" in csv_text
    assert "Attendee Name" in csv_text
