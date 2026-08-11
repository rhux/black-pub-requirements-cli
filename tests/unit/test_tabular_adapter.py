from __future__ import annotations

from pathlib import Path

from scoutmb.adapters.files.tabular import load_csv, load_text


def test_load_csv_without_recognizable_headers_falls_back_to_load_text(tmp_path: Path) -> None:
    """Migrated from tests/characterization/test_phase_a_gap_closure.py (retired in Slice 2b
    B10.4)."""
    path = tmp_path / "no_headers.csv"
    path.write_text("foo,bar\nhttps://example.invalid/?t=X\n", encoding="utf-8")
    result = load_csv(path)
    assert result == load_text(path)
    assert len(result) == 2
    assert result[-1].url == "https://example.invalid/?t=X"


def test_load_csv_of_a_completely_empty_file_falls_back_to_load_text(tmp_path: Path) -> None:
    # csv.DictReader.fieldnames is None for a zero-byte file -- a different route to the same
    # load_text() fallback than "headers present but unrecognized".
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    assert load_csv(path) == load_text(path) == []
