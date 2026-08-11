import json
import os
from pathlib import Path

import pytest

from scoutmb.adapters.files.atomic import atomic_write_text
from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutResult
from scoutmb.interfaces.cli.composition import build_reporting_service


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


@pytest.mark.matrix_case(case_id="ART-FAIL-003", context_id="atomic_fail", lane="default")
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


# =================================================================================================
# ART-FAIL-001/002/004/005/006 -- the remaining atomic_write_text filesystem seams
# (Path.open, os.fsync, a multi-file partial-publish ordering, and Path.unlink inside the
# finally cleanup block), plus the after-atomic-replace/partial-multi-file write_outputs
# ordering claims. ART-FAIL-003 (os.replace itself) is covered above.
# =================================================================================================


@pytest.mark.matrix_case(case_id="ART-FAIL-001", context_id="atomic_fail", lane="default")
def test_open_failure_leaves_destination_untouched_and_creates_no_tmp(tmp_path, monkeypatch):
    """Path.open on the temp file raises before any bytes are written at all."""
    p = tmp_path / "scouts.json"
    p.write_text("prior-content", encoding="utf-8-sig")

    real_open = Path.open

    def boom_open(self, *args, **kwargs):
        if self.name.endswith(".tmp"):
            raise OSError("open failed")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", boom_open)

    with pytest.raises(OSError):
        atomic_write_text(p, "new-content-that-must-not-land")

    assert p.read_text(encoding="utf-8-sig") == "prior-content"
    assert list(tmp_path.glob("*.tmp")) == []  # nothing for the finally unlink to do


@pytest.mark.matrix_case(case_id="ART-FAIL-002", context_id="atomic_fail", lane="default")
def test_fsync_failure_leaves_destination_untouched_and_cleans_up_tmp(tmp_path, monkeypatch):
    """os.fsync raises after the temp file's content was fully written but before os.replace."""
    p = tmp_path / "scouts.json"
    p.write_text("prior-content", encoding="utf-8-sig")

    def boom_fsync(_fd):
        raise OSError("fsync failed")

    monkeypatch.setattr(os, "fsync", boom_fsync)

    with pytest.raises(OSError):
        atomic_write_text(p, "new-content-that-must-not-land")

    assert p.read_text(encoding="utf-8-sig") == "prior-content"
    assert list(tmp_path.glob("*.tmp")) == []  # finally block removed the orphaned .tmp


@pytest.mark.matrix_case(case_id="ART-FAIL-005", context_id="atomic_fail", lane="default")
def test_unlink_failure_after_successful_replace_still_propagates(tmp_path, monkeypatch):
    """Path.unlink raises INSIDE the finally block AFTER os.replace already succeeded: the
    publish itself succeeded (destination has the NEW content), but the caller still sees the
    exception from the failed cleanup."""
    p = tmp_path / "scouts.json"
    p.write_text("prior-content", encoding="utf-8-sig")

    real_unlink = Path.unlink

    def boom_unlink(self, *args, **kwargs):
        if self.name.endswith(".tmp"):
            raise OSError("unlink failed")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", boom_unlink)

    with pytest.raises(OSError):
        atomic_write_text(p, "new-content")

    # The publish itself succeeded -- os.replace already landed the new content -- even though
    # the caller still observes the propagated cleanup failure.
    assert p.read_text(encoding="utf-8-sig") == "new-content"


def _one_scout_result() -> ScoutResult:
    class_record = ClassRecord(
        scout_name="Avery Example",
        attendee_id="90000001",
        class_number="26MB1",
        class_p4_id="2000001",
        class_name="Chess",
        days="MoTuWeTh",
        period_name="A Block",
        start_time="09:00 AM",
        start_time_24h="09:00:00",
        location="Pavilion",
        has_requirements=True,
        class_completed=False,
        raw_class_name="MoTuWeTh - Chess - 26MB1 (Pavilion)",
    )
    requirement_record = RequirementRecord(
        scout_name="Avery Example",
        attendee_id="90000001",
        class_number="26MB1",
        class_p4_id="2000001",
        merit_badge_name="Chess",
        requirement_id="r1",
        requirement_type_id="1",
        requirement_number="#1a",
        description="Show your work.",
        completed_requirement=False,
        completed_class=False,
        requirement_on_event=True,
        present_days="MoTuWeTh",
    )
    return ScoutResult(
        name="Avery Example",
        qr_url="https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_X",
        attendee_id="90000001",
        classes=(class_record,),
        requirements=(requirement_record,),
        errors=(),
    )


def _fail_on_nth_replace(n: int, monkeypatch):
    real_replace = os.replace
    state = {"count": 0}

    def _replace(src, dst):
        state["count"] += 1
        if state["count"] == n:
            raise OSError(f"replace #{n} failed")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _replace)


@pytest.mark.matrix_case(case_id="ART-FAIL-004", context_id="atomic_fail", lane="default")
def test_write_outputs_earlier_successful_publish_is_not_rolled_back(tmp_path, monkeypatch):
    """write_outputs' FIRST atomic_write_text call (scouts.json) succeeds and is durably
    published; injecting a failure on the SECOND call (classes.csv) leaves the first file's
    successful content intact."""
    out = tmp_path / "run"
    _fail_on_nth_replace(2, monkeypatch)

    with pytest.raises(OSError):
        build_reporting_service().publish(
            out,
            [_one_scout_result()],
            generated_at_local="2026-01-01 00:00:00",
            generated_at_iso="2026-01-01T00:00:00",
            run_identity=RunIdentity(),
            generate_html=True,
        )

    scouts_json = out / "scouts.json"
    assert scouts_json.exists()
    payload = json.loads(scouts_json.read_text(encoding="utf-8"))
    assert len(payload) == 1


@pytest.mark.matrix_case(case_id="ART-FAIL-006", context_id="atomic_fail", lane="default")
def test_write_outputs_partial_multi_file_failure_stops_later_siblings(tmp_path, monkeypatch):
    """write_outputs calls atomic_write_text for scouts.json, classes.csv, requirements.csv,
    errors.csv, the HTML report, then summary.json, in that fixed order; injecting a failure on
    os.replace for the THIRD call (requirements.csv) leaves scouts.json and classes.csv
    published, requirements.csv untouched/absent, and every later sibling never attempted."""
    out = tmp_path / "run"
    _fail_on_nth_replace(3, monkeypatch)

    with pytest.raises(OSError):
        build_reporting_service().publish(
            out,
            [_one_scout_result()],
            generated_at_local="2026-01-01 00:00:00",
            generated_at_iso="2026-01-01T00:00:00",
            run_identity=RunIdentity(),
            generate_html=True,
        )

    assert (out / "scouts.json").exists() is True
    assert (out / "classes.csv").exists() is True
    assert (out / "requirements.csv").exists() is False
    assert (out / "errors.csv").exists() is False
    assert (out / "report.html").exists() is False
    assert (out / "summary.json").exists() is False


@pytest.mark.matrix_case(case_id="PDF-SCHEMA-001", context_id="schema", lane="default")
def test_write_attendees_csv_header_unchanged_after_atomic_routing(tmp_path):
    import csv

    from scoutmb.core.models import ExtractedAttendee
    from scoutmb.features.ingest.pdf_extract import write_attendees_csv

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
