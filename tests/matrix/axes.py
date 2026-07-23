from __future__ import annotations

from dataclasses import dataclass

from tests.matrix.model import Domain


@dataclass(frozen=True, slots=True)
class AxisSpec:
    axis_id: str
    domain: Domain
    members: frozenset[str]
    min_focused_cases: int
    interactions: frozenset[str]
    boundaries: frozenset[str]


_NO_INTERACTIONS: frozenset[str] = frozenset()

# Input-domain axes (Task 17). Each member set is exhaustive for the behavior it names, and
# ``min_focused_cases`` equals the member count because the catalog declares exactly one
# focused case per member. ``boundaries`` name the load_* seams the axis exercises.
_INPUT_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="IN-FORMAT",
        domain=Domain.INPUT,
        members=frozenset(
            {
                "csv",
                "xlsx",
                "json-list",
                "json-scouts",
                "json-data",
                "json-mapping",
                "json-string-row",
                "text",
            }
        ),
        min_focused_cases=8,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(
            {
                "IN-B-LOAD-INPUTS",
                "IN-B-LOAD-CSV",
                "IN-B-LOAD-XLSX",
                "IN-B-LOAD-JSON",
                "IN-B-LOAD-TEXT",
            }
        ),
    ),
    AxisSpec(
        axis_id="IN-ALIAS-NAME",
        domain=Domain.INPUT,
        members=frozenset({"attendee-name", "name", "scout-name"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"IN-B-LOAD-CSV", "IN-B-LOAD-XLSX"}),
    ),
    AxisSpec(
        axis_id="IN-ALIAS-URL",
        domain=Domain.INPUT,
        members=frozenset({"qr-code-contents", "url", "qr-url", "link"}),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"IN-B-LOAD-CSV", "IN-B-LOAD-XLSX"}),
    ),
    AxisSpec(
        axis_id="IN-ALIAS-TYPE",
        domain=Domain.INPUT,
        members=frozenset({"registrant-type", "type"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"IN-B-LOAD-CSV", "IN-B-LOAD-XLSX"}),
    ),
    AxisSpec(
        axis_id="IN-HEADER",
        domain=Domain.INPUT,
        members=frozenset({"utf8-bom", "normalization", "whitespace", "unknown"}),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"IN-B-LOAD-CSV", "IN-B-LOAD-INPUTS"}),
    ),
    AxisSpec(
        axis_id="IN-XLSX-SHEET",
        domain=Domain.INPUT,
        members=frozenset({"requested", "scouts-only", "first"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"IN-B-LOAD-XLSX", "IN-B-LOAD-INPUTS"}),
    ),
    AxisSpec(
        axis_id="IN-XLSX-ERR",
        domain=Domain.INPUT,
        members=frozenset({"empty-workbook", "missing-url"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"IN-B-LOAD-XLSX"}),
    ),
    AxisSpec(
        axis_id="IN-JSON",
        domain=Domain.INPUT,
        members=frozenset(
            {
                "name-aliases",
                "url-aliases",
                "type-aliases",
                "string-item",
                "invalid-item",
                "malformed-top",
            }
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"IN-B-LOAD-JSON"}),
    ),
    AxisSpec(
        axis_id="IN-TEXT",
        domain=Domain.INPUT,
        members=frozenset({"url-only", "name-url", "blank-comment", "comma-no-https"}),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"IN-B-LOAD-TEXT"}),
    ),
    AxisSpec(
        axis_id="IN-FILTER",
        domain=Domain.INPUT,
        members=frozenset(
            {
                "valid-prefix",
                "invalid-scheme",
                "invalid-host-path",
                "adult",
                "part-time-adult",
                "include-adults",
            }
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"IN-B-LOAD-INPUTS"}),
    ),
    AxisSpec(
        axis_id="IN-DEDUP",
        domain=Domain.INPUT,
        members=frozenset({"duplicate-url", "distinct-urls"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"IN-B-LOAD-INPUTS"}),
    ),
    AxisSpec(
        axis_id="IN-EMPTY",
        domain=Domain.INPUT,
        members=frozenset({"physically-empty", "all-filtered"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"IN-B-LOAD-INPUTS"}),
    ),
    AxisSpec(
        axis_id="IN-IMPORT",
        domain=Domain.INPUT,
        members=frozenset({"base", "pdf", "acquisition", "all"}),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
)

# PDF-domain axes (Task 18). Each member set is exhaustive for the behavior it names, and
# ``min_focused_cases`` equals the member count because the catalog declares exactly one focused
# case per member. ``boundaries`` name the pdf_to_scouts seams the axis exercises.
_PDF_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="PDF-DISC",
        domain=Domain.PDF,
        members=frozenset(
            {"file", "directory", "glob", "recursive", "overlapping", "missing"}
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"PDF-B-EXPAND"}),
    ),
    AxisSpec(
        axis_id="PDF-ID",
        domain=Domain.PDF,
        members=frozenset(
            {
                "all-fields",
                "missing-name",
                "missing-type",
                "missing-qr",
                "missing-name-type",
                "name-qr",
                "type-qr",
                "all-missing",
            }
        ),
        min_focused_cases=8,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"PDF-B-IDENTITY", "PDF-B-EXTRACT"}),
    ),
    AxisSpec(
        axis_id="PDF-CASE",
        domain=Domain.PDF,
        members=frozenset(
            {"normalize-miles", "normalization-disabled", "preserve-mcdonald", "preserve-aj"}
        ),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"PDF-B-NORMALIZE"}),
    ),
    AxisSpec(
        axis_id="PDF-QR",
        domain=Domain.PDF,
        members=frozenset(
            {"embedded", "rendered", "preferred", "first-other", "multi-symbol", "total-failure"}
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"PDF-B-EMBEDDED", "PDF-B-RENDERED"}),
    ),
    AxisSpec(
        axis_id="PDF-PAGE",
        domain=Domain.PDF,
        members=frozenset({"multipage-order", "multi-pdf-order"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"PDF-B-EXTRACT"}),
    ),
    AxisSpec(
        axis_id="PDF-CORRUPT",
        domain=Domain.PDF,
        members=frozenset({"corrupt-open", "corrupt-embedded"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"PDF-B-EXTRACT"}),
    ),
    AxisSpec(
        axis_id="PDF-DEBUG",
        domain=Domain.PDF,
        members=frozenset({"with-root", "without-root"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"PDF-B-RENDERED"}),
    ),
    AxisSpec(
        axis_id="PDF-FILTER",
        domain=Domain.PDF,
        members=frozenset(
            {
                "default-adult",
                "custom-adult",
                "include-adults",
                "scoutingevent-only",
                "duplicate-removed",
                "duplicates-retained",
            }
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"PDF-B-MAIN", "PDF-B-ATTENDEE-CSV"}),
    ),
    AxisSpec(
        axis_id="PDF-SCHEMA",
        domain=Domain.PDF,
        members=frozenset({"attendee-columns", "error-columns"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"PDF-B-ATTENDEE-CSV", "PDF-B-ERRORS-CSV"}),
    ),
    AxisSpec(
        axis_id="PDF-CLI",
        domain=Domain.PDF,
        members=frozenset(
            {
                "help",
                "no-match",
                "dpi-low",
                "dpi-high",
                "success",
                "strict-exit",
                "quiet",
                "stale",
            }
        ),
        min_focused_cases=8,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"PDF-B-MAIN", "PDF-B-EXPAND", "PDF-B-ERRORS-CSV"}),
    ),
)

# Domain axes are declared by later slices (Tasks 19-21) and appended here.
AXES: tuple[AxisSpec, ...] = _INPUT_AXES + _PDF_AXES
