"""Input-loader characterization catalog (Task 17).

Every row here is ``preserve`` classification: it pins the *current* behavior of
``scout_schedule_cli``'s ``load_inputs`` / ``load_csv`` / ``load_xlsx`` / ``load_json`` /
``load_text`` seams, not a desired future behavior. This module holds only frozen data --
it never imports the legacy application or any optional third-party package. The runner in
``tests/characterization/test_input_matrix.py`` performs the real imports.

Success rows normalize to an exact ``(name, url, registrant_type)`` tuple. Error rows record
the exception type and the complete bounded message (with the temp path replaced by the
fixed ``<input>`` sentinel so the message is deterministic).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.matrix.model import (
    CaseMetadata,
    Classification,
    Domain,
    EvidenceKind,
)

# Synthetic identities only -- never real scout data.
NAME_A = "Avery Example"
NAME_B = "Bailey Example"
URL_A = "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_A"
URL_B = "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_B"


@dataclass(frozen=True, slots=True)
class InputSpec:
    format: str
    variant: str
    entry: str = "load_inputs"
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    json_value: object | None = None
    text_lines: tuple[str, ...] = ()
    sheets: tuple[tuple[str, tuple[str, ...], tuple[tuple[str, ...], ...]], ...] = ()
    sheet_arg: str = "Scouts Only"
    include_adults: bool = False
    profile: str = ""


@dataclass(frozen=True, slots=True)
class InputObservation:
    records: tuple[tuple[str, str, str], ...] = ()
    exception_type: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class InputCase:
    meta: CaseMetadata
    input: InputSpec
    expected_legacy: InputObservation = field(default_factory=InputObservation)


def _meta(
    case_id: str,
    axis_id: str,
    member: str,
    contexts: tuple[str, ...],
    rationale: str,
    evidence_reference: str,
) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id=axis_id,
        member=member,
        domain=Domain.INPUT,
        classification=Classification.PRESERVE,
        evidence=EvidenceKind.CURRENT_BRANCH,
        rationale=rationale,
        contexts=contexts,
        evidence_reference=evidence_reference,
    )


NAME_URL_HEADERS = ("Attendee Name", "QR Code Contents")
NAME_URL_TYPE_HEADERS = ("Attendee Name", "QR Code Contents", "Registrant Type")

_FORMAT_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-FORMAT-001",
            "IN-FORMAT",
            "csv",
            ("csv",),
            "A well-formed CSV with the canonical headers loads one normalized row.",
            "scout_schedule_cli.load_csv lines 289-317",
        ),
        InputSpec(
            format="csv",
            variant="canonical-csv",
            headers=NAME_URL_TYPE_HEADERS,
            rows=((NAME_A, URL_A, "Youth"),),
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
    InputCase(
        _meta(
            "IN-FORMAT-002",
            "IN-FORMAT",
            "xlsx",
            ("xlsx",),
            "A single-sheet XLSX with canonical headers loads one normalized row.",
            "scout_schedule_cli.load_xlsx lines 261-286",
        ),
        InputSpec(
            format="xlsx",
            variant="canonical-xlsx",
            headers=NAME_URL_TYPE_HEADERS,
            rows=((NAME_A, URL_A, "Youth"),),
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
    InputCase(
        _meta(
            "IN-FORMAT-003",
            "IN-FORMAT",
            "json-list",
            ("json",),
            "A top-level JSON list of mapping items loads through the load_inputs pipeline.",
            "scout_schedule_cli.load_json lines 320-336",
        ),
        InputSpec(
            format="json",
            variant="json-list",
            json_value=[{"name": NAME_A, "url": URL_A, "registrant_type": "Youth"}],
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
    InputCase(
        _meta(
            "IN-FORMAT-004",
            "IN-FORMAT",
            "json-scouts",
            ("json",),
            "A JSON object with a 'scouts' key unwraps to its list before loading.",
            "scout_schedule_cli.load_json line 323",
        ),
        InputSpec(
            format="json",
            variant="json-scouts",
            json_value={"scouts": [{"name": NAME_A, "url": URL_A, "registrant_type": "Youth"}]},
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
    InputCase(
        _meta(
            "IN-FORMAT-005",
            "IN-FORMAT",
            "json-data",
            ("json",),
            "A JSON object with a 'data' key unwraps to its list before loading.",
            "scout_schedule_cli.load_json line 323",
        ),
        InputSpec(
            format="json",
            variant="json-data",
            json_value={"data": [{"name": NAME_A, "url": URL_A, "registrant_type": "Youth"}]},
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
    InputCase(
        _meta(
            "IN-FORMAT-006",
            "IN-FORMAT",
            "json-mapping",
            ("json",),
            "A bare JSON mapping without scouts/data keys wraps itself as a one-item list.",
            "scout_schedule_cli.load_json line 323",
        ),
        InputSpec(
            format="json",
            variant="json-mapping",
            json_value={"name": NAME_A, "url": URL_A, "registrant_type": "Youth"},
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
    InputCase(
        _meta(
            "IN-FORMAT-007",
            "IN-FORMAT",
            "json-string-row",
            ("json",),
            "A JSON list of bare strings loads each string as a URL with an empty name.",
            "scout_schedule_cli.load_json lines 326-327",
        ),
        InputSpec(
            format="json",
            variant="json-string-row",
            json_value=[URL_A],
        ),
        InputObservation(records=(("", URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-FORMAT-008",
            "IN-FORMAT",
            "text",
            ("text",),
            "A plain-text file with one URL per line loads through the load_inputs pipeline.",
            "scout_schedule_cli.load_text lines 339-350",
        ),
        InputSpec(
            format="text",
            variant="text-url",
            text_lines=(URL_A,),
        ),
        InputObservation(records=(("", URL_A, ""),)),
    ),
)

_ALIAS_NAME_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-ALIAS-NAME-001",
            "IN-ALIAS-NAME",
            "attendee-name",
            ("csv", "xlsx"),
            "The 'Attendee Name' header resolves the name column in both tabular formats.",
            "scout_schedule_cli.first_matching_key/load_csv name aliases",
        ),
        InputSpec(
            format="tabular",
            variant="name-attendee",
            headers=("Attendee Name", "QR Code Contents"),
            rows=((NAME_A, URL_A),),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-ALIAS-NAME-002",
            "IN-ALIAS-NAME",
            "name",
            ("csv", "xlsx"),
            "The bare 'Name' header resolves the name column in both tabular formats.",
            "scout_schedule_cli name-alias list ['Attendee Name','Name','Scout Name']",
        ),
        InputSpec(
            format="tabular",
            variant="name-bare",
            headers=("Name", "QR Code Contents"),
            rows=((NAME_A, URL_A),),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-ALIAS-NAME-003",
            "IN-ALIAS-NAME",
            "scout-name",
            ("csv", "xlsx"),
            "The 'Scout Name' header resolves the name column in both tabular formats.",
            "scout_schedule_cli name-alias list ['Attendee Name','Name','Scout Name']",
        ),
        InputSpec(
            format="tabular",
            variant="name-scout",
            headers=("Scout Name", "QR Code Contents"),
            rows=((NAME_A, URL_A),),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
)

_ALIAS_URL_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-ALIAS-URL-001",
            "IN-ALIAS-URL",
            "qr-code-contents",
            ("csv", "xlsx"),
            "The 'QR Code Contents' header resolves the URL column in both tabular formats.",
            "scout_schedule_cli url-alias list ['QR Code Contents','URL','QR URL','Link']",
        ),
        InputSpec(
            format="tabular",
            variant="url-qrcode",
            headers=("Attendee Name", "QR Code Contents"),
            rows=((NAME_A, URL_A),),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-ALIAS-URL-002",
            "IN-ALIAS-URL",
            "url",
            ("csv", "xlsx"),
            "The bare 'URL' header resolves the URL column in both tabular formats.",
            "scout_schedule_cli url-alias list ['QR Code Contents','URL','QR URL','Link']",
        ),
        InputSpec(
            format="tabular",
            variant="url-bare",
            headers=("Attendee Name", "URL"),
            rows=((NAME_A, URL_A),),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-ALIAS-URL-003",
            "IN-ALIAS-URL",
            "qr-url",
            ("csv", "xlsx"),
            "The 'QR URL' header resolves the URL column in both tabular formats.",
            "scout_schedule_cli url-alias list ['QR Code Contents','URL','QR URL','Link']",
        ),
        InputSpec(
            format="tabular",
            variant="url-qrurl",
            headers=("Attendee Name", "QR URL"),
            rows=((NAME_A, URL_A),),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-ALIAS-URL-004",
            "IN-ALIAS-URL",
            "link",
            ("csv", "xlsx"),
            "The 'Link' header resolves the URL column in both tabular formats.",
            "scout_schedule_cli url-alias list ['QR Code Contents','URL','QR URL','Link']",
        ),
        InputSpec(
            format="tabular",
            variant="url-link",
            headers=("Attendee Name", "Link"),
            rows=((NAME_A, URL_A),),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
)

_ALIAS_TYPE_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-ALIAS-TYPE-001",
            "IN-ALIAS-TYPE",
            "registrant-type",
            ("csv", "xlsx"),
            "The 'Registrant Type' header resolves the type column in both tabular formats.",
            "scout_schedule_cli type-alias list ['Registrant Type','Type']",
        ),
        InputSpec(
            format="tabular",
            variant="type-registrant",
            headers=("Attendee Name", "QR Code Contents", "Registrant Type"),
            rows=((NAME_A, URL_A, "Youth"),),
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
    InputCase(
        _meta(
            "IN-ALIAS-TYPE-002",
            "IN-ALIAS-TYPE",
            "type",
            ("csv", "xlsx"),
            "The bare 'Type' header resolves the type column in both tabular formats.",
            "scout_schedule_cli type-alias list ['Registrant Type','Type']",
        ),
        InputSpec(
            format="tabular",
            variant="type-bare",
            headers=("Attendee Name", "QR Code Contents", "Type"),
            rows=((NAME_A, URL_A, "Youth"),),
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
)

_HEADER_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-HEADER-001",
            "IN-HEADER",
            "utf8-bom",
            ("csv",),
            "A UTF-8 BOM on the first header is stripped so the leading column still matches.",
            "scout_schedule_cli.load_csv opens with encoding utf-8-sig",
        ),
        InputSpec(
            format="csv",
            variant="header-bom",
            headers=("Attendee Name", "QR Code Contents"),
            rows=((NAME_A, URL_A),),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-HEADER-002",
            "IN-HEADER",
            "normalization",
            ("csv",),
            "Header case and punctuation are normalized away before alias matching.",
            "scout_schedule_cli.norm_header line 218",
        ),
        InputSpec(
            format="csv",
            variant="header-normalization",
            headers=("ATTENDEE  NAME", "qr.code.contents"),
            rows=((NAME_A, URL_A),),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-HEADER-003",
            "IN-HEADER",
            "whitespace",
            ("csv",),
            "Surrounding whitespace on a header is trimmed before alias matching.",
            "scout_schedule_cli.norm_header strips then removes non-alnum",
        ),
        InputSpec(
            format="csv",
            variant="header-whitespace",
            headers=("  Attendee Name  ", "\tQR Code Contents\t"),
            rows=((NAME_A, URL_A),),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-HEADER-004",
            "IN-HEADER",
            "unknown",
            ("csv",),
            "An unrecognized extra header column is ignored when a URL column is present.",
            "scout_schedule_cli.load_csv only maps known aliases",
        ),
        InputSpec(
            format="csv",
            variant="header-unknown",
            headers=("Attendee Name", "QR Code Contents", "Mystery Column"),
            rows=((NAME_A, URL_A, "ignored-extra"),),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
)

_XLSX_SHEET_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-XLSX-SHEET-001",
            "IN-XLSX-SHEET",
            "requested",
            ("xlsx",),
            "A requested sheet name that exists is selected over all other sheets.",
            "scout_schedule_cli.load_xlsx lines 263-268",
        ),
        InputSpec(
            format="xlsx",
            variant="sheet-requested",
            sheets=(
                ("Requested", NAME_URL_HEADERS, ((NAME_A, URL_A),)),
                ("Other", NAME_URL_HEADERS, ((NAME_B, URL_B),)),
            ),
            sheet_arg="Requested",
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-XLSX-SHEET-002",
            "IN-XLSX-SHEET",
            "scouts-only",
            ("xlsx",),
            "When the requested sheet is absent, a 'Scouts Only' sheet is preferred.",
            "scout_schedule_cli.load_xlsx lines 265-266",
        ),
        InputSpec(
            format="xlsx",
            variant="sheet-scouts-only",
            sheets=(
                ("Other", NAME_URL_HEADERS, ((NAME_B, URL_B),)),
                ("Scouts Only", NAME_URL_HEADERS, ((NAME_A, URL_A),)),
            ),
            sheet_arg="Absent Sheet",
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-XLSX-SHEET-003",
            "IN-XLSX-SHEET",
            "first",
            ("xlsx",),
            "With neither the requested nor a 'Scouts Only' sheet, the first sheet is used.",
            "scout_schedule_cli.load_xlsx line 268",
        ),
        InputSpec(
            format="xlsx",
            variant="sheet-first",
            sheets=(
                ("First", NAME_URL_HEADERS, ((NAME_A, URL_A),)),
                ("Second", NAME_URL_HEADERS, ((NAME_B, URL_B),)),
            ),
            sheet_arg="Absent Sheet",
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
)

_XLSX_ERR_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-XLSX-ERR-001",
            "IN-XLSX-ERR",
            "empty-workbook",
            ("xlsx",),
            "An empty workbook is tolerated by load_xlsx, which returns no rows rather "
            "than raising.",
            "scout_schedule_cli.load_xlsx lines 270-272",
        ),
        InputSpec(
            format="xlsx",
            variant="empty-workbook",
            entry="load_xlsx",
            sheets=(),
        ),
        InputObservation(records=()),
    ),
    InputCase(
        _meta(
            "IN-XLSX-ERR-002",
            "IN-XLSX-ERR",
            "missing-url",
            ("xlsx",),
            "A sheet without any recognizable URL column raises a bounded ValueError.",
            "scout_schedule_cli.load_xlsx lines 277-278",
        ),
        InputSpec(
            format="xlsx",
            variant="missing-url-column",
            entry="load_xlsx",
            sheets=(("Sheet", ("Attendee Name", "Registrant Type"), ((NAME_A, "Youth"),)),),
        ),
        InputObservation(
            exception_type="ValueError",
            message="Could not find a URL column in XLSX sheet 'Sheet'",
        ),
    ),
)

_JSON_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-JSON-001",
            "IN-JSON",
            "name-aliases",
            ("json",),
            "load_json resolves the name from both 'name' and 'attendee_name' keys.",
            "scout_schedule_cli.load_json line 331",
        ),
        InputSpec(
            format="json",
            variant="json-name-aliases",
            entry="load_json",
            json_value=[
                {"name": NAME_A, "url": "token-a"},
                {"attendee_name": NAME_B, "url": "token-b"},
            ],
        ),
        InputObservation(records=((NAME_A, "token-a", ""), (NAME_B, "token-b", ""))),
    ),
    InputCase(
        _meta(
            "IN-JSON-002",
            "IN-JSON",
            "url-aliases",
            ("json",),
            "load_json resolves the URL from 'url', 'qr_url', and 'qr_code_contents' keys.",
            "scout_schedule_cli.load_json line 332",
        ),
        InputSpec(
            format="json",
            variant="json-url-aliases",
            entry="load_json",
            json_value=[
                {"name": NAME_A, "qr_url": "token-a"},
                {"name": NAME_B, "qr_code_contents": "token-b"},
            ],
        ),
        InputObservation(records=((NAME_A, "token-a", ""), (NAME_B, "token-b", ""))),
    ),
    InputCase(
        _meta(
            "IN-JSON-003",
            "IN-JSON",
            "type-aliases",
            ("json",),
            "load_json resolves the registrant type from both 'registrant_type' and 'type'.",
            "scout_schedule_cli.load_json line 333",
        ),
        InputSpec(
            format="json",
            variant="json-type-aliases",
            entry="load_json",
            json_value=[
                {"name": NAME_A, "url": "token-a", "registrant_type": "Youth"},
                {"name": NAME_B, "url": "token-b", "type": "Adult"},
            ],
        ),
        InputObservation(records=((NAME_A, "token-a", "Youth"), (NAME_B, "token-b", "Adult"))),
    ),
    InputCase(
        _meta(
            "IN-JSON-004",
            "IN-JSON",
            "string-item",
            ("json",),
            "A bare string list item becomes a URL with an empty name and type.",
            "scout_schedule_cli.load_json lines 326-327",
        ),
        InputSpec(
            format="json",
            variant="json-string-item",
            entry="load_json",
            json_value=["standalone-token"],
        ),
        InputObservation(records=(("", "standalone-token", ""),)),
    ),
    InputCase(
        _meta(
            "IN-JSON-005",
            "IN-JSON",
            "invalid-item",
            ("json",),
            "Non-string, non-mapping list items (numbers, null) are silently skipped.",
            "scout_schedule_cli.load_json lines 325-335",
        ),
        InputSpec(
            format="json",
            variant="json-invalid-item",
            entry="load_json",
            json_value=[123, {"name": NAME_A, "url": "token-a"}, None],
        ),
        InputObservation(records=((NAME_A, "token-a", ""),)),
    ),
    InputCase(
        _meta(
            "IN-JSON-006",
            "IN-JSON",
            "malformed-top",
            ("json",),
            "A scalar top-level JSON value raises TypeError when load_json iterates it.",
            "scout_schedule_cli.load_json line 325",
        ),
        InputSpec(
            format="json",
            variant="json-malformed-top",
            entry="load_json",
            json_value=42,
        ),
        InputObservation(
            exception_type="TypeError",
            message="'int' object is not iterable",
        ),
    ),
)

_TEXT_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-TEXT-001",
            "IN-TEXT",
            "url-only",
            ("text",),
            "A line with only a URL becomes a record with an empty name.",
            "scout_schedule_cli.load_text lines 348-349",
        ),
        InputSpec(
            format="text",
            variant="text-url-only",
            entry="load_text",
            text_lines=(URL_A,),
        ),
        InputObservation(records=(("", URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-TEXT-002",
            "IN-TEXT",
            "name-url",
            ("text",),
            "A 'name,url' line with an https URL splits into name and URL on the first comma.",
            "scout_schedule_cli.load_text lines 345-347",
        ),
        InputSpec(
            format="text",
            variant="text-name-url",
            entry="load_text",
            text_lines=(f"{NAME_A},{URL_A}",),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-TEXT-003",
            "IN-TEXT",
            "blank-comment",
            ("text",),
            "Blank lines and lines starting with '#' are skipped.",
            "scout_schedule_cli.load_text lines 342-344",
        ),
        InputSpec(
            format="text",
            variant="text-blank-comment",
            entry="load_text",
            text_lines=("", "# a comment line", URL_A),
        ),
        InputObservation(records=(("", URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-TEXT-004",
            "IN-TEXT",
            "comma-no-https",
            ("text",),
            "A comma line without an https token is kept whole as a single URL value.",
            "scout_schedule_cli.load_text line 345 requires both comma and https",
        ),
        InputSpec(
            format="text",
            variant="text-comma-no-https",
            entry="load_text",
            text_lines=(f"{NAME_A},not-a-url",),
        ),
        InputObservation(records=(("", f"{NAME_A},not-a-url", ""),)),
    ),
)

_FILTER_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-FILTER-001",
            "IN-FILTER",
            "valid-prefix",
            ("csv",),
            "A URL under the scoutingevent mobile prefix survives the load_inputs filter.",
            "scout_schedule_cli.load_inputs line 247",
        ),
        InputSpec(
            format="csv",
            variant="filter-valid",
            headers=NAME_URL_TYPE_HEADERS,
            rows=((NAME_A, URL_A, "Youth"),),
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
    InputCase(
        _meta(
            "IN-FILTER-002",
            "IN-FILTER",
            "invalid-scheme",
            ("csv",),
            "An http (non-https) mobile URL is dropped while the valid row survives.",
            "scout_schedule_cli.load_inputs line 247",
        ),
        InputSpec(
            format="csv",
            variant="filter-scheme",
            headers=NAME_URL_TYPE_HEADERS,
            rows=(
                (NAME_A, URL_A, "Youth"),
                (NAME_B, "http://scoutingevent.com/mobile/checkin?t=TESTTOKEN_B", "Youth"),
            ),
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
    InputCase(
        _meta(
            "IN-FILTER-003",
            "IN-FILTER",
            "invalid-host-path",
            ("csv",),
            "An https URL on the wrong host is dropped while the valid row survives.",
            "scout_schedule_cli.load_inputs line 247",
        ),
        InputSpec(
            format="csv",
            variant="filter-host",
            headers=NAME_URL_TYPE_HEADERS,
            rows=(
                (NAME_A, URL_A, "Youth"),
                (NAME_B, "https://example.com/mobile/checkin?t=TESTTOKEN_B", "Youth"),
            ),
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
    InputCase(
        _meta(
            "IN-FILTER-004",
            "IN-FILTER",
            "adult",
            ("csv",),
            "An 'Adult' registrant is excluded by default while the youth row survives.",
            "scout_schedule_cli.load_inputs line 249",
        ),
        InputSpec(
            format="csv",
            variant="filter-adult",
            headers=NAME_URL_TYPE_HEADERS,
            rows=(
                (NAME_A, URL_A, "Youth"),
                (NAME_B, URL_B, "Adult"),
            ),
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
    InputCase(
        _meta(
            "IN-FILTER-005",
            "IN-FILTER",
            "part-time-adult",
            ("csv",),
            "A 'Part-Time Adult' registrant is excluded by default while the youth survives.",
            "scout_schedule_cli.load_inputs line 249",
        ),
        InputSpec(
            format="csv",
            variant="filter-part-time-adult",
            headers=NAME_URL_TYPE_HEADERS,
            rows=(
                (NAME_A, URL_A, "Youth"),
                (NAME_B, URL_B, "Part-Time Adult"),
            ),
        ),
        InputObservation(records=((NAME_A, URL_A, "Youth"),)),
    ),
    InputCase(
        _meta(
            "IN-FILTER-006",
            "IN-FILTER",
            "include-adults",
            ("csv",),
            "With include_adults set, the sole Adult row survives the load_inputs filter.",
            "scout_schedule_cli.load_inputs line 249",
        ),
        InputSpec(
            format="csv",
            variant="filter-include-adults",
            headers=NAME_URL_TYPE_HEADERS,
            rows=((NAME_B, URL_B, "Adult"),),
            include_adults=True,
        ),
        InputObservation(records=((NAME_B, URL_B, "Adult"),)),
    ),
)

_DEDUP_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-DEDUP-001",
            "IN-DEDUP",
            "duplicate-url",
            ("csv",),
            "Two rows sharing one URL collapse to the first-seen row.",
            "scout_schedule_cli.load_inputs lines 251-253",
        ),
        InputSpec(
            format="csv",
            variant="dedup-duplicate",
            headers=NAME_URL_HEADERS,
            rows=(
                (NAME_A, URL_A),
                (NAME_B, URL_A),
            ),
        ),
        InputObservation(records=((NAME_A, URL_A, ""),)),
    ),
    InputCase(
        _meta(
            "IN-DEDUP-002",
            "IN-DEDUP",
            "distinct-urls",
            ("csv",),
            "One name across two distinct URLs stays as two separate records.",
            "scout_schedule_cli.load_inputs dedupes on URL, not name",
        ),
        InputSpec(
            format="csv",
            variant="dedup-distinct",
            headers=NAME_URL_HEADERS,
            rows=(
                (NAME_A, URL_A),
                (NAME_A, URL_B),
            ),
        ),
        InputObservation(records=((NAME_A, URL_A, ""), (NAME_A, URL_B, ""))),
    ),
)

_EMPTY_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-EMPTY-001",
            "IN-EMPTY",
            "physically-empty",
            ("text",),
            "A physically empty file yields the bounded no-URLs ValueError.",
            "scout_schedule_cli.load_inputs lines 256-257",
        ),
        InputSpec(
            format="text",
            variant="empty-physical",
            text_lines=(),
        ),
        InputObservation(
            exception_type="ValueError",
            message="No ScoutingEvent QR URLs found in <input>",
        ),
    ),
    InputCase(
        _meta(
            "IN-EMPTY-002",
            "IN-EMPTY",
            "all-filtered",
            ("csv",),
            "Rows that are all filtered out yield the same bounded no-URLs ValueError.",
            "scout_schedule_cli.load_inputs lines 256-257",
        ),
        InputSpec(
            format="csv",
            variant="empty-all-filtered",
            headers=NAME_URL_TYPE_HEADERS,
            rows=((NAME_A, URL_A, "Adult"),),
        ),
        InputObservation(
            exception_type="ValueError",
            message="No ScoutingEvent QR URLs found in <input>",
        ),
    ),
)

_IMPORT_CASES: tuple[InputCase, ...] = (
    InputCase(
        _meta(
            "IN-IMPORT-001",
            "IN-IMPORT",
            "base",
            ("subprocess",),
            "With no dependency blocked, importing scout_schedule_cli succeeds and pulls in "
            "openpyxl and playwright.",
            "scout_schedule_cli top-level imports lines 30-31",
        ),
        InputSpec(format="import", variant="import-base", profile="base"),
        InputObservation(
            exception_type=None,
            message="profile=base returncode=0 imported=openpyxl,playwright",
        ),
    ),
    InputCase(
        _meta(
            "IN-IMPORT-002",
            "IN-IMPORT",
            "pdf",
            ("subprocess",),
            "Blocking the PDF stack (fitz, cv2) does not affect the scout_schedule_cli import.",
            "scout_schedule_cli does not import PyMuPDF or opencv",
        ),
        InputSpec(format="import", variant="import-pdf", profile="pdf"),
        InputObservation(
            exception_type=None,
            message="profile=pdf returncode=0 imported=openpyxl,playwright",
        ),
    ),
    InputCase(
        _meta(
            "IN-IMPORT-003",
            "IN-IMPORT",
            "acquisition",
            ("subprocess",),
            "Blocking playwright makes the scout_schedule_cli import fail with ImportError, "
            "since it is a top-level dependency.",
            "scout_schedule_cli imports playwright at module scope line 31",
        ),
        InputSpec(format="import", variant="import-acquisition", profile="acquisition"),
        InputObservation(
            exception_type="ImportError",
            message="profile=acquisition returncode=0 imported=openpyxl",
        ),
    ),
    InputCase(
        _meta(
            "IN-IMPORT-004",
            "IN-IMPORT",
            "all",
            ("subprocess",),
            "Blocking every heavy dependency fails the import at openpyxl before playwright.",
            "scout_schedule_cli imports openpyxl at module scope line 30",
        ),
        InputSpec(format="import", variant="import-all", profile="all"),
        InputObservation(
            exception_type="ImportError",
            message="profile=all returncode=0 imported=",
        ),
    ),
)

INPUT_CASES: tuple[InputCase, ...] = (
    *_FORMAT_CASES,
    *_ALIAS_NAME_CASES,
    *_ALIAS_URL_CASES,
    *_ALIAS_TYPE_CASES,
    *_HEADER_CASES,
    *_XLSX_SHEET_CASES,
    *_XLSX_ERR_CASES,
    *_JSON_CASES,
    *_TEXT_CASES,
    *_FILTER_CASES,
    *_DEDUP_CASES,
    *_EMPTY_CASES,
    *_IMPORT_CASES,
)
