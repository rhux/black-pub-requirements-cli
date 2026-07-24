"""Artifact/output-writer characterization catalog (Task 20).

Every row is ``preserve`` EXCEPT ``ART-NAME-007`` (``intentional-change``): legacy currently
follows a symlinked output root when publishing files (no realpath/containment check anywhere in
``atomic_write_text`` or ``write_outputs``); Slice 2's target is to reject that before
publication.

This module holds only frozen data -- it never imports ``scout_schedule_cli`` at module level.
The runner in ``tests/characterization/test_artifact_matrix.py`` performs the real import and
drives the real writers (``write_outputs``, ``write_html_report``, ``write_email_reports``,
``write_csv``, ``atomic_write_text``, ``attendee_filename_stem``, ``safe_slug``,
``json_for_html``) -- never mocked except at the exact filesystem seams ART-FAIL-* names
(``Path.open``/``os.fsync``/``os.replace``/``Path.unlink``), and never the serializers
(``json.dumps``/``csv.DictWriter``) or the writer functions themselves.

Case-only-filename-collision, Windows-reserved-name, and Unicode-normalization rows are PURE
simulated contract cases over strings/paths: they characterize what the current filename
sanitization/collision-detection LOGIC does with these inputs, not real OS-level filesystem
collision behavior (no actual case-insensitive or reserved-name filesystem is exercised).

Execution contexts (each case declares exactly one in ``meta.contexts``):

* ``schema`` -- ART-SCHEMA-*: drives ``write_outputs``/``write_html_report``/
  ``write_email_reports`` and reads the resulting files back byte-for-byte.
* ``html`` -- ART-HTML-*: drives the real ``json_for_html`` directly against a requirements
  payload carrying the sentinel/adversarial string, then ``json.loads`` the result back.
* ``email`` -- ART-EMAIL-*: drives ``write_email_reports`` against different scout-completion
  shapes.
* ``filename`` -- ART-NAME-*: drives ``safe_slug``/``attendee_filename_stem`` and, where
  containment is the point, a small real ``write_outputs`` call against a ``tmp_path`` root
  (including a real symlinked root for ART-NAME-007).
* ``formula`` -- ART-FORMULA-*: drives ``write_csv`` with a formula-injection-prefixed field and
  reads the raw CSV bytes back.
* ``atomic_fail`` -- ART-FAIL-*: drives ``atomic_write_text``/``write_outputs`` with a failure
  injected at one exact filesystem seam via ``unittest.mock.patch``, and inspects before/after
  file bytes, leftover temp files, and sibling files.

No test writes outside ``tmp_path`` and this module performs no real network I/O.

Each case declares exactly one execution context in ``meta.contexts`` and a matching real
expected value in ``expected_by_context`` (keyed by that same context id), mirroring the pattern
``requirement_cases.py`` uses for ``RequirementCase``. The runner in
``tests/characterization/test_artifact_matrix.py`` computes an ``observed`` value from the real
writer call and asserts ``observed == case.expected_by_context[context_id]`` -- one clean
equality per case, never several inline ad hoc assertions. Where one member's real behavior spans
several related facts (e.g. "file exists AND has this exact content AND no leftover temp file"),
the stored expected value is a small tuple capturing all of them together, with the tuple's shape
documented inline above the axis that uses it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tests.matrix.model import CaseMetadata, Classification, Domain, EvidenceKind


@dataclass(frozen=True, slots=True)
class ArtifactCase:
    meta: CaseMetadata
    input_rows: tuple[Mapping[str, object], ...]
    expected_by_context: Mapping[str, object]


def _meta(
    case_id: str,
    axis_id: str,
    member: str,
    context: str,
    rationale: str,
    evidence_reference: str,
    *,
    classification: Classification = Classification.PRESERVE,
    target_owner: str | None = None,
    target_observation: str | None = None,
) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id=axis_id,
        member=member,
        domain=Domain.ARTIFACT,
        classification=classification,
        evidence=EvidenceKind.CURRENT_BRANCH,
        rationale=rationale,
        contexts=(context,),
        evidence_reference=evidence_reference,
        target_owner=target_owner,
        target_observation=target_observation,
    )


# Synthetic identity used across every case in this catalog -- never real scout data.
SCOUT_NAME = "Avery Example"
ATTENDEE_ID = "90000001"
CLASS_P4_ID = "2000001"
QR_URL = "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_X"

_EVIDENCE_WRITE_OUTPUTS = "scout_schedule_cli.py:1721-1789 write_outputs"
_EVIDENCE_HTML_REPORT = "scout_schedule_cli.py:1060-1717 write_html_report"
_EVIDENCE_EMAIL = "scout_schedule_cli.py:989-1046 write_email_reports"
_EVIDENCE_JSON_FOR_HTML = "scout_schedule_cli.py:1048-1057 json_for_html"
_EVIDENCE_FILENAME = "scout_schedule_cli.py:635-646 safe_slug / attendee_filename_stem"
_EVIDENCE_WRITE_CSV = "scout_schedule_cli.py:663-669 write_csv"
_EVIDENCE_ATOMIC = "scout_schedule_cli.py:648-661 atomic_write_text"


def _class_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "scout_name": SCOUT_NAME,
        "attendee_id": ATTENDEE_ID,
        "class_number": "26MB1",
        "class_p4_id": CLASS_P4_ID,
        "class_name": "Chess",
        "days": "MoTuWeTh",
        "period_name": "A Block",
        "start_time": "09:00 AM",
        "start_time_24h": "09:00:00",
        "location": "Pavilion",
        "has_requirements": True,
        "class_completed": False,
        "raw_class_name": "MoTuWeTh - Chess - 26MB1 (Pavilion)",
    }
    row.update(overrides)
    return row


def _requirement_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "scout_name": SCOUT_NAME,
        "attendee_id": ATTENDEE_ID,
        "class_number": "26MB1",
        "class_p4_id": CLASS_P4_ID,
        "merit_badge_name": "Chess",
        "requirement_id": "r1",
        "requirement_type_id": "1",
        "requirement_number": "#1a",
        "description": "Show your work.",
        "completed_requirement": False,
        "completed_class": False,
        "requirement_on_event": True,
        "present_days": "MoTuWeTh",
    }
    row.update(overrides)
    return row


# ==============================================================================================
# ART-SCHEMA-001..008 -- every file write_outputs produces, plus the HTML report-data payload and
# the two email artifacts, each compared by ordered keys/headers, complete rows, encoding, and
# newline convention.
#
# expected_by_context["schema"] shape is per-member (mirrors what the runner's real writer call
# actually produces for that member):
#   scouts-json      -> the exact parsed scouts.json payload (a list of one ScoutResult dict).
#   classes-csv      -> (fieldnames tuple, row count, rows[0]["class_name"]).
#   requirements-csv -> (fieldnames tuple, row count, rows[0]["requirement_number"]).
#   errors-csv       -> (fieldnames list, rows list).
#   summary-json     -> (frozenset(summary keys), scouts_processed, classes, requirements,
#                        html_report, email_report_dir).
#   report-data      -> (no-placeholder-leftover bool, frozenset(payload keys),
#                        len(payload["classes"]), len(payload["requirements"])).
#   email-csv        -> (fieldnames tuple, row count, rows[0]["status"]).
#   email-text-html  -> (txt file count, html file count, txt starts with greeting bool,
#                        html contains doctype bool).
# ==============================================================================================
ARTIFACT_CASES_SCHEMA: tuple[ArtifactCase, ...] = (
    ArtifactCase(
        meta=_meta(
            "ART-SCHEMA-001",
            "ART-SCHEMA",
            "scouts-json",
            "schema",
            "scouts.json is a JSON array of {name, qr_url, attendee_id, classes, requirements, "
            "errors} nested dicts -- one entry per ScoutResult, written with indent=2 via "
            "atomic_write_text(..., encoding='utf-8').",
            _EVIDENCE_WRITE_OUTPUTS,
        ),
        input_rows=(_class_row(), _requirement_row()),
        expected_by_context={
            "schema": [
                {
                    "name": SCOUT_NAME,
                    "qr_url": QR_URL,
                    "attendee_id": ATTENDEE_ID,
                    "classes": [_class_row()],
                    "requirements": [_requirement_row()],
                    "errors": [],
                }
            ]
        },
    ),
    ArtifactCase(
        meta=_meta(
            "ART-SCHEMA-002",
            "ART-SCHEMA",
            "classes-csv",
            "schema",
            "classes.csv's header is exactly ClassRecord.__dataclass_fields__ in declaration "
            "order, one data row per ClassRecord, written via write_csv (utf-8-sig, CRLF from "
            "csv.DictWriter's default \\r\\n line terminator).",
            "scout_schedule_cli.py:82-95 ClassRecord; :663-669 write_csv",
        ),
        input_rows=(_class_row(),),
        expected_by_context={"schema": (tuple(_class_row()), 1, "Chess")},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-SCHEMA-003",
            "ART-SCHEMA",
            "requirements-csv",
            "schema",
            "requirements.csv's header is exactly RequirementRecord.__dataclass_fields__ in "
            "declaration order, one data row per RequirementRecord.",
            "scout_schedule_cli.py:99-112 RequirementRecord; :663-669 write_csv",
        ),
        input_rows=(_requirement_row(),),
        expected_by_context={"schema": (tuple(_requirement_row()), 1, "#1a")},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-SCHEMA-004",
            "ART-SCHEMA",
            "errors-csv",
            "schema",
            "errors.csv's header is exactly ['scout_name', 'attendee_id', 'error'], one row per "
            "ScoutResult.errors entry.",
            "scout_schedule_cli.py:1762-1768 error_rows/error_writer",
        ),
        input_rows=(),
        expected_by_context={
            "schema": (
                ["scout_name", "attendee_id", "error"],
                [{"scout_name": SCOUT_NAME, "attendee_id": ATTENDEE_ID, "error": "boom"}],
            )
        },
    ),
    ArtifactCase(
        meta=_meta(
            "ART-SCHEMA-005",
            "ART-SCHEMA",
            "summary-json",
            "schema",
            "summary.json has the exact key set {scouts_processed, scouts_with_errors, classes, "
            "requirements, generated_at_local, generated_at_iso, html_report, "
            "email_report_dir}.",
            "scout_schedule_cli.py:1780-1791 summary dict",
        ),
        input_rows=(_class_row(), _requirement_row()),
        expected_by_context={
            "schema": (
                frozenset(
                    {
                        "scouts_processed",
                        "scouts_with_errors",
                        "classes",
                        "requirements",
                        "generated_at_local",
                        "generated_at_iso",
                        "html_report",
                        "email_report_dir",
                    }
                ),
                1,
                1,
                1,
                "report.html",
                None,
            )
        },
    ),
    ArtifactCase(
        meta=_meta(
            "ART-SCHEMA-006",
            "ART-SCHEMA",
            "report-data",
            "schema",
            "The JSON embedded in the HTML report (inside <script id='report-data'>) has the "
            "exact key set {generated_at_local, generated_at_iso, run_id, scouts, classes, "
            "requirements, errors} and no residual __REPORT_DATA__ placeholder.",
            _EVIDENCE_HTML_REPORT,
        ),
        input_rows=(_class_row(), _requirement_row()),
        expected_by_context={
            "schema": (
                True,
                frozenset(
                    {
                        "generated_at_local",
                        "generated_at_iso",
                        "run_id",
                        "scouts",
                        "classes",
                        "requirements",
                        "errors",
                    }
                ),
                1,
                1,
            )
        },
    ),
    ArtifactCase(
        meta=_meta(
            "ART-SCHEMA-007",
            "ART-SCHEMA",
            "email-csv",
            "schema",
            "emails/missing_requirements.csv's header is exactly ['scout_name', 'attendee_id', "
            "'status', 'merit_badge_count', 'missing_requirement_count', 'subject', "
            "'body_text', 'body_html'], one row per scout regardless of status.",
            _EVIDENCE_EMAIL,
        ),
        input_rows=(_requirement_row(completed_requirement=False),),
        expected_by_context={
            "schema": (
                (
                    "scout_name",
                    "attendee_id",
                    "status",
                    "merit_badge_count",
                    "missing_requirement_count",
                    "subject",
                    "body_text",
                    "body_html",
                ),
                1,
                "missing_requirements",
            )
        },
    ),
    ArtifactCase(
        meta=_meta(
            "ART-SCHEMA-008",
            "ART-SCHEMA",
            "email-text-html",
            "schema",
            "For a scout with missing requirements, write_email_reports writes BOTH "
            "emails/<slug>.txt (utf-8, no BOM) and emails/<slug>.html (utf-8, no BOM) using the "
            "same attendee_filename_stem as the raw/ audit files.",
            _EVIDENCE_EMAIL,
        ),
        input_rows=(_requirement_row(completed_requirement=False),),
        expected_by_context={"schema": (1, 1, True, True)},
    ),
)


# ==============================================================================================
# ART-HTML-001..005 -- json_for_html's escaping contract (scout_schedule_cli.py:1048-1057):
# &, <, > become &/</>; U+2028/U+2029 become  / ; everything else
# (including non-ASCII) passes through literally because json.dumps is called with
# ensure_ascii=False. Every case's sentinel/adversarial string round-trips through
# json.loads(json_for_html(...)) to its ORIGINAL value even though the intermediate text is
# HTML/script-safe.
# expected_by_context["html"] is always this fixed 10-tuple (an element is None wherever the
# case's description doesn't contain the character that fact is about):
#   (script_tag_absent, escaped_lt, escaped_gt, escaped_amp, escaped_u2028, escaped_u2029,
#    literal_u2028_absent, literal_u2029_absent, non_ascii_literal_present, round_trip_matches)
# ==============================================================================================
ARTIFACT_CASES_HTML: tuple[ArtifactCase, ...] = (
    ArtifactCase(
        meta=_meta(
            "ART-HTML-001",
            "ART-HTML",
            "xss-sentinel",
            "html",
            "A description containing '<img src=x onerror=alert(1)>' embedded exactly once: "
            "the '<'/'>' characters must be escaped to \\u003c/\\u003e in the embedded text so "
            'the payload cannot break out of the <script type="application/json"> block, '
            "while json.loads still recovers the original literal string.",
            _EVIDENCE_JSON_FOR_HTML,
        ),
        input_rows=(_requirement_row(description="<img src=x onerror=alert(1)>"),),
        expected_by_context={"html": (True, True, True, None, None, None, None, None, None, True)},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-HTML-002",
            "ART-HTML",
            "script-close-tag",
            "html",
            "A description containing the literal string '</script>': the embedded text must "
            "never contain that literal 4-character sequence 'so the HTML page's real "
            '<script id="report-data"> block cannot be closed early by embedded data.',
            _EVIDENCE_JSON_FOR_HTML,
        ),
        input_rows=(
            _requirement_row(description="close it here: </script><script>evil()</script>"),
        ),
        expected_by_context={"html": (True, True, True, None, None, None, None, None, None, True)},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-HTML-003",
            "ART-HTML",
            "angle-amp",
            "html",
            "A description containing '<', '>', and '&' together: all three must be escaped in "
            "the embedded text and recovered exactly by json.loads.",
            _EVIDENCE_JSON_FOR_HTML,
        ),
        input_rows=(_requirement_row(description="A & B <C> D"),),
        expected_by_context={"html": (True, True, True, True, None, None, None, None, None, True)},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-HTML-004",
            "ART-HTML",
            "line-para-separators",
            "html",
            "A description containing U+2028 (LINE SEPARATOR) and U+2029 (PARAGRAPH SEPARATOR): "
            "both are valid inside a JSON string but invalid inside a raw JavaScript string "
            "literal, so json_for_html escapes them to \\u2028/\\u2029; json.loads still "
            "recovers the original raw characters.",
            _EVIDENCE_JSON_FOR_HTML,
        ),
        input_rows=(_requirement_row(description="line one line two paragraph two"),),
        expected_by_context={"html": (True, None, None, None, True, True, True, True, None, True)},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-HTML-005",
            "ART-HTML",
            "non-ascii-unicode",
            "html",
            "A description containing non-ASCII Unicode (accented Latin, CJK, and an emoji): "
            "json_for_html calls json.dumps(..., ensure_ascii=False), so these characters "
            "appear LITERALLY (not as \\uXXXX escapes) in the embedded text, and still "
            "round-trip exactly through json.loads.",
            _EVIDENCE_JSON_FOR_HTML,
        ),
        input_rows=(_requirement_row(description="Café 徽章 \U0001f9ed"),),
        expected_by_context={"html": (True, None, None, None, None, None, None, None, True, True)},
    ),
)


# ==============================================================================================
# ART-EMAIL-001..004 -- write_email_reports' per-scout status/branching
# (scout_schedule_cli.py:1009-1015).
#
# expected_by_context["email"] shape is per-member:
#   missing-requirements       -> (txt file count, html file count).
#   all-complete                -> (txt file count, html file count, csv row status).
#   no-data                     -> (csv row status,).
#   same-name-disambiguation    -> (txt file count, filenames distinct bool).
# ==============================================================================================
ARTIFACT_CASES_EMAIL: tuple[ArtifactCase, ...] = (
    ArtifactCase(
        meta=_meta(
            "ART-EMAIL-001",
            "ART-EMAIL",
            "missing-requirements",
            "email",
            "A scout with one incomplete actionable leaf gets status 'missing_requirements' and "
            "BOTH a .txt and .html file are written under emails/.",
            _EVIDENCE_EMAIL,
        ),
        input_rows=(_requirement_row(completed_requirement=False),),
        expected_by_context={"email": (1, 1)},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-EMAIL-002",
            "ART-EMAIL",
            "all-complete",
            "email",
            "A scout whose only requirement is completed gets status 'all_complete' and NO "
            ".txt/.html files are written (missing_count == 0 skips the write at "
            "scout_schedule_cli.py:1020-1024).",
            _EVIDENCE_EMAIL,
        ),
        input_rows=(_requirement_row(completed_requirement=True),),
        expected_by_context={"email": (0, 0, "all_complete")},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-EMAIL-003",
            "ART-EMAIL",
            "no-data",
            "email",
            "A scout with no requirements at all but a recorded error gets status "
            "'no_data_scraped' (the 'elif not scout.get(\"requirements\") and "
            "scout.get(\"errors\")' branch), not 'all_complete'.",
            _EVIDENCE_EMAIL,
        ),
        input_rows=(),
        expected_by_context={"email": ("no_data_scraped",)},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-EMAIL-004",
            "ART-EMAIL",
            "same-name-disambiguation",
            "email",
            "Two DIFFERENT attendees (different attendee_id) sharing the exact same display "
            "name, both with missing requirements: attendee_filename_stem's per-run UUID makes "
            "their two .txt/.html filenames distinct even though the name-slug portion is "
            "identical.",
            _EVIDENCE_EMAIL + "; " + _EVIDENCE_FILENAME,
        ),
        input_rows=(
            _requirement_row(attendee_id="90000001", completed_requirement=False),
            _requirement_row(attendee_id="90000002", completed_requirement=False),
        ),
        expected_by_context={"email": (2, True)},
    ),
)


# ==============================================================================================
# ART-NAME-001..009 -- safe_slug/attendee_filename_stem's ASCII-only, non-alnum-collapsing
# contract (scout_schedule_cli.py:635-646). ART-NAME-007 is the ONE intentional-change row in
# Task 20: legacy follows a symlinked output root with no realpath/containment check anywhere in
# atomic_write_text or write_outputs.
#
# expected_by_context["filename"] shape is per-member:
#   path-traversal / absolute-path / unicode-name / windows-reserved / empty-name
#       -> the exact safe_slug() return string.
#   case-collision              -> (stem_a startswith "avery-archer-", stem_b startswith
#                                   "avery-archer-", stems distinct).
#   symlinked-root               -> the round-tripped file content read back through the real
#                                   (non-symlink) target directory.
#   duplicate-display-name       -> stems distinct bool.
#   duplicate-html-filename      -> (sub_dir_created bool, escape_dir_created bool,
#                                    first/second report content differ bool).
# ==============================================================================================
ARTIFACT_CASES_NAME: tuple[ArtifactCase, ...] = (
    ArtifactCase(
        meta=_meta(
            "ART-NAME-001",
            "ART-NAME",
            "path-traversal",
            "filename",
            "safe_slug('../../etc/passwd') collapses every run of non [A-Za-z0-9] characters "
            "(including '.' and '/') to a single '-', so the traversal sequence cannot survive "
            "into the filename: the result is 'etc-passwd', not a path.",
            _EVIDENCE_FILENAME,
        ),
        input_rows=({"scout_name": "../../etc/passwd"},),
        expected_by_context={"filename": "etc-passwd"},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-NAME-002",
            "ART-NAME",
            "absolute-path",
            "filename",
            "safe_slug('/etc/shadow') collapses the leading '/' the same way, producing "
            "'etc-shadow' -- never an absolute path.",
            _EVIDENCE_FILENAME,
        ),
        input_rows=({"scout_name": "/etc/shadow"},),
        expected_by_context={"filename": "etc-shadow"},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-NAME-003",
            "ART-NAME",
            "unicode-name",
            "filename",
            "safe_slug's character class [^A-Za-z0-9] is ASCII-only, so a name made entirely of "
            "non-ASCII letters (e.g. Japanese) has EVERY character replaced by '-', collapses "
            "to '', and falls back to the literal 'unknown-scout' -- a real, surprising "
            "PRESERVE finding, not a fix.",
            _EVIDENCE_FILENAME,
        ),
        input_rows=({"scout_name": "日本語太郎"},),
        expected_by_context={"filename": "unknown-scout"},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-NAME-004",
            "ART-NAME",
            "case-collision",
            "filename",
            "safe_slug lowercases, so 'Avery Archer' and 'AVERY ARCHER' produce the identical "
            "slug 'avery-archer'; this is a PURE simulated string-contract case (no real "
            "filesystem collision is exercised) -- two DIFFERENT attendee_ids still resolve to "
            "distinct final filenames because attendee_filename_stem appends the full per-run "
            "UUID, never relying on slug uniqueness alone.",
            _EVIDENCE_FILENAME,
        ),
        input_rows=(
            {"scout_name": "Avery Archer", "attendee_id": "90000001"},
            {"scout_name": "AVERY ARCHER", "attendee_id": "90000002"},
        ),
        expected_by_context={"filename": (True, True, True)},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-NAME-005",
            "ART-NAME",
            "windows-reserved",
            "filename",
            "safe_slug('CON') has no Windows-reserved-device-name defense at all: the slug is "
            "the literal 'con', which a real Windows filesystem would refuse as a bare "
            "filename component. This is a PURE simulated string-contract case over the "
            "slugification logic, not a claim about actual Windows filesystem behavior.",
            _EVIDENCE_FILENAME,
        ),
        input_rows=({"scout_name": "CON"},),
        expected_by_context={"filename": "con"},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-NAME-006",
            "ART-NAME",
            "empty-name",
            "filename",
            "safe_slug('') collapses to '' and falls back to the literal 'unknown-scout', "
            "identical to the all-non-ASCII case.",
            _EVIDENCE_FILENAME,
        ),
        input_rows=({"scout_name": ""},),
        expected_by_context={"filename": "unknown-scout"},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-NAME-007",
            "ART-NAME",
            "symlinked-root",
            "filename",
            "Legacy write_outputs/atomic_write_text call Path.mkdir/Path.open directly with no "
            "realpath resolution or containment check: when the CLI's --output directory is "
            "itself a symlink to another directory, the file is published through the symlink "
            "into that OTHER directory with no warning or rejection.",
            _EVIDENCE_ATOMIC + "; " + _EVIDENCE_WRITE_OUTPUTS,
            classification=Classification.INTENTIONAL_CHANGE,
            target_owner="Slice 2",
            target_observation="Slice 2's output-root resolution will reject (or explicitly "
            "confirm) a symlinked --output directory before publishing any file, instead of "
            "silently following it.",
        ),
        input_rows=({"scout_name": SCOUT_NAME},),
        expected_by_context={"filename": "hello"},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-NAME-008",
            "ART-NAME",
            "duplicate-display-name",
            "filename",
            "Two DIFFERENT attendees with the EXACT SAME display name and casing: "
            "attendee_filename_stem still yields two different filenames because the per-run "
            "UUID (keyed on attendee_id, not name) differs.",
            _EVIDENCE_FILENAME,
        ),
        input_rows=(
            {"scout_name": SCOUT_NAME, "attendee_id": "90000003"},
            {"scout_name": SCOUT_NAME, "attendee_id": "90000004"},
        ),
        expected_by_context={"filename": True},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-NAME-009",
            "ART-NAME",
            "duplicate-html-filename",
            "filename",
            "write_outputs resolves --html-name to Path(html_name).name (its basename only), so "
            "a path-like or repeated html_name always collapses to the same safe basename "
            "inside output_dir; writing the report twice with the same requested name simply "
            "overwrites the prior file atomically (last write wins), never creating two files "
            "or escaping output_dir.",
            _EVIDENCE_WRITE_OUTPUTS,
        ),
        input_rows=({"scout_name": SCOUT_NAME},),
        expected_by_context={"filename": (False, False, True)},
    ),
)


# ==============================================================================================
# ART-FORMULA-001..006 -- the six CSV/XLSX formula-injection prefixes, placed in an
# outward-facing CSV field. write_csv (scout_schedule_cli.py:663-669) writes the field value
# through csv.DictWriter completely unescaped: PRESERVE, no current mitigation exists.
#
# expected_by_context["formula"] is the raw prefix VALUE itself (from the same table row the
# input was built from): the real claim under test is "the value survives unchanged," so the
# expected value is that same source-of-truth string, never a hand-retyped copy of it.
# ==============================================================================================
_FORMULA_PREFIXES: tuple[tuple[str, str], ...] = (
    ("eq-prefix", "=SUM(A1:A9)"),
    ("plus-prefix", "+1+1"),
    ("minus-prefix", "-1-1"),
    ("at-prefix", "@SUM(A1:A9)"),
    ("tab-prefix", "\t=cmd|'/c calc'!A1"),
    ("cr-prefix", "\r=cmd|'/c calc'!A1"),
)

ARTIFACT_CASES_FORMULA: tuple[ArtifactCase, ...] = tuple(
    ArtifactCase(
        meta=_meta(
            f"ART-FORMULA-{i:03d}",
            "ART-FORMULA",
            member,
            "formula",
            f"A scout_name field starting with {value[:1]!r} (spreadsheet-formula-injection "
            "prefix): write_csv writes it through csv.DictWriter with no escaping, quoting-only "
            "defense, or leading-apostrophe defusing -- the raw prefix survives into the "
            "written CSV bytes unchanged.",
            _EVIDENCE_WRITE_CSV,
        ),
        input_rows=({"scout_name": value},),
        expected_by_context={"formula": value},
    )
    for i, (member, value) in enumerate(_FORMULA_PREFIXES, start=1)
)


# ==============================================================================================
# ART-FAIL-001..006 -- failure injected at one exact filesystem seam inside atomic_write_text
# (scout_schedule_cli.py:648-661): Path.open (temp-file open), the write() call on the opened
# temp file, os.fsync, os.replace (the atomic publish step itself), and Path.unlink (the finally
# cleanup). "partial-multi-file" injects the failure on the Nth of several sibling
# atomic_write_text calls inside one write_outputs run. The SERIALIZERS (json.dumps/csv writer)
# and the writer functions under test are never mocked -- only these filesystem seams.
#
# expected_by_context["atomic_fail"] shape is per-member:
#   before-render / during-temp-write / before-atomic-replace
#       -> (destination file content after the failed write, count of leftover *.tmp files).
#   after-atomic-replace   -> (scouts.json exists, len(parsed scouts.json payload)).
#   during-cleanup         -> the destination file content (the publish itself still succeeded).
#   partial-multi-file     -> (scouts.json exists, classes.csv exists, requirements.csv exists,
#                              errors.csv exists, report.html exists, summary.json exists).
# ==============================================================================================
ARTIFACT_CASES_FAIL: tuple[ArtifactCase, ...] = (
    ArtifactCase(
        meta=_meta(
            "ART-FAIL-001",
            "ART-FAIL",
            "before-render",
            "atomic_fail",
            "Path.open on the temp file raises before any bytes are written at all: the prior "
            "destination file (if any) is left completely untouched, and no .tmp file is ever "
            "created (there is nothing for the finally block's unlink(missing_ok=True) to do).",
            _EVIDENCE_ATOMIC,
        ),
        input_rows=(),
        expected_by_context={"atomic_fail": ("prior-content", 0)},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-FAIL-002",
            "ART-FAIL",
            "during-temp-write",
            "atomic_fail",
            "os.fsync raises after the temp file's content was fully written but before "
            "os.replace: the prior destination file is untouched, and the finally block "
            "removes the now-orphaned .tmp file, leaving no leftover.",
            _EVIDENCE_ATOMIC,
        ),
        input_rows=(),
        expected_by_context={"atomic_fail": ("prior-content", 0)},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-FAIL-003",
            "ART-FAIL",
            "before-atomic-replace",
            "atomic_fail",
            "os.replace itself raises: the destination file keeps its PRIOR content exactly "
            "(the replace never happened), and the finally block still removes the .tmp file "
            "(os.replace failing left the .tmp file present at its original path, so unlink "
            "has something real to remove).",
            _EVIDENCE_ATOMIC,
        ),
        input_rows=(),
        expected_by_context={"atomic_fail": ("prior-content", 0)},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-FAIL-004",
            "ART-FAIL",
            "after-atomic-replace",
            "atomic_fail",
            "Within one write_outputs run, the FIRST atomic_write_text call (scouts.json) "
            "succeeds and is durably published; injecting a failure on the SECOND call "
            "(classes.csv) leaves the first file's successful content intact -- a successful "
            "earlier publish is never rolled back by a later failure.",
            _EVIDENCE_WRITE_OUTPUTS + "; " + _EVIDENCE_ATOMIC,
        ),
        input_rows=(_class_row(), _requirement_row()),
        expected_by_context={"atomic_fail": (True, 1)},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-FAIL-005",
            "ART-FAIL",
            "during-cleanup",
            "atomic_fail",
            "Path.unlink raises INSIDE the finally block AFTER os.replace already succeeded: "
            "the destination file's new content is durably correct (the publish itself "
            "succeeded), yet the exception from the failed cleanup still propagates to the "
            "caller -- a caller-visible failure despite the write having actually succeeded.",
            _EVIDENCE_ATOMIC,
        ),
        input_rows=(),
        expected_by_context={"atomic_fail": "new-content"},
    ),
    ArtifactCase(
        meta=_meta(
            "ART-FAIL-006",
            "ART-FAIL",
            "partial-multi-file",
            "atomic_fail",
            "write_outputs calls atomic_write_text for scouts.json, classes.csv, "
            "requirements.csv, errors.csv, the HTML report, then summary.json, in that fixed "
            "order; injecting a failure on os.replace for the THIRD call (requirements.csv) "
            "leaves scouts.json and classes.csv published, requirements.csv untouched/absent, "
            "and every later sibling (errors.csv, the HTML report, summary.json) never "
            "attempted at all.",
            _EVIDENCE_WRITE_OUTPUTS,
        ),
        input_rows=(_class_row(), _requirement_row()),
        expected_by_context={"atomic_fail": (True, True, False, False, False, False)},
    ),
)


ARTIFACT_CASES: tuple[ArtifactCase, ...] = (
    ARTIFACT_CASES_SCHEMA
    + ARTIFACT_CASES_HTML
    + ARTIFACT_CASES_EMAIL
    + ARTIFACT_CASES_NAME
    + ARTIFACT_CASES_FORMULA
    + ARTIFACT_CASES_FAIL
)


# ==============================================================================================
# PRIV-SURFACE / PRIV-EGRESS / PRIV-CONTAIN -- bare metadata only (like NET-POLICY-* in
# acquisition_cases.py). The actual assertions live in tests/privacy/test_surface_policies.py as
# plain pytest functions (not routed through LegacyArtifactRunner, since each exercises a
# different SurfaceClass policy rather than one uniform writer call); these entries exist so the
# registry self-check can confirm every PRIV-SURFACE/PRIV-EGRESS/PRIV-CONTAIN axis member is
# covered by a declared, evidenced case.
# ==============================================================================================
_EVIDENCE_POLICY = (
    "tests/matrix/policies.py SurfacePolicy rows; tests/privacy/test_surface_policies.py"
)

_PRIV_SURFACE_MEMBERS = (
    "input-private-allowed",
    "input-private-forbidden",
    "adapter-private-allowed",
    "adapter-private-forbidden",
    "operational-private-allowed",
    "operational-private-forbidden",
    "audience-shareable-allowed",
    "audience-shareable-forbidden",
    "local-ui-allowed",
    "local-ui-forbidden",
    "diagnostic-allowed",
    "diagnostic-forbidden",
)

PRIV_SURFACE_METADATA: tuple[CaseMetadata, ...] = tuple(
    _meta(
        f"PRIV-SURFACE-{i:03d}",
        "PRIV-SURFACE",
        member,
        "privacy",
        f"SurfaceClass member {member!r}: {'an allowed field appears' if member.endswith('allowed') else 'a forbidden sentinel never appears'} on this surface's real output, per its SurfacePolicy row.",
        _EVIDENCE_POLICY,
    )
    for i, member in enumerate(_PRIV_SURFACE_MEMBERS, start=1)
)

_PRIV_EGRESS_MEMBERS = (
    "filename",
    "json",
    "csv",
    "html",
    "email",
    "stdout",
    "stderr",
    "api-error",
    "sse",
    "diagnostics",
)

PRIV_EGRESS_METADATA: tuple[CaseMetadata, ...] = tuple(
    _meta(
        f"PRIV-EGRESS-{i:03d}",
        "PRIV-EGRESS",
        member,
        "privacy",
        f"The {member} output channel never contains a forbidden sentinel value.",
        _EVIDENCE_POLICY,
    )
    for i, member in enumerate(_PRIV_EGRESS_MEMBERS, start=1)
)

PRIV_CONTAIN_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "PRIV-CONTAIN-001",
        "PRIV-CONTAIN",
        "adapter-file-stays-in-root",
        "privacy",
        "An adapter-private (raw/) file is written strictly inside its selected output root; "
        "no adapter-private write escapes above the run's output directory.",
        _EVIDENCE_POLICY,
    ),
    _meta(
        "PRIV-CONTAIN-002",
        "PRIV-CONTAIN",
        "no-private-field-reaches-shareable",
        "privacy",
        "No field allowed only on an input-private/adapter-private/operational-private surface "
        "(per its SurfacePolicy.allowed_fields) ever appears among an audience-shareable "
        "surface's allowed_fields.",
        _EVIDENCE_POLICY,
    ),
)

PRIVACY_METADATA: tuple[CaseMetadata, ...] = (
    PRIV_SURFACE_METADATA + PRIV_EGRESS_METADATA + PRIV_CONTAIN_METADATA
)

ALL_ARTIFACT_METADATA: tuple[CaseMetadata, ...] = (
    tuple(case.meta for case in ARTIFACT_CASES) + PRIVACY_METADATA
)
