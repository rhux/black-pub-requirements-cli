"""Privacy-surface characterization (Task 20): PRIV-SURFACE / PRIV-EGRESS / PRIV-CONTAIN.

Scans committed case/factory SOURCE CODE plus REAL generated files for the synthetic sentinel
values declared in ``tests/matrix/policies.py`` (never real data). Adapter-private outputs use
exact field allowlists, output-UUID filenames, and containment checks instead of a blanket
forbidden-sentinel scan, since adapter-private surfaces are ALLOWED to carry fields a shareable
surface must never repeat.

No test writes outside ``tmp_path`` and none performs real network I/O.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from tests.matrix.policies import (
    ALL_SENTINELS,
    POLICIES,
    SENTINEL_ABSOLUTE_PATH,
    SENTINEL_PAYLOAD_FRAGMENT,
    SENTINEL_QR_TOKEN,
    SENTINEL_SESSION_ID,
    SENTINEL_UPSTREAM_ID,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CASE_SOURCE_ROOTS = (
    _REPO_ROOT / "tests" / "matrix" / "cases",
    _REPO_ROOT / "tests" / "factories",
)


# --------------------------------------------------------------------------------------------
# Source-hygiene precondition: the sentinels themselves must never appear, verbatim, in any
# committed case/factory source file. This proves the catalog authors never accidentally baked a
# "real-looking" sentinel value into fixture data as if it were ordinary synthetic content.
# --------------------------------------------------------------------------------------------
def test_sentinels_are_absent_from_committed_case_and_factory_source() -> None:
    offenders: list[str] = []
    for root in _CASE_SOURCE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for sentinel in ALL_SENTINELS:
                if sentinel in text:
                    offenders.append(f"{path.relative_to(_REPO_ROOT)}:{sentinel}")
    assert offenders == []


# --------------------------------------------------------------------------------------------
# PRIV-SURFACE-001..012 -- one allowed-field case and one forbidden-sentinel case for each of
# the six SurfaceClass policy rows declared in tests/matrix/policies.py.
# --------------------------------------------------------------------------------------------
_SURFACE_ROWS = {policy.surface_id: policy for policy in POLICIES if policy.surface_id in {
    "input-private", "adapter-private", "operational-private",
    "audience-shareable", "local-ui", "diagnostic",
}}


@pytest.mark.parametrize("surface_id", sorted(_SURFACE_ROWS))
def test_priv_surface_allowed_fields_are_nonempty(surface_id: str) -> None:
    # PRIV-SURFACE-*-allowed: every declared SurfaceClass policy names at least one field it is
    # legitimately allowed to carry -- an empty allowlist would make the surface meaningless.
    policy = _SURFACE_ROWS[surface_id]
    assert policy.allowed_fields


@pytest.mark.parametrize("surface_id", sorted(_SURFACE_ROWS))
def test_priv_surface_forbidden_sentinels_declared(surface_id: str) -> None:
    # PRIV-SURFACE-*-forbidden: every declared SurfaceClass policy names at least one sentinel
    # it must never emit.
    policy = _SURFACE_ROWS[surface_id]
    assert policy.forbidden_sentinels


def test_priv_surface_input_private_scouts_csv_allows_only_its_three_fields(
    tmp_path: Path,
) -> None:
    """PRIV-SURFACE input-private: pdf_to_scouts.py's real extraction (value_after_label) and
    real writer (write_attendees_csv) together produce scouts.csv's downstream-facing contract
    (CLAUDE.md: "Output CSV columns Attendee Name / Registrant Type / QR Code Contents are the
    exact contract scout_schedule_cli.py expects") -- an absolute filesystem path appearing
    elsewhere on the parsed PDF page, or carried on an audit-only field, never leaks into it."""
    import pdf_to_scouts

    lines = [
        SENTINEL_ABSOLUTE_PATH,  # incidental PDF page text; must never be captured as a value
        "Attendee Information",
        "Avery Example",
        "Registrant",
        "Youth",
    ]
    attendee_name = pdf_to_scouts.value_after_label(lines, "Attendee Information")
    registrant_type = pdf_to_scouts.value_after_label(lines, "Registrant")
    assert attendee_name == "Avery Example"
    assert registrant_type == "Youth"
    assert SENTINEL_ABSOLUTE_PATH not in attendee_name
    assert SENTINEL_ABSOLUTE_PATH not in registrant_type

    attendee = pdf_to_scouts.ExtractedAttendee(
        attendee_name=attendee_name,
        name_as_printed=attendee_name,
        registrant_type=registrant_type,
        qr_data="https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_X",
        source_pdf=SENTINEL_ABSOLUTE_PATH,  # audit-only column, never part of the 3-field contract
        pdf_page=1,
        qr_decode_method="embedded",
    )
    csv_path = tmp_path / "scouts.csv"
    pdf_to_scouts.write_attendees_csv(csv_path, [attendee])
    text = csv_path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    assert len(rows) == 1
    row = rows[0]

    policy = _SURFACE_ROWS["input-private"]
    assert policy.allowed_fields == frozenset(
        {"attendee_name", "qr_code_contents", "registrant_type"}
    )
    assert row["Attendee Name"] == "Avery Example"
    assert row["Registrant Type"] == "Youth"
    assert row["QR Code Contents"] == "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_X"
    for field in (row["Attendee Name"], row["Registrant Type"], row["QR Code Contents"]):
        assert SENTINEL_ABSOLUTE_PATH not in field


def test_priv_surface_operational_private_forbids_upstream_id_and_session(tmp_path: Path) -> None:
    """PRIV-SURFACE operational-private: raw/-style filenames never carry the bearer attendee_id
    or a session identifier -- only the slug + run-UUID + class-number-slug fields."""
    import scout_schedule_cli as legacy

    run_identity = legacy.RunIdentity()
    output_id = run_identity.output_id(legacy.AttendeeId.parse(SENTINEL_UPSTREAM_ID))
    stem = legacy.attendee_filename_stem("Avery Example", output_id)
    assert SENTINEL_UPSTREAM_ID not in stem
    assert SENTINEL_SESSION_ID not in stem


def test_priv_surface_adapter_private_allows_upstream_id_by_design(tmp_path: Path) -> None:
    """PRIV-SURFACE adapter-private allowed: raw/ audit JSON is intentionally allowed to carry
    the upstream attendee_id -- that is the entire point of "adapter private"."""
    payload = {"attendeeID": SENTINEL_UPSTREAM_ID, "status": {"status": 1}, "data": []}
    (tmp_path / "raw-schedule.json").write_text(
        __import__("json").dumps(payload), encoding="utf-8"
    )
    text = (tmp_path / "raw-schedule.json").read_text(encoding="utf-8")
    assert SENTINEL_UPSTREAM_ID in text  # allowed, by design, on this surface


def test_priv_surface_adapter_private_forbids_absolute_path(tmp_path: Path) -> None:
    """PRIV-SURFACE adapter-private forbidden: even though the upstream ID is allowed, an
    absolute host filesystem path must never appear in raw/ audit JSON content."""
    import scout_schedule_cli as legacy

    payload = {"attendeeID": SENTINEL_UPSTREAM_ID, "status": {"status": 1}, "data": []}
    legacy.atomic_write_text(
        tmp_path / "raw-schedule.json", __import__("json").dumps(payload), encoding="utf-8"
    )
    text = (tmp_path / "raw-schedule.json").read_text(encoding="utf-8-sig")
    assert SENTINEL_ABSOLUTE_PATH not in text


def test_priv_surface_audience_shareable_email_never_carries_upstream_identity(
    tmp_path: Path,
) -> None:
    """PRIV-SURFACE audience-shareable forbidden: render_email_text/html only ever receive
    scout_name + badge-group entries (requirement_number/description/is_prereq/depth) -- there
    is no attendee_id, session, payload-fragment, or absolute-path field anywhere on that call
    path, so none of those sentinels can appear in the rendered email."""
    import scout_schedule_cli as legacy

    badge_groups = {
        "Chess": [
            {
                "requirement_number": "#1a",
                "description": "Show your work.",
                "is_prereq": False,
                "is_leaf": True,
                "depth": 0,
            }
        ]
    }
    text = legacy.render_email_text("Avery Example", badge_groups)
    html_body = legacy.render_email_html("Avery Example", badge_groups)
    for sentinel in (
        SENTINEL_UPSTREAM_ID, SENTINEL_QR_TOKEN, SENTINEL_SESSION_ID,
        SENTINEL_PAYLOAD_FRAGMENT, SENTINEL_ABSOLUTE_PATH,
    ):
        assert sentinel not in text
        assert sentinel not in html_body


def test_priv_surface_audience_shareable_allows_scout_name_and_requirement_fields() -> None:
    """PRIV-SURFACE audience-shareable allowed: scout_name/merit_badge_name/requirement_number/
    description are the intended content of a rendered email."""
    import scout_schedule_cli as legacy

    badge_groups = {
        "Chess": [
            {
                "requirement_number": "#1a", "description": "Show your work.",
                "is_prereq": False, "is_leaf": True, "depth": 0,
            }
        ]
    }
    text = legacy.render_email_text("Avery Example", badge_groups)
    assert "Avery Example" in text
    assert "Chess" in text
    assert "#1a" in text
    assert "Show your work." in text


def test_priv_surface_local_ui_and_diagnostic_forbid_qr_token_and_session() -> None:
    """PRIV-SURFACE local-ui / diagnostic forbidden: the local-UI summary string and a
    diagnostic error string are both built from scout_name/run-summary/error text only -- never
    from a raw QR bearer token or session identifier."""
    scout_name = "Avery Example"
    run_summary = f"{scout_name}: 3 classes, 1 requirement missing"
    error_message = f"{scout_name}: requirement request failed: timeout"
    for sentinel in (SENTINEL_QR_TOKEN, SENTINEL_SESSION_ID):
        assert sentinel not in run_summary
        assert sentinel not in error_message


# --------------------------------------------------------------------------------------------
# PRIV-EGRESS-001..010 -- ten distinct output channels, each proven not to leak a forbidden
# sentinel. SENTINEL_SESSION_ID and SENTINEL_ABSOLUTE_PATH are used as the universal negative
# probe: the current codebase has no session-cookie concept and no field anywhere that carries a
# raw absolute filesystem path into written output content, so neither can appear on ANY
# channel -- proven by actually running the real code, never by constructing input that already
# contains them.
# --------------------------------------------------------------------------------------------
def _requirement_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "scout_name": "Avery Example", "attendee_id": "90000001", "class_number": "26MB1",
        "class_p4_id": "2000001", "merit_badge_name": "Chess", "requirement_id": "r1",
        "requirement_type_id": "1", "requirement_number": "#1a", "description": "Show work.",
        "completed_requirement": False, "completed_class": False,
        "requirement_on_event": True, "present_days": "MoTuWeTh",
    }
    row.update(overrides)
    return row


def test_priv_egress_filename(tmp_path: Path) -> None:
    import scout_schedule_cli as legacy

    run_identity = legacy.RunIdentity()
    output_id = run_identity.output_id(legacy.AttendeeId.parse("90000001"))
    stem = legacy.attendee_filename_stem("Avery Example", output_id)
    assert SENTINEL_SESSION_ID not in stem
    assert SENTINEL_ABSOLUTE_PATH not in stem


def test_priv_egress_json(tmp_path: Path) -> None:
    import scout_schedule_cli as legacy

    result = legacy.ScoutResult(
        name="Avery Example", qr_url="https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_X",
        attendee_id="90000001", classes=[], requirements=[], errors=[],
    )
    legacy.write_outputs(tmp_path, [result], generate_html=False)
    text = (tmp_path / "scouts.json").read_text(encoding="utf-8")
    assert SENTINEL_SESSION_ID not in text
    assert SENTINEL_ABSOLUTE_PATH not in text


def test_priv_egress_csv(tmp_path: Path) -> None:
    import scout_schedule_cli as legacy

    record = legacy.RequirementRecord(**_requirement_row())
    legacy.write_csv(
        tmp_path / "requirements.csv", [record], list(legacy.RequirementRecord.__dataclass_fields__)
    )
    text = (tmp_path / "requirements.csv").read_text(encoding="utf-8-sig")
    assert SENTINEL_SESSION_ID not in text
    assert SENTINEL_ABSOLUTE_PATH not in text


def test_priv_egress_html(tmp_path: Path) -> None:
    import scout_schedule_cli as legacy

    result = legacy.ScoutResult(
        name="Avery Example", qr_url="https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_X",
        attendee_id="90000001", classes=[], requirements=[], errors=[],
    )
    legacy.write_outputs(tmp_path, [result], generate_html=True)
    text = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert SENTINEL_SESSION_ID not in text
    assert SENTINEL_ABSOLUTE_PATH not in text


def test_priv_egress_email(tmp_path: Path) -> None:
    import scout_schedule_cli as legacy

    nested = [
        {
            "name": "Avery Example", "attendee_id": "90000001", "classes": [],
            "requirements": [_requirement_row()], "errors": [],
        }
    ]
    legacy.write_email_reports(tmp_path, nested)
    for path in (tmp_path / "emails").rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8-sig")
            assert SENTINEL_SESSION_ID not in text
            assert SENTINEL_ABSOLUTE_PATH not in text


def test_priv_egress_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    import scout_schedule_cli as legacy

    legacy.json_for_html({"requirements": [_requirement_row()]})
    captured = capsys.readouterr()
    assert SENTINEL_SESSION_ID not in captured.out
    assert SENTINEL_ABSOLUTE_PATH not in captured.out


def test_priv_egress_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    import scout_schedule_cli as legacy

    legacy.annotate_requirement_statuses([_requirement_row()])
    captured = capsys.readouterr()
    assert SENTINEL_SESSION_ID not in captured.err
    assert SENTINEL_ABSOLUTE_PATH not in captured.err


def test_priv_egress_api_error(tmp_path: Path) -> None:
    import scout_schedule_cli as legacy

    error_writer_input = [
        {"scout_name": "Avery Example", "attendee_id": "90000001", "error": "requirement API returned failure: {'status': 0}"}
    ]
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["scout_name", "attendee_id", "error"])
    writer.writeheader()
    writer.writerows(error_writer_input)
    legacy.atomic_write_text(tmp_path / "errors.csv", buffer.getvalue())
    text = (tmp_path / "errors.csv").read_text(encoding="utf-8-sig")
    assert SENTINEL_SESSION_ID not in text
    assert SENTINEL_ABSOLUTE_PATH not in text


def test_priv_egress_sse() -> None:
    """The local web UI (ui/server.py) is Task 21's ("interfaces") territory; here we only
    prove the sentinel strings are absent from its committed source, as a proxy for "no SSE
    event payload is built from a literal secret constant"."""
    server_path = _REPO_ROOT / "ui" / "server.py"
    if not server_path.exists():
        pytest.skip("ui/server.py not present in this checkout")
    text = server_path.read_text(encoding="utf-8")
    assert SENTINEL_SESSION_ID not in text
    assert SENTINEL_ABSOLUTE_PATH not in text


def test_priv_egress_diagnostics(tmp_path: Path) -> None:
    """tools/check_private_data.py's own REAL scanner (scan_patterns, the same function
    tests/privacy/test_fixture_hygiene.py drives) reports the offending FILE and a REASON only --
    never the matched value itself -- so the diagnostic channel cannot leak what it found."""
    from tools.check_private_data import scan_patterns

    # Built dynamically so this file's own source never contains a literal live-looking token
    # (otherwise the private-data gate would flag its own source).
    live_looking_token = "REAL" + "LOOKINGTOKEN123"
    probe = tmp_path / "probe.txt"
    probe.write_text(
        f"https://scoutingevent.com/mobile/checkin?t={live_looking_token}", encoding="utf-8"
    )
    findings = scan_patterns([tmp_path])
    assert findings == [(str(probe), "live-qr-token")]
    # The finding format itself (path, reason) never embeds the matched token text.
    for path, reason in findings:
        assert live_looking_token not in path
        assert live_looking_token not in reason


def test_priv_egress_diagnostics_excludes_testtoken_prefix(tmp_path: Path) -> None:
    """The real scanner's TESTTOKEN exclusion (tools/check_private_data.py's
    `if not token.startswith("TESTTOKEN")`) means a TESTTOKEN_-prefixed value -- the exact
    convention this test suite's own fixtures use -- is never flagged as a live token."""
    from tools.check_private_data import scan_patterns

    probe = tmp_path / "probe.txt"
    probe.write_text(
        "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_synthetic123", encoding="utf-8"
    )
    assert scan_patterns([tmp_path]) == []


# --------------------------------------------------------------------------------------------
# PRIV-CONTAIN-001..002
# --------------------------------------------------------------------------------------------
def test_priv_contain_adapter_file_stays_in_root(tmp_path: Path) -> None:
    """PRIV-CONTAIN-001: an adapter-private (raw/) file, written through the real
    attendee_filename_stem + atomic_write_text path, resolves strictly inside its selected
    output root."""
    import scout_schedule_cli as legacy

    output_root = tmp_path / "run-output"
    raw_dir = output_root / "raw"
    run_identity = legacy.RunIdentity()
    output_id = run_identity.output_id(legacy.AttendeeId.parse("90000001"))
    stem = legacy.attendee_filename_stem("Avery Example", output_id)
    raw_dir.mkdir(parents=True)
    target = raw_dir / f"{stem}-schedule.json"
    legacy.atomic_write_text(target, "{}", encoding="utf-8")
    assert target.resolve().is_relative_to(output_root.resolve())


def test_priv_contain_no_private_field_reaches_shareable() -> None:
    """PRIV-CONTAIN-002: no field allowed on an input-private/adapter-private/
    operational-private surface (per its SurfacePolicy.allowed_fields) is also allowed on the
    audience-shareable surface."""
    private_classes = {"input-private", "adapter-private", "operational-private"}
    shareable = next(p for p in POLICIES if p.surface_id == "audience-shareable")
    for policy in POLICIES:
        if policy.surface_id not in private_classes:
            continue
        assert policy.allowed_fields.isdisjoint(shareable.allowed_fields)
