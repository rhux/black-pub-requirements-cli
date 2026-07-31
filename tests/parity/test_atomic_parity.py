"""CRLF survives only because DictWriter's \\r\\n meets a newline="" handle. Change either
half and ART-SCHEMA-002/003 break, so both halves are pinned here."""

from __future__ import annotations

import contextlib
from pathlib import Path

import scout_schedule_cli as legacy

from scoutmb.adapters.files.atomic import atomic_write_text, write_csv


def test_legacy_names_are_the_package_objects() -> None:
    assert legacy.atomic_write_text is atomic_write_text
    assert legacy.write_csv is write_csv


def test_csv_bytes_are_utf8_sig_with_crlf(tmp_path: Path) -> None:
    from scoutmb.core.models import ClassRecord

    record = ClassRecord(
        scout_name="Avery Example",
        attendee_id="90000001",
        class_number="26MB1",
        class_p4_id="2000001",
        class_name="Chess",
        days="MoTuWeTh",
        period_name="Period 1",
        start_time="9:00 AM",
        start_time_24h="09:00",
        location="Pavilion",
        has_requirements=True,
        class_completed=False,
        raw_class_name="MoTuWeTh - Chess",
    )
    target = tmp_path / "classes.csv"
    write_csv(target, [record], [f.name for f in ClassRecord.__dataclass_fields__.values()])

    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "utf-8-sig BOM missing"
    assert b"\r\n" in raw
    assert b"\n\n" not in raw, "line terminators were translated -- newline='' was lost"


def test_atomic_write_preserves_prior_bytes_on_failure(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "artifact.json"
    target.write_text("original", encoding="utf-8")

    def explode(*args: object, **kwargs: object) -> None:
        raise OSError("injected")

    monkeypatch.setattr("os.replace", explode)
    with contextlib.suppress(OSError):
        atomic_write_text(target, "replacement", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "original"
