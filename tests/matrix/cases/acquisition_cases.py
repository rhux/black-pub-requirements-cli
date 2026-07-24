"""Acquisition characterization catalog (Task 19).

Almost every row is ``preserve``: it pins the *current* behavior of ``scout_schedule_cli``'s
acquisition pipeline (``form_values`` / ``is_schedule_response`` / ``navigate_and_trigger_schedule``
/ ``post_requirement`` / ``process_scout`` / ``RunIdentity.output_id``), not a desired future
behavior. Two rows are ``intentional-change`` (``ACQ-HASREQ-002``, ``ACQ-REQ-004``): they pin the
CURRENT legacy behavior as the observation but record what Slice 2 will do instead. The
``ACQ-BREAKER-*`` / ``ACQ-RESUME-*`` / ``NET-WIRE-*`` rows are ``new-acceptance`` metadata-only
placeholders owned by Slice 2 -- nothing in the current branch implements a circuit breaker, a
resumable checkpoint, or an extracted network gateway, so these carry no execution context.

This module holds only frozen data -- it never imports the legacy application
(``scout_schedule_cli``), ``scoutmb``, or any optional third-party package (``playwright``). The
runners in ``tests/characterization/test_acquisition_matrix.py`` and
``tests/characterization/test_browser_matrix.py`` perform the real imports and drive the real
code through the strict fakes in ``tests/fakes/``.

Execution contexts (each executable case declares exactly one, in ``meta.contexts``):

* ``form`` -- calls the real ``form_values`` / ``is_schedule_response`` directly against a
  minimal ``FormResponseStub``. ``script`` holds one ``("schedule", ScriptedResponse(value=post_data))``
  pair carrying the raw POST body to parse; ``expected_legacy.result`` is
  ``(("form", sorted-items), ("is_schedule_response", bool))``.
* ``process`` -- drives the real ``process_scout`` end to end through the strict fake
  Browser/Context/Page, comparing the projected ``ScoutResult`` (``expected_legacy.result``),
  the ordered ``calls``, the recorded ``waits_ms``, and normalized ``relative_files`` (the
  per-run UUID segment collapsed to the literal ``<uuid>``), and always asserting the fake
  context was closed and the script fully consumed.
* ``raw`` -- like ``process``, but reads the raw/ JSON files back by pattern (a real,
  un-normalized UUIDv4 hex segment) instead of comparing filenames literally.
* ``identity`` -- calls ``RunIdentity.output_id`` directly (no browser at all).
* ``asset`` -- drives ``process_scout`` for a happy-path scout, then inspects/invokes the
  ``context.route(...)`` handler ``process_scout`` registered (or asserts none was registered).

Non-ACQ rows in this catalog (``FAKE-STRICT-*``, ``BROWSER-LOCAL-*``, ``BROWSER-EGRESS-*``,
``NET-POLICY-*``, ``NET-WIRE-*``) are plain ``CaseMetadata`` -- they characterize the strict-fake
misuse contract, the guarded browser harness, and the existing network-policy boundary rather
than one ``AcquisitionCase`` shape, so they are declared directly as metadata tuples that the
matching test modules dispatch on by ``case_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tests.fakes.acquisition import AJAX_URL
from tests.matrix.model import (
    CaseMetadata,
    Classification,
    Domain,
    EvidenceKind,
    Lane,
)

# Synthetic identities only -- never real scout data.
NAME_A = "Avery Example"
NAME_B = "Bailey Example"
URL_A = "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_A"
URL_B = "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_B"
ATTENDEE_A = "90000001"
ATTENDEE_B = "90000002"
CLASS_A = "2000001"
CLASS_B = "2000002"


@dataclass(frozen=True, slots=True)
class ExpectedRequest:
    operation: Literal["schedule", "requirement", "wait"]
    attendee_id: str
    class_id: str = ""
    delay_ms: int = 0


@dataclass(frozen=True, slots=True)
class ScriptedResponse:
    value: object | None = None
    error_type: type[Exception] | None = None
    error_message: str = ""


@dataclass(frozen=True, slots=True)
class AcquisitionObservation:
    result: tuple[object, ...] = ()
    calls: tuple[ExpectedRequest, ...] = ()
    waits_ms: tuple[int, ...] = ()
    relative_files: tuple[str, ...] = ()
    closed: bool = True


@dataclass(frozen=True, slots=True)
class AcquisitionCase:
    meta: CaseMetadata
    scout_name: str
    qr_url: str
    script: tuple[tuple[ExpectedRequest, ScriptedResponse], ...]
    expected_legacy: AcquisitionObservation | None
    request_delay_ms: int = 0
    allow_dead_assets: bool = False
    timeout_seconds: int = 5


def _meta(
    case_id: str,
    axis_id: str,
    member: str,
    context: str,
    rationale: str,
    evidence_reference: str,
    *,
    classification: Classification = Classification.PRESERVE,
    surface_id: str | None = None,
    target_owner: str | None = None,
    target_observation: str | None = None,
    lane: Lane = Lane.DEFAULT,
) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id=axis_id,
        member=member,
        domain=Domain.ACQUISITION,
        classification=classification,
        evidence=EvidenceKind.CURRENT_BRANCH,
        rationale=rationale,
        contexts=(context,),
        evidence_reference=evidence_reference,
        surface_id=surface_id,
        target_owner=target_owner,
        target_observation=target_observation,
        lane=lane,
    )


def _class_row(
    class_p4_id: str,
    class_number: str = "26MB1",
    *,
    has_req: str = "1",
    completed: str = "0",
    name: str = "Chess",
) -> dict[str, object]:
    return {
        "classP4ID": class_p4_id,
        "CLASS_NAME": f"MoTuWeTh - {name} - {class_number} (Pavilion)",
        "CLASS_NAME_ONLY": name,
        "CLASS_NBR": class_number,
        "PERIOD_NAME": "A Block",
        "CLASS_STIME": "09:00 AM",
        "STIME": "09:00:00",
        "LOCATION_ROOM_NAME": "Pavilion",
        "HAS_REQ": has_req,
        "CLASS_COMPLETED": completed,
    }


def _req_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "MDM_LKP_BADGE_REQ_ID": "r1",
        "MDM_LKP_BADGE_REQ_TYPE_ID": "1",
        "MERIT_BADGE_NAME": "Chess",
        "REQ_NBR": "1",
        "REQ_NBR_WEB_DISPLAY": "#1",
        "REQ_DESCR": "Discuss the history of chess.",
        "COMPLETED_REQ_FLAG": "0",
        "COMPLETED_CLASS_FLAG": "0",
        "REQ_ON_EVENT": "1",
        "PRESENT_DAYS": "MoTuWeTh",
    }
    row.update(overrides)
    return row


def _schedule_payload(rows: tuple[dict[str, object], ...], status: int = 1) -> dict[str, object]:
    return {"status": {"status": status}, "data": list(rows)}


def _requirement_payload(
    rows: tuple[dict[str, object], ...] = (), status: int = 1
) -> dict[str, object]:
    return {"status": {"status": status}, "data": list(rows)}


def _sched(attendee_id: str, payload: object) -> tuple[ExpectedRequest, ScriptedResponse]:
    # `payload` is a schedule-payload dict for "process"/"raw" context cases, or a raw POST-body
    # string for "form" context cases that exercise form_values/is_schedule_response directly.
    return (ExpectedRequest("schedule", attendee_id), ScriptedResponse(value=payload))


def _req(
    attendee_id: str, class_id: str, payload: dict[str, object]
) -> tuple[ExpectedRequest, ScriptedResponse]:
    return (ExpectedRequest("requirement", attendee_id, class_id), ScriptedResponse(value=payload))


def _req_fail(
    attendee_id: str, class_id: str, message: str = "synthetic timeout"
) -> tuple[ExpectedRequest, ScriptedResponse]:
    return (
        ExpectedRequest("requirement", attendee_id, class_id),
        ScriptedResponse(error_type=TimeoutError, error_message=message),
    )


def _wait(ms: int) -> tuple[ExpectedRequest, ScriptedResponse]:
    return (ExpectedRequest("wait", "", "", ms), ScriptedResponse(value=None))


# --------------------------------------------------------------------------------------------
# ACQ-RESP / ACQ-ID: form_values + is_schedule_response, called directly (no browser).
# --------------------------------------------------------------------------------------------
_RESP_CASES: tuple[AcquisitionCase, ...] = (
    AcquisitionCase(
        _meta(
            "ACQ-RESP-001",
            "ACQ-RESP",
            "correct",
            "form",
            "The real ajax_mobile.php URL with getUnitClass=true is recognized as the schedule "
            "response.",
            "scout_schedule_cli.is_schedule_response lines 358-362",
        ),
        NAME_A,
        AJAX_URL,
        (_sched(ATTENDEE_A, "getUnitClass=true&attendeeID=" + ATTENDEE_A),),
        AcquisitionObservation(
            result=(
                ("form", (("attendeeID", ATTENDEE_A), ("getUnitClass", "true"))),
                ("is_schedule_response", True),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-RESP-002",
            "ACQ-RESP",
            "wrong-url",
            "form",
            "A response whose URL is not ajax_mobile.php is never the schedule response, "
            "regardless of its form body.",
            "scout_schedule_cli.is_schedule_response line 359 URL guard",
        ),
        NAME_A,
        "https://scoutingevent.com/mobile/other.php",
        (
            (
                ExpectedRequest("schedule", ATTENDEE_A),
                ScriptedResponse(value="getUnitClass=true&attendeeID=" + ATTENDEE_A),
            ),
        ),
        AcquisitionObservation(
            result=(
                ("form", (("attendeeID", ATTENDEE_A), ("getUnitClass", "true"))),
                ("is_schedule_response", False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-RESP-003",
            "ACQ-RESP",
            "wrong-method",
            "form",
            "A getUnitClass value other than 'true' (case-insensitively) is not the schedule "
            "response even at the right URL.",
            "scout_schedule_cli.is_schedule_response line 362 value guard",
        ),
        NAME_A,
        AJAX_URL,
        (_sched(ATTENDEE_A, "getUnitClass=false&attendeeID=" + ATTENDEE_A),),
        AcquisitionObservation(
            result=(
                ("form", (("attendeeID", ATTENDEE_A), ("getUnitClass", "false"))),
                ("is_schedule_response", False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-RESP-004",
            "ACQ-RESP",
            "wrong-body",
            "form",
            "A form body missing getUnitClass entirely defaults to an empty string, which fails "
            "the schedule-response check.",
            "scout_schedule_cli.is_schedule_response line 362 .get default",
        ),
        NAME_A,
        AJAX_URL,
        (_sched(ATTENDEE_A, "foo=bar"),),
        AcquisitionObservation(
            result=(("form", (("foo", "bar"),)), ("is_schedule_response", False))
        ),
    ),
)

_ID_CASES: tuple[AcquisitionCase, ...] = (
    AcquisitionCase(
        _meta(
            "ACQ-ID-001",
            "ACQ-ID",
            "present",
            "form",
            "A present attendeeID key parses to its value.",
            "scout_schedule_cli.form_values lines 353-355",
        ),
        NAME_A,
        URL_A,
        (_sched(ATTENDEE_A, "attendeeID=" + ATTENDEE_A),),
        AcquisitionObservation(
            result=(("form", (("attendeeID", ATTENDEE_A),)), ("is_schedule_response", False))
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-ID-002",
            "ACQ-ID",
            "absent",
            "form",
            "A form body with no attendeeID key at all yields an empty parsed mapping.",
            "scout_schedule_cli.form_values parse_qs over a key-less body",
        ),
        NAME_A,
        URL_A,
        (_sched("", "foo=bar"),),
        AcquisitionObservation(result=(("form", (("foo", "bar"),)), ("is_schedule_response", False))),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-ID-003",
            "ACQ-ID",
            "blank",
            "form",
            "A blank attendeeID value is kept (keep_blank_values=True) rather than dropped.",
            "scout_schedule_cli.form_values line 354 keep_blank_values=True",
        ),
        NAME_A,
        URL_A,
        (_sched("", "attendeeID="),),
        AcquisitionObservation(
            result=(("form", (("attendeeID", ""),)), ("is_schedule_response", False))
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-ID-004",
            "ACQ-ID",
            "repeated-last-wins",
            "form",
            "A repeated attendeeID key resolves to the LAST value, not the first.",
            "scout_schedule_cli.form_values line 355 values[-1]",
        ),
        NAME_A,
        URL_A,
        (_sched("", "attendeeID=111&attendeeID=222"),),
        AcquisitionObservation(
            result=(("form", (("attendeeID", "222"),)), ("is_schedule_response", False))
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# ACQ-SCHED: the schedule payload's data-array shapes, driven through the real process_scout.
# --------------------------------------------------------------------------------------------
_SCHED_CASES: tuple[AcquisitionCase, ...] = (
    AcquisitionCase(
        _meta(
            "ACQ-SCHED-001",
            "ACQ-SCHED",
            "empty-data",
            "process",
            "An explicit empty data array yields zero classes and no requirement calls at all.",
            "scout_schedule_cli.process_scout line 538 schedule_rows loop over []",
        ),
        NAME_A,
        URL_A,
        (_sched(ATTENDEE_A, _schedule_payload(())),),
        AcquisitionObservation(result=(("attendee_id", ATTENDEE_A),)),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-SCHED-002",
            "ACQ-SCHED",
            "one-class",
            "process",
            "A single scheduled class produces one ClassRecord and one requirement round trip.",
            "scout_schedule_cli.process_scout lines 554-596",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("req", CLASS_A, "#1", False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-SCHED-003",
            "ACQ-SCHED",
            "multiple-classes",
            "process",
            "Two distinct scheduled classes each get their own ClassRecord and requirement "
            "round trip, in schedule order.",
            "scout_schedule_cli.process_scout line 554 for item in schedule_rows",
        ),
        NAME_A,
        URL_A,
        (
            _sched(
                ATTENDEE_A,
                _schedule_payload(
                    (_class_row(CLASS_A, "26MB1"), _class_row(CLASS_B, "26MB2", name="Fire Safety"))
                ),
            ),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
            _req(ATTENDEE_A, CLASS_B, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("class", "26MB2", CLASS_B, True, False),
                ("req", CLASS_A, "#1", False),
                ("req", CLASS_B, "#1", False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-SCHED-004",
            "ACQ-SCHED",
            "failed-status",
            "process",
            "A schedule payload with status.status != 1 raises before any class row is read, "
            "producing zero classes and one bounded error.",
            "scout_schedule_cli.process_scout lines 535-536",
        ),
        NAME_A,
        URL_A,
        (_sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),), status=0)),),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("error", "Schedule API returned failure: {'status': 0}"),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-SCHED-005",
            "ACQ-SCHED",
            "missing-data",
            "process",
            "A schedule payload with no 'data' key at all falls back to an empty list rather "
            "than raising.",
            "scout_schedule_cli.process_scout line 538 .get('data') or []",
        ),
        NAME_A,
        URL_A,
        (_sched(ATTENDEE_A, {"status": {"status": 1}}),),
        AcquisitionObservation(result=(("attendee_id", ATTENDEE_A),)),
    ),
)


# --------------------------------------------------------------------------------------------
# ACQ-DEDUP: the classP4ID dedup/regression-guard loop.
# --------------------------------------------------------------------------------------------
_DEDUP_CASES: tuple[AcquisitionCase, ...] = (
    AcquisitionCase(
        _meta(
            "ACQ-DEDUP-001",
            "ACQ-DEDUP",
            "unique-ids",
            "process",
            "Two rows with distinct classP4IDs are both kept -- there is nothing to dedupe.",
            "scout_schedule_cli.process_scout lines 541-549",
        ),
        NAME_A,
        URL_A,
        (
            _sched(
                ATTENDEE_A,
                _schedule_payload((_class_row(CLASS_A), _class_row(CLASS_B, "26MB2"))),
            ),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
            _req(ATTENDEE_A, CLASS_B, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("class", "26MB2", CLASS_B, True, False),
                ("req", CLASS_A, "#1", False),
                ("req", CLASS_B, "#1", False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-DEDUP-002",
            "ACQ-DEDUP",
            "missing-ids",
            "process",
            "Two rows that both omit classP4ID are each treated as their own class (a synthetic "
            "__no_id_N key), not merged together.",
            "scout_schedule_cli.process_scout lines 542-545",
        ),
        NAME_A,
        URL_A,
        (
            _sched(
                ATTENDEE_A,
                _schedule_payload((_class_row(""), _class_row("", "26MB2", name="Fire Safety"))),
            ),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", "", True, False),
                ("class", "26MB2", "", True, False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-DEDUP-003",
            "ACQ-DEDUP",
            "incomplete-to-complete",
            "process",
            "When a later duplicate for the same classP4ID is CLASS_COMPLETED and the earlier "
            "one was not, the later (completed) row replaces it.",
            "scout_schedule_cli.process_scout line 550 prefer-completed replace",
        ),
        NAME_A,
        URL_A,
        (
            _sched(
                ATTENDEE_A,
                _schedule_payload(
                    (
                        _class_row(CLASS_A, completed="0"),
                        _class_row(CLASS_A, completed="1"),
                    )
                ),
            ),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, True),
                ("req", CLASS_A, "#1", False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-DEDUP-004",
            "ACQ-DEDUP",
            "complete-to-incomplete",
            "process",
            "When an earlier duplicate is already CLASS_COMPLETED, a later not-completed "
            "duplicate for the same classP4ID does NOT regress it -- the first (completed) row "
            "wins.",
            "scout_schedule_cli.process_scout line 550 guard: only replace when new is complete "
            "and old is not",
        ),
        NAME_A,
        URL_A,
        (
            _sched(
                ATTENDEE_A,
                _schedule_payload(
                    (
                        _class_row(CLASS_A, completed="1"),
                        _class_row(CLASS_A, completed="0"),
                    )
                ),
            ),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, True),
                ("req", CLASS_A, "#1", False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-DEDUP-005",
            "ACQ-DEDUP",
            "equal-duplicate",
            "process",
            "Two duplicates for the same classP4ID with the same (not-completed) status keep "
            "only the first-seen row.",
            "scout_schedule_cli.process_scout lines 547-551 elif chain, both branches false",
        ),
        NAME_A,
        URL_A,
        (
            _sched(
                ATTENDEE_A,
                _schedule_payload(
                    (
                        _class_row(CLASS_A, completed="0"),
                        _class_row(CLASS_A, completed="0"),
                    )
                ),
            ),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("req", CLASS_A, "#1", False),
            )
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# ACQ-HASREQ: whether HAS_REQ gates the requirement fetch. It does NOT -- only a blank classP4ID
# does. ACQ-HASREQ-002 pins that surprising current behavior as intentional-change.
# --------------------------------------------------------------------------------------------
_HASREQ_CASES: tuple[AcquisitionCase, ...] = (
    AcquisitionCase(
        _meta(
            "ACQ-HASREQ-001",
            "ACQ-HASREQ",
            "has-req-1",
            "process",
            "HAS_REQ=1 with a non-blank classP4ID fetches requirements, as expected.",
            "scout_schedule_cli.process_scout lines 573-582",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A, has_req="1"),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("req", CLASS_A, "#1", False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-HASREQ-002",
            "ACQ-HASREQ",
            "has-req-0",
            "process",
            "HAS_REQ=0 does NOT skip the requirement fetch: process_scout only gates on a "
            "non-blank classP4ID (line 573), never on HAS_REQ, so a requirement request is "
            "still issued for a class the schedule marked as having none.",
            "scout_schedule_cli.process_scout lines 567,573-582 -- has_requirements is stored "
            "on ClassRecord but never read before the requirement fetch",
            classification=Classification.INTENTIONAL_CHANGE,
            target_owner="Slice 2",
            target_observation="Slice 2 will skip the requirement request entirely when "
            "HAS_REQ='0', instead of issuing it and relying on the response to be empty.",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A, has_req="0"),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, False, False),
                ("req", CLASS_A, "#1", False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-HASREQ-003",
            "ACQ-HASREQ",
            "blank-class-id",
            "process",
            "A blank classP4ID skips the requirement fetch entirely via the explicit 'continue' "
            "guard, regardless of HAS_REQ.",
            "scout_schedule_cli.process_scout lines 573-574",
        ),
        NAME_A,
        URL_A,
        (_sched(ATTENDEE_A, _schedule_payload((_class_row("", has_req="1"),))),),
        AcquisitionObservation(
            result=(("attendee_id", ATTENDEE_A), ("class", "26MB1", "", True, False))
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# ACQ-REQ: the requirement payload's data-array shapes.
# --------------------------------------------------------------------------------------------
_REQ_CASES: tuple[AcquisitionCase, ...] = (
    AcquisitionCase(
        _meta(
            "ACQ-REQ-001",
            "ACQ-REQ",
            "success",
            "process",
            "A well-formed requirement row builds one RequirementRecord with every field "
            "carried through.",
            "scout_schedule_cli.process_scout lines 605-622",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("req", CLASS_A, "#1", False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-REQ-002",
            "ACQ-REQ",
            "failed-status",
            "process",
            "A requirement payload with status.status != 1 adds one bounded error and no "
            "requirement rows, without raising.",
            "scout_schedule_cli.process_scout lines 598-603",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload(status=0)),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("error", "Chess: requirement API returned failure: {'status': 0}"),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-REQ-003",
            "ACQ-REQ",
            "empty-data",
            "process",
            "An empty requirement data array yields zero RequirementRecords and no error.",
            "scout_schedule_cli.process_scout line 605 for req in [] ",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload(())),
        ),
        AcquisitionObservation(
            result=(("attendee_id", ATTENDEE_A), ("class", "26MB1", CLASS_A, True, False))
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-REQ-004",
            "ACQ-REQ",
            "missing-fields",
            "process",
            "A requirement row missing every optional field is silently coerced to blank "
            "strings and false flags (str(x.get(k) or '') / truthy(None) is False) rather than "
            "being rejected.",
            "scout_schedule_cli.process_scout lines 605-622 str(...or '') / truthy(...) coercion",
            classification=Classification.INTENTIONAL_CHANGE,
            target_owner="Slice 2",
            target_observation="Slice 2 will validate requirement rows against a schema and "
            "flag/reject rows missing required fields instead of silently coercing them to "
            "blank strings and false flags.",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(
                ATTENDEE_A,
                CLASS_A,
                _requirement_payload(({"MERIT_BADGE_NAME": "Chess"},)),
            ),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("req", CLASS_A, "", False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-REQ-005",
            "ACQ-REQ",
            "unknown-fields",
            "process",
            "Extra unrecognized keys on a requirement row are silently ignored -- the record "
            "reads only the named keys it knows about.",
            "scout_schedule_cli.process_scout lines 605-622 only named .get() reads",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(
                ATTENDEE_A,
                CLASS_A,
                _requirement_payload((_req_row(SOME_FUTURE_FIELD="unused"),)),
            ),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("req", CLASS_A, "#1", False),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-REQ-006",
            "ACQ-REQ",
            "non-list-data",
            "process",
            "A non-list, non-falsey 'data' value (an int) is NOT treated as empty by "
            "'or []' -- iterating it raises, which escapes both loops uncaught and is only "
            "caught by process_scout's outer handler, aborting all further classes.",
            "scout_schedule_cli.process_scout line 605 for req in (42 or [])",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(ATTENDEE_A, CLASS_A, {"status": {"status": 1}, "data": 42}),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("error", "'int' object is not iterable"),
            )
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# ACQ-RETRY: the fixed range(1, 4) retry loop and its 500*attempt backoff.
# --------------------------------------------------------------------------------------------
_RETRY_CASES: tuple[AcquisitionCase, ...] = (
    AcquisitionCase(
        _meta(
            "ACQ-RETRY-001",
            "ACQ-RETRY",
            "immediate-success",
            "process",
            "A requirement request that succeeds on the first attempt never waits at all.",
            "scout_schedule_cli.process_scout lines 578-586 break on success",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("req", CLASS_A, "#1", False),
            ),
            waits_ms=(),
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-RETRY-002",
            "ACQ-RETRY",
            "two-failures-then-success",
            "process",
            "Two transient failures wait 500ms then 1000ms (500*attempt) before the third "
            "attempt succeeds.",
            "scout_schedule_cli.process_scout lines 578-586",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req_fail(ATTENDEE_A, CLASS_A),
            _wait(500),
            _req_fail(ATTENDEE_A, CLASS_A),
            _wait(1000),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("req", CLASS_A, "#1", False),
            ),
            waits_ms=(500, 1000),
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-RETRY-003",
            "ACQ-RETRY",
            "three-failures",
            "process",
            "All three attempts fail: the retry loop still waits after the THIRD (terminal) "
            "failure -- 500, 1000, then 1500ms -- even though no fourth attempt follows, "
            "before giving up and recording one bounded error.",
            "scout_schedule_cli.process_scout lines 578-586 range(1,4), wait runs "
            "unconditionally inside the except branch",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req_fail(ATTENDEE_A, CLASS_A),
            _wait(500),
            _req_fail(ATTENDEE_A, CLASS_A),
            _wait(1000),
            _req_fail(ATTENDEE_A, CLASS_A),
            _wait(1500),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("error", "Chess: requirement request failed: synthetic timeout"),
            ),
            waits_ms=(500, 1000, 1500),
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# ACQ-DELAY: the args.request_delay_ms gap after each class's requirement round trip.
# --------------------------------------------------------------------------------------------
_DELAY_CASES: tuple[AcquisitionCase, ...] = (
    AcquisitionCase(
        _meta(
            "ACQ-DELAY-001",
            "ACQ-DELAY",
            "zero-delay",
            "process",
            "request_delay_ms=0 skips the inter-class wait entirely (the guard is > 0, not "
            ">= 0).",
            "scout_schedule_cli.process_scout line 624",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("req", CLASS_A, "#1", False),
            ),
            waits_ms=(),
        ),
        request_delay_ms=0,
    ),
    AcquisitionCase(
        _meta(
            "ACQ-DELAY-002",
            "ACQ-DELAY",
            "positive-delay",
            "process",
            "A positive request_delay_ms waits exactly that many milliseconds after the "
            "class's requirement round trip.",
            "scout_schedule_cli.process_scout lines 624-625",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
            _wait(250),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("req", CLASS_A, "#1", False),
            ),
            waits_ms=(250,),
        ),
        request_delay_ms=250,
    ),
)


# --------------------------------------------------------------------------------------------
# ACQ-RAW: raw/ JSON audit files, and distinct filenames for same-named attendees.
# --------------------------------------------------------------------------------------------
_RAW_CASES: tuple[AcquisitionCase, ...] = (
    AcquisitionCase(
        _meta(
            "ACQ-RAW-001",
            "ACQ-RAW",
            "schedule-file",
            "raw",
            "A successful schedule fetch writes the untouched schedule JSON payload to "
            "raw/<slug>-<uuid>-schedule.json.",
            "scout_schedule_cli.process_scout lines 528-533",
            surface_id="acq-raw-filename",
        ),
        NAME_A,
        URL_A,
        (_sched(ATTENDEE_A, _schedule_payload((_class_row(""),))),),
        AcquisitionObservation(
            result=(("attendee_id", ATTENDEE_A), ("class", "26MB1", "", True, False)),
            relative_files=("raw/avery-example-<uuid>-schedule.json",),
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-RAW-002",
            "ACQ-RAW",
            "requirement-file",
            "raw",
            "A successful requirement fetch writes the untouched requirement JSON payload to "
            "raw/<slug>-<uuid>-<class-number-slug>-requirements.json.",
            "scout_schedule_cli.process_scout lines 594-596",
            surface_id="acq-raw-filename",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("req", CLASS_A, "#1", False),
            ),
            relative_files=(
                "raw/avery-example-<uuid>-26mb1-requirements.json",
                "raw/avery-example-<uuid>-schedule.json",
            ),
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-RAW-003",
            "ACQ-RAW",
            "distinct-uuid-filenames",
            "raw",
            "Two attendees who share the same printed name still get two distinct raw "
            "filenames, because the UUID segment is keyed on attendee_id, not on name.",
            "scout_schedule_cli.RunIdentity.output_id lines 66-71 keyed on attendee.value",
            surface_id="acq-raw-filename",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(""),))),
            _sched(ATTENDEE_B, _schedule_payload((_class_row(""),))),
        ),
        AcquisitionObservation(result=(("distinct", True),)),
    ),
)


# --------------------------------------------------------------------------------------------
# ACQ-CLEAN: context.close() runs on every path (success, schedule exception, terminal retry
# failure) because it lives in a `finally`.
# --------------------------------------------------------------------------------------------
_CLEAN_CASES: tuple[AcquisitionCase, ...] = (
    AcquisitionCase(
        _meta(
            "ACQ-CLEAN-001",
            "ACQ-CLEAN",
            "success",
            "process",
            "On a clean success the browser context is closed and the whole script is "
            "consumed.",
            "scout_schedule_cli.process_scout lines 629-630 finally: await context.close()",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("req", CLASS_A, "#1", False),
            ),
            closed=True,
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-CLEAN-002",
            "ACQ-CLEAN",
            "schedule-exception",
            "process",
            "Even when the schedule fetch raises (a failed API status), the finally clause "
            "still closes the browser context -- the batch loop in async_main can safely move "
            "on to the next scout.",
            "scout_schedule_cli.process_scout lines 535-536 raise then 629-630 finally close; "
            "async_main lines 1820-1835 continues the per-scout loop regardless of errors",
        ),
        NAME_A,
        URL_A,
        (_sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),), status=0)),),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("error", "Schedule API returned failure: {'status': 0}"),
            ),
            closed=True,
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-CLEAN-003",
            "ACQ-CLEAN",
            "terminal-requirement-failure",
            "process",
            "Even when every requirement retry is exhausted, the finally clause still closes "
            "the browser context -- one scout's requirement failure never leaks an open "
            "context into the next scout in async_main's per-scout loop.",
            "scout_schedule_cli.process_scout lines 588-592 error recorded, continue; then "
            "629-630 finally close; async_main lines 1820-1835 per-scout loop",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req_fail(ATTENDEE_A, CLASS_A),
            _wait(500),
            _req_fail(ATTENDEE_A, CLASS_A),
            _wait(1000),
            _req_fail(ATTENDEE_A, CLASS_A),
            _wait(1500),
        ),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, True, False),
                ("error", "Chess: requirement request failed: synthetic timeout"),
            ),
            waits_ms=(500, 1000, 1500),
            closed=True,
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# ACQ-ASSET: the dead-asset route guard, installed only when allow_dead_assets is False.
# --------------------------------------------------------------------------------------------
_ASSET_CASES: tuple[AcquisitionCase, ...] = (
    AcquisitionCase(
        _meta(
            "ACQ-ASSET-001",
            "ACQ-ASSET",
            "dead-asset-aborted",
            "asset",
            "With the default allow_dead_assets=False, a request to a known dead-asset host is "
            "aborted while a request to any other host continues.",
            "scout_schedule_cli.process_scout lines 499-509 block_dead_assets",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(("route_registered", True), ("dead_aborted", True), ("normal_continued", True))
        ),
        allow_dead_assets=False,
    ),
    AcquisitionCase(
        _meta(
            "ACQ-ASSET-002",
            "ACQ-ASSET",
            "allowed-dead-asset",
            "asset",
            "With --allow-dead-assets, process_scout never installs the route guard at all, so "
            "every request (including the known dead-asset hosts) is left to Playwright's "
            "default handling.",
            "scout_schedule_cli.process_scout line 499 if not args.allow_dead_assets guard",
        ),
        NAME_A,
        URL_A,
        (
            _sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A),))),
            _req(ATTENDEE_A, CLASS_A, _requirement_payload((_req_row(),))),
        ),
        AcquisitionObservation(
            result=(("route_registered", False), ("dead_aborted", None), ("normal_continued", None))
        ),
        allow_dead_assets=True,
    ),
)


# --------------------------------------------------------------------------------------------
# ACQ-IDENTITY: attendee-id validation and the per-run UUIDv4 identity map.
# --------------------------------------------------------------------------------------------
_IDENTITY_CASES: tuple[AcquisitionCase, ...] = (
    AcquisitionCase(
        _meta(
            "ACQ-IDENTITY-001",
            "ACQ-IDENTITY",
            "missing-id-fails-closed",
            "process",
            "A schedule request whose post_data carries no attendeeID raises before "
            "result.attendee_id is ever set and before any raw file is written -- there is no "
            "partial identity.",
            "scout_schedule_cli.process_scout lines 519-524",
        ),
        NAME_A,
        URL_A,
        (_sched("", _schedule_payload((_class_row(CLASS_A),))),),
        AcquisitionObservation(
            result=(
                ("attendee_id", ""),
                ("error", "The schedule request did not contain attendeeID"),
            )
        ),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-IDENTITY-002",
            "ACQ-IDENTITY",
            "uuidv4-stable",
            "identity",
            "RunIdentity.output_id returns a well-formed UUIDv4 and is stable across repeated "
            "calls for the same attendee within one run.",
            "scout_schedule_cli.RunIdentity.output_id lines 66-71",
        ),
        NAME_A,
        URL_A,
        (),
        AcquisitionObservation(result=(("stable", True), ("uuidv4", True))),
    ),
    AcquisitionCase(
        _meta(
            "ACQ-IDENTITY-003",
            "ACQ-IDENTITY",
            "runs-unlinkable",
            "identity",
            "Two separate RunIdentity instances (two separate runs) assign different UUIDs to "
            "the same attendee, so raw filenames from different runs cannot be linked by UUID "
            "alone.",
            "scout_schedule_cli.RunIdentity._by_attendee is instance-scoped, not global",
        ),
        NAME_A,
        URL_A,
        (),
        AcquisitionObservation(result=(("unlinkable", True),)),
    ),
)


ACQUISITION_CASES: tuple[AcquisitionCase, ...] = (
    *_RESP_CASES,
    *_ID_CASES,
    *_SCHED_CASES,
    *_DEDUP_CASES,
    *_HASREQ_CASES,
    *_REQ_CASES,
    *_RETRY_CASES,
    *_DELAY_CASES,
    *_RAW_CASES,
    *_CLEAN_CASES,
    *_ASSET_CASES,
    *_IDENTITY_CASES,
)


# --------------------------------------------------------------------------------------------
# ACQ-BREAKER / ACQ-RESUME: new-acceptance placeholders owned by Slice 2. Nothing in the
# current branch implements a circuit breaker or a resumable checkpoint, so these carry no
# execution context (contexts=()) -- only complete metadata proving the row is accounted for.
# --------------------------------------------------------------------------------------------
NEW_ACCEPTANCE_ACQUISITION_METADATA: tuple[CaseMetadata, ...] = (
    CaseMetadata(
        case_id="ACQ-BREAKER-001",
        axis_id="ACQ-BREAKER",
        member="below-threshold",
        domain=Domain.ACQUISITION,
        classification=Classification.NEW_ACCEPTANCE,
        evidence=EvidenceKind.PROPERTY_BOUNDARY,
        rationale="The current acquisition loop has no failure-count breaker at all -- every "
        "scout is attempted regardless of how many prior scouts failed.",
        contexts=(),
        evidence_reference="scout_schedule_cli.async_main lines 1799-1873 (no breaker state)",
        target_owner="Slice 2",
        target_observation="Slice 2 will track consecutive failures and stay closed (keep "
        "attempting scouts) while the count is below a configured threshold.",
    ),
    CaseMetadata(
        case_id="ACQ-BREAKER-002",
        axis_id="ACQ-BREAKER",
        member="threshold-opens",
        domain=Domain.ACQUISITION,
        classification=Classification.NEW_ACCEPTANCE,
        evidence=EvidenceKind.PROPERTY_BOUNDARY,
        rationale="The current acquisition loop cannot open a circuit -- there is no concept "
        "of consecutive-failure count to compare against a threshold.",
        contexts=(),
        evidence_reference="scout_schedule_cli.async_main lines 1799-1873 (no breaker state)",
        target_owner="Slice 2",
        target_observation="Slice 2 will open the circuit and stop attempting further scouts "
        "once consecutive failures reach the configured threshold.",
    ),
    CaseMetadata(
        case_id="ACQ-BREAKER-003",
        axis_id="ACQ-BREAKER",
        member="recovery-resets",
        domain=Domain.ACQUISITION,
        classification=Classification.NEW_ACCEPTANCE,
        evidence=EvidenceKind.PROPERTY_BOUNDARY,
        rationale="The current acquisition loop has no recovery/half-open state to reset -- "
        "every scout's success or failure is independent of the ones before it.",
        contexts=(),
        evidence_reference="scout_schedule_cli.async_main lines 1799-1873 (no breaker state)",
        target_owner="Slice 2",
        target_observation="Slice 2 will reset the consecutive-failure count to zero after a "
        "successful scout, so a transient run of failures does not permanently trip the "
        "breaker.",
    ),
    CaseMetadata(
        case_id="ACQ-RESUME-001",
        axis_id="ACQ-RESUME",
        member="new-checkpoint",
        domain=Domain.ACQUISITION,
        classification=Classification.NEW_ACCEPTANCE,
        evidence=EvidenceKind.PROPERTY_BOUNDARY,
        rationale="The current acquisition loop has no on-disk checkpoint of any kind -- a run "
        "that is interrupted leaves nothing behind to resume from.",
        contexts=(),
        evidence_reference="scout_schedule_cli.async_main lines 1799-1873 (no checkpoint I/O)",
        target_owner="Slice 2",
        target_observation="Slice 2 will create a fresh on-disk checkpoint file at the start "
        "of a run with no prior checkpoint.",
    ),
    CaseMetadata(
        case_id="ACQ-RESUME-002",
        axis_id="ACQ-RESUME",
        member="completed-not-repeated",
        domain=Domain.ACQUISITION,
        classification=Classification.NEW_ACCEPTANCE,
        evidence=EvidenceKind.PROPERTY_BOUNDARY,
        rationale="The current acquisition loop always reprocesses every scout in the input "
        "file from the top -- there is no notion of 'already completed' to skip.",
        contexts=(),
        evidence_reference="scout_schedule_cli.async_main lines 1820-1834 unconditional "
        "enumerate(scouts, start=1)",
        target_owner="Slice 2",
        target_observation="Slice 2 will skip scouts the checkpoint already recorded as "
        "completed when resuming an interrupted run.",
    ),
    CaseMetadata(
        case_id="ACQ-RESUME-003",
        axis_id="ACQ-RESUME",
        member="uuid-survives-resume",
        domain=Domain.ACQUISITION,
        classification=Classification.NEW_ACCEPTANCE,
        evidence=EvidenceKind.PROPERTY_BOUNDARY,
        rationale="RunIdentity is created fresh in async_main (line 1814) every time it runs, "
        "so an attendee's output UUID does not currently survive a process restart.",
        contexts=(),
        evidence_reference="scout_schedule_cli.async_main line 1814 run_identity = RunIdentity()",
        target_owner="Slice 2",
        target_observation="Slice 2 will persist the attendee-to-output-UUID map in the "
        "checkpoint so a resumed run reuses the same output UUID for each attendee.",
    ),
    CaseMetadata(
        case_id="ACQ-RESUME-004",
        axis_id="ACQ-RESUME",
        member="corrupt-checkpoint-fails-closed",
        domain=Domain.ACQUISITION,
        classification=Classification.NEW_ACCEPTANCE,
        evidence=EvidenceKind.PROPERTY_BOUNDARY,
        rationale="There is no checkpoint file format yet, so there is nothing that could be "
        "corrupt or version-mismatched today.",
        contexts=(),
        evidence_reference="scout_schedule_cli.async_main lines 1799-1873 (no checkpoint I/O)",
        target_owner="Slice 2",
        target_observation="Slice 2 will refuse to resume from a corrupt or version-mismatched "
        "checkpoint file, failing closed (starting a fresh run only on explicit request) "
        "rather than guessing at partial state.",
    ),
)


# --------------------------------------------------------------------------------------------
# FAKE-STRICT: the strict-fake misuse contract itself (tests/fakes/*). Each row names one
# scenario tests/fakes/test_strict_fakes.py drives to prove the fake fails loudly and exactly
# as designed. There is no AcquisitionCase shape for these -- the test module dispatches on
# case_id directly.
# --------------------------------------------------------------------------------------------
FAKE_STRICT_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "FAKE-STRICT-001",
        "FAKE-STRICT",
        "wrong-attendee-id",
        "misuse",
        "Calling the requirement fake with the wrong attendee_id raises UnexpectedFakeCall "
        "instead of silently returning the scripted response.",
        "tests/fakes/acquisition.py StrictScript.next_requirement id comparison",
    ),
    _meta(
        "FAKE-STRICT-002",
        "FAKE-STRICT",
        "wrong-class-id",
        "misuse",
        "Calling the requirement fake with the wrong class_id raises UnexpectedFakeCall.",
        "tests/fakes/acquisition.py StrictScript.next_requirement id comparison",
    ),
    _meta(
        "FAKE-STRICT-003",
        "FAKE-STRICT",
        "wrong-order",
        "misuse",
        "Calling the fake out of its scripted order (a wait before the schedule call) raises "
        "UnexpectedFakeCall rather than silently reordering the script.",
        "tests/fakes/acquisition.py StrictScript._pop operation-type comparison",
    ),
    _meta(
        "FAKE-STRICT-004",
        "FAKE-STRICT",
        "wrong-delay",
        "misuse",
        "Calling wait_for_timeout with a millisecond value that does not match the scripted "
        "wait raises UnexpectedFakeCall.",
        "tests/fakes/acquisition.py StrictScript.next_wait delay comparison",
    ),
    _meta(
        "FAKE-STRICT-005",
        "FAKE-STRICT",
        "unexpected-retry",
        "misuse",
        "A retry attempt the script did not anticipate (the script only scripted one "
        "requirement attempt but the code under test issues a second) raises "
        "UnexpectedFakeCall.",
        "tests/fakes/acquisition.py StrictScript._pop empty-deque guard",
    ),
    _meta(
        "FAKE-STRICT-006",
        "FAKE-STRICT",
        "extra-call",
        "misuse",
        "Any call made after the script is already fully consumed raises UnexpectedFakeCall.",
        "tests/fakes/acquisition.py StrictScript._pop empty-deque guard",
    ),
    _meta(
        "FAKE-STRICT-007",
        "FAKE-STRICT",
        "unconsumed-response",
        "misuse",
        "A scripted response the code under test never asked for is caught by "
        "assert_consumed() raising UnconsumedFakeResponses.",
        "tests/fakes/acquisition.py StrictScript.assert_consumed",
    ),
)


# --------------------------------------------------------------------------------------------
# BROWSER-LOCAL / BROWSER-EGRESS: the guarded browser harness (tests/harnesses/browser.py) and
# its loopback-only fake service, driven with a real Playwright browser.
# --------------------------------------------------------------------------------------------
BROWSER_LOCAL_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "BROWSER-LOCAL-001",
        "BROWSER-LOCAL",
        "capture-schedule-post",
        "browser",
        "A real Chromium page posting to the loopback fake service's schedule endpoint is "
        "observed by the guarded context without being blocked.",
        "tests/harnesses/browser.py guarded_context + loopback fake service",
        lane=Lane.BROWSER,
    ),
    _meta(
        "BROWSER-LOCAL-002",
        "BROWSER-LOCAL",
        "serve-requirement-json",
        "browser",
        "The loopback fake service serves deterministic requirement JSON that a real page can "
        "fetch() and read back.",
        "tests/harnesses/browser.py loopback fake service requirement route",
        lane=Lane.BROWSER,
    ),
    _meta(
        "BROWSER-LOCAL-003",
        "BROWSER-LOCAL",
        "real-interception",
        "browser",
        "The guarded context's request listener actually observes a real Playwright request "
        "event for a loopback navigation, proving the guard is wired to the real browser and "
        "not a no-op.",
        "tests/harnesses/browser.py install_egress_guard request listener",
        lane=Lane.BROWSER,
    ),
    _meta(
        "BROWSER-LOCAL-004",
        "BROWSER-LOCAL",
        "full-local-success",
        "browser",
        "A full local acquisition round trip (navigate, capture the schedule POST, fetch a "
        "requirement) succeeds end to end against the loopback fake service with the guard "
        "installed.",
        "tests/harnesses/browser.py guarded_context + loopback fake service, full round trip",
        lane=Lane.BROWSER,
    ),
)

BROWSER_EGRESS_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "BROWSER-EGRESS-001",
        "BROWSER-EGRESS",
        "navigation",
        "browser",
        "A direct page.goto() to a non-loopback host is blocked by the guard's request "
        "listener before Playwright can complete it.",
        "tests/harnesses/browser.py assert_loopback + request guard",
        lane=Lane.BROWSER,
    ),
    _meta(
        "BROWSER-EGRESS-002",
        "BROWSER-EGRESS",
        "redirect",
        "browser",
        "A loopback response that redirects to a non-loopback host is blocked by the guard's "
        "route() handler: since Chromium never re-invokes route() for a navigation's "
        "redirected hop, the handler fetches the response itself with max_redirects=0, "
        "inspects the Location header before the browser ever sees it, and aborts in place if "
        "that target is non-loopback.",
        "tests/harnesses/browser.py install_egress_guard navigation-redirect route().fetch handling",
        lane=Lane.BROWSER,
    ),
    _meta(
        "BROWSER-EGRESS-003",
        "BROWSER-EGRESS",
        "frame",
        "browser",
        "A child frame (iframe) that navigates to a non-loopback host is blocked by the "
        "guard's frame-navigation listener.",
        "tests/harnesses/browser.py assert_loopback + frame guard",
        lane=Lane.BROWSER,
    ),
    _meta(
        "BROWSER-EGRESS-004",
        "BROWSER-EGRESS",
        "popup",
        "browser",
        "A popup window opened toward a non-loopback host is blocked by the guard's popup "
        "listener.",
        "tests/harnesses/browser.py assert_loopback + popup guard",
        lane=Lane.BROWSER,
    ),
    _meta(
        "BROWSER-EGRESS-005",
        "BROWSER-EGRESS",
        "worker-fetch",
        "browser",
        "An in-page fetch()/XHR (and a worker's network access) toward a non-loopback host is "
        "blocked by the guard's request listener the same as any other request.",
        "tests/harnesses/browser.py assert_loopback + request guard (fetch/XHR/worker)",
        lane=Lane.BROWSER,
    ),
    _meta(
        "BROWSER-EGRESS-006",
        "BROWSER-EGRESS",
        "websocket",
        "browser",
        "A WebSocket connection attempt toward a non-loopback host is blocked by the guard's "
        "WebSocket listener.",
        "tests/harnesses/browser.py assert_loopback + websocket guard",
        lane=Lane.BROWSER,
    ),
    _meta(
        "BROWSER-EGRESS-007",
        "BROWSER-EGRESS",
        "download",
        "browser",
        "A download triggered toward a non-loopback host is blocked before Chromium's download "
        "subsystem ever sees a response -- the same route() host check that blocks any other "
        "non-loopback request runs first, so page.on('download') never even fires for it; the "
        "dedicated page.on('download', ...) listener is verified directly (a unit-style proof, "
        "not a full real-Chromium download flow, since a genuinely reachable non-loopback "
        "download event is unconstructable once route() already blocks the underlying request).",
        "tests/harnesses/browser.py install_egress_guard _guard_page download listener",
        lane=Lane.BROWSER,
    ),
)


# --------------------------------------------------------------------------------------------
# NET-POLICY: the EXISTING scoutmb.network_policy.assert_egress_allowed boundary (Slice 1a).
# --------------------------------------------------------------------------------------------
NET_POLICY_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "NET-POLICY-001",
        "NET-POLICY",
        "loopback-allowed",
        "net-policy",
        "assert_egress_allowed returns None (no exception) for every loopback host name, with "
        "no environment opt-in required.",
        "src/scoutmb/network_policy.py lines 19-25 _LOOPBACK set",
    ),
    _meta(
        "NET-POLICY-002",
        "NET-POLICY",
        "non-loopback-denied",
        "net-policy",
        "assert_egress_allowed raises ExternalNetworkBlocked for a non-loopback host when the "
        "SCOUTMB_ALLOW_LIVE_SERVICE opt-in is unset.",
        "src/scoutmb/network_policy.py lines 19-25",
    ),
    _meta(
        "NET-POLICY-003",
        "NET-POLICY",
        "opt-in-allowed",
        "net-policy",
        "With SCOUTMB_ALLOW_LIVE_SERVICE set, assert_egress_allowed allows a non-loopback "
        "service host -- but that environment opt-in is only ONE of the two parts real live "
        "tests require; they must also carry the 'live_service' pytest marker before "
        "pytest-socket itself will let the connection through.",
        "src/scoutmb/network_policy.py lines 19-25; tests/conftest.py pytest_runtest_setup "
        "live_service marker gate",
    ),
)


# --------------------------------------------------------------------------------------------
# NET-WIRE: new-acceptance placeholders owned by Slice 2. Nothing today calls
# assert_egress_allowed from an HTTP or Playwright gateway -- Slice 1a only shipped the
# boundary function itself (see NET-POLICY above), not its wiring.
# --------------------------------------------------------------------------------------------
NET_WIRE_METADATA: tuple[CaseMetadata, ...] = (
    CaseMetadata(
        case_id="NET-WIRE-001",
        axis_id="NET-WIRE",
        member="http-gateway-consults-policy",
        domain=Domain.ACQUISITION,
        classification=Classification.NEW_ACCEPTANCE,
        evidence=EvidenceKind.PROPERTY_BOUNDARY,
        rationale="No extracted HTTP gateway exists yet in this branch -- scout_schedule_cli "
        "issues its fetch() calls directly from in-page Playwright code, never through a "
        "gateway that could consult assert_egress_allowed.",
        contexts=(),
        evidence_reference="scout_schedule_cli.post_requirement lines 454-486 (no gateway "
        "seam)",
        target_owner="Slice 2",
        target_observation="Slice 2 will extract an HTTP gateway that calls "
        "assert_egress_allowed(host) before issuing any request.",
    ),
    CaseMetadata(
        case_id="NET-WIRE-002",
        axis_id="NET-WIRE",
        member="playwright-gateway-consults-policy",
        domain=Domain.ACQUISITION,
        classification=Classification.NEW_ACCEPTANCE,
        evidence=EvidenceKind.PROPERTY_BOUNDARY,
        rationale="No extracted Playwright navigation gateway exists yet -- "
        "navigate_and_trigger_schedule calls page.goto() directly, never through a gateway "
        "that could consult assert_egress_allowed.",
        contexts=(),
        evidence_reference="scout_schedule_cli.navigate_and_trigger_schedule lines 405-451 "
        "(no gateway seam)",
        target_owner="Slice 2",
        target_observation="Slice 2 will extract a Playwright navigation gateway that calls "
        "assert_egress_allowed(host) before any page.goto()/navigation.",
    ),
)


ALL_ACQUISITION_METADATA: tuple[CaseMetadata, ...] = (
    tuple(case.meta for case in ACQUISITION_CASES)
    + NEW_ACCEPTANCE_ACQUISITION_METADATA
    + FAKE_STRICT_METADATA
    + BROWSER_LOCAL_METADATA
    + BROWSER_EGRESS_METADATA
    + NET_POLICY_METADATA
    + NET_WIRE_METADATA
)
