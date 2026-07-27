from __future__ import annotations

from pathlib import Path

import pytest

from scoutmb.core.models import ScoutInput
from scoutmb.errors import ScoutmbError
from scoutmb.features.ingest.service import IngestService, NoSupportedSource

URL_A = "https://scoutingevent.com/mobile/checkin?t=A"
URL_B = "https://scoutingevent.com/mobile/checkin?t=B"


class FakeSource:
    def __init__(self, suffix: str, rows: list[ScoutInput]) -> None:
        self.suffix, self.rows, self.calls = suffix, rows, 0

    def supports(self, path: Path) -> bool:
        return path.suffix == self.suffix

    def load(self, path: Path) -> list[ScoutInput]:
        self.calls += 1
        return list(self.rows)


def _service(rows: list[ScoutInput], *, include_adults: bool = False) -> IngestService:
    return IngestService(sources=(FakeSource(".csv", rows),), include_adults=include_adults)


def test_first_supporting_source_wins() -> None:
    row = ScoutInput(name="Avery", url=URL_A)
    first, second = FakeSource(".csv", [row]), FakeSource(".csv", [])
    service = IngestService(sources=(first, second))
    assert service.load(Path("in.csv")) == [row]
    assert (first.calls, second.calls) == (1, 0)


def test_values_are_normalized_without_mutating_the_adapter_output() -> None:
    row = ScoutInput(name="  Avery  ", url=f"  {URL_A}  ", registrant_type="  Youth  ")
    loaded = _service([row]).load(Path("in.csv"))
    assert loaded == [ScoutInput(name="Avery", url=URL_A, registrant_type="Youth")]
    assert row.name == "  Avery  ", "the adapter's object was mutated in place"


def test_non_scoutingevent_urls_are_dropped() -> None:
    rows = [ScoutInput(name="A", url="https://example.invalid/x"), ScoutInput(name="B", url=URL_A)]
    assert [s.name for s in _service(rows).load(Path("in.csv"))] == ["B"]


@pytest.mark.parametrize("registrant_type", ["Adult", "adult", "Part-Time Adult"])
def test_adults_are_filtered_unless_included(registrant_type: str) -> None:
    rows = [ScoutInput(name="A", url=URL_A, registrant_type=registrant_type)]
    with pytest.raises(ValueError):
        _service(rows).load(Path("in.csv"))
    assert len(_service(rows, include_adults=True).load(Path("in.csv"))) == 1


def test_duplicate_urls_are_dropped_keeping_the_first() -> None:
    rows = [
        ScoutInput(name="First", url=URL_A),
        ScoutInput(name="Second", url=URL_A),
        ScoutInput(name="Third", url=URL_B),
    ]
    assert [s.name for s in _service(rows).load(Path("in.csv"))] == ["First", "Third"]


def test_empty_result_raises_the_legacy_message() -> None:
    path = Path("in.csv")
    with pytest.raises(ValueError) as caught:
        _service([]).load(path)
    assert str(caught.value) == f"No ScoutingEvent QR URLs found in {path}"


def test_no_supporting_source_fails_closed() -> None:
    with pytest.raises(NoSupportedSource) as caught:
        _service([]).load(Path("in.pdf"))
    assert isinstance(caught.value, ScoutmbError)


def test_non_canonical_suffix_falls_through_to_text_parsing(tmp_path: Path) -> None:
    """Regression: legacy load_inputs fell through to line-delimited text parsing for ANY
    unrecognized suffix (the else-branch was unconditional). TabularAttendeeSource.supports()
    must accept files like `.dat`/`.tsv` and let load() apply that same text fallback --
    narrowing supports() to a fixed suffix set made IngestService raise NoSupportedSource
    instead, a real behavior regression caught by spec review of Task 17.

    This exercises the real TabularAttendeeSource through IngestService (the actual
    load_inputs orchestration path), not load_text() directly -- the bug was specifically in
    the supports() gate IngestService checks before ever calling load().
    """
    from scoutmb.adapters.files.tabular import TabularAttendeeSource

    path = tmp_path / "attendees.dat"
    path.write_text(f"Avery,{URL_A}\n", encoding="utf-8")

    service = IngestService(sources=(TabularAttendeeSource(),))
    loaded = service.load(path)

    assert loaded == [ScoutInput(name="Avery", url=URL_A)]
