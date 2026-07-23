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

# Domain axes are declared by later slices (Tasks 18-21) and appended here.
AXES: tuple[AxisSpec, ...] = _INPUT_AXES
