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

# Corpus/registry-domain axes (Task 16 backfill, Slice 1b Phase A Gate): the tools/verify_corpus.py
# and tests/harnesses/corpus.py seams (CORP-*), plus the tests/matrix/registry.py structural
# self-tests (REG-*, all NEW_ACCEPTANCE -- see tests/matrix/cases/corpus_cases.py's module
# docstring for why they carry no boundary and no execution context).
_CORPUS_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="CORP-SPLIT",
        domain=Domain.CORPUS,
        members=frozenset(
            {
                "mixed-partition",
                "schema-independent",
                "both-predicates-unrecognized",
                "non-mapping-row",
            }
        ),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"CORP-B-CLASSIFY", "CORP-B-SUMMARIZE"}),
    ),
    AxisSpec(
        axis_id="CORP-CLI",
        domain=Domain.CORPUS,
        members=frozenset({"valid-output", "missing-corpus"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"CORP-B-MAIN"}),
    ),
    AxisSpec(
        axis_id="CORP-FP",
        domain=Domain.CORPUS,
        members=frozenset(
            {"unchanged-equal", "changed-unequal", "symlink-unsafe", "timestamp-mode-invariant"}
        ),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"CORP-B-FINGERPRINT"}),
    ),
    AxisSpec(
        axis_id="CORP-READ",
        domain=Domain.CORPUS,
        members=frozenset({"permission-denied-unreadable"}),
        min_focused_cases=1,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"CORP-B-FINGERPRINT"}),
    ),
    AxisSpec(
        axis_id="CORP-CANON",
        domain=Domain.CORPUS,
        members=frozenset({"canonical-payload-split"}),
        min_focused_cases=1,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"CORP-B-SUMMARIZE"}),
    ),
    AxisSpec(
        axis_id="CORP-PDF",
        domain=Domain.CORPUS,
        members=frozenset({"pdf-extraction-aggregate"}),
        min_focused_cases=1,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"CORP-B-PDF-AGGREGATE"}),
    ),
    AxisSpec(
        axis_id="CORP-SNAPSHOT",
        domain=Domain.CORPUS,
        members=frozenset({"three-runs-share-multiset", "changed-payload-breaks-equality"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"CORP-B-MULTISET"}),
    ),
    AxisSpec(
        axis_id="CORP-MODE",
        domain=Domain.CORPUS,
        members=frozenset({"absent", "present", "empty-and-wrong-layout", "alternate-root"}),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"CORP-B-CORPUS-STATUS"}),
    ),
)

_REGISTRY_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="REG-ID",
        domain=Domain.CORPUS,
        members=frozenset({"same-case-two-contexts", "duplicate-case-ids"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
    AxisSpec(
        axis_id="REG-AXIS",
        domain=Domain.CORPUS,
        members=frozenset(
            {
                "unknown-axis",
                "missing-member",
                "too-few-cases",
                "missing-interaction",
                "unmapped-boundary",
                "unreviewed-exclusion",
            }
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
    AxisSpec(
        axis_id="REG-META",
        domain=Domain.CORPUS,
        members=frozenset(
            {
                "blank-rationale",
                "incomplete-evidence",
                "missing-owner",
                "incomplete-intentional-change",
                "policy-mismatch",
            }
        ),
        min_focused_cases=5,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
    AxisSpec(
        axis_id="REG-LANE",
        domain=Domain.CORPUS,
        members=frozenset(
            {
                "empty-required-set",
                "deselected-required-key",
                "skipped-required-key",
                "duplicated-required-key",
                "missing-required-key",
            }
        ),
        min_focused_cases=5,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
)

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
        members=frozenset({"file", "directory", "glob", "recursive", "overlapping", "missing"}),
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
            {"normalize-cody", "normalization-disabled", "preserve-mcarthur", "preserve-aj"}
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

# Acquisition-domain axes (Task 19). Each member set is exhaustive for the behavior it names.
# ``boundaries`` name the scout_schedule_cli acquisition seams and the assert_egress_allowed
# network-policy boundary an axis exercises. ACQ-BREAKER / ACQ-RESUME / NET-WIRE members are
# new-acceptance placeholders owned by Slice 2 -- they carry no current boundary since nothing
# in the current branch implements a breaker, a resumable checkpoint, or an extracted gateway.
_ACQUISITION_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="ACQ-RESP",
        domain=Domain.ACQUISITION,
        members=frozenset({"correct", "wrong-url", "wrong-method", "wrong-body"}),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-IS-SCHEDULE-RESPONSE", "ACQ-B-NAVIGATE"}),
    ),
    AxisSpec(
        axis_id="ACQ-ID",
        domain=Domain.ACQUISITION,
        members=frozenset({"present", "absent", "blank", "repeated-last-wins"}),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-FORM-VALUES"}),
    ),
    AxisSpec(
        axis_id="ACQ-SCHED",
        domain=Domain.ACQUISITION,
        members=frozenset(
            {"empty-data", "one-class", "multiple-classes", "failed-status", "missing-data"}
        ),
        min_focused_cases=5,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-PROCESS-SCOUT"}),
    ),
    AxisSpec(
        axis_id="ACQ-DEDUP",
        domain=Domain.ACQUISITION,
        members=frozenset(
            {
                "unique-ids",
                "missing-ids",
                "incomplete-to-complete",
                "complete-to-incomplete",
                "equal-duplicate",
            }
        ),
        min_focused_cases=5,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-PROCESS-SCOUT"}),
    ),
    AxisSpec(
        axis_id="ACQ-HASREQ",
        domain=Domain.ACQUISITION,
        members=frozenset({"has-req-1", "has-req-0", "blank-class-id"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-PROCESS-SCOUT"}),
    ),
    AxisSpec(
        axis_id="ACQ-REQ",
        domain=Domain.ACQUISITION,
        members=frozenset(
            {
                "success",
                "failed-status",
                "empty-data",
                "missing-fields",
                "unknown-fields",
                "non-list-data",
            }
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-POST-REQUIREMENT"}),
    ),
    AxisSpec(
        axis_id="ACQ-RETRY",
        domain=Domain.ACQUISITION,
        members=frozenset({"immediate-success", "two-failures-then-success", "three-failures"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-POST-REQUIREMENT"}),
    ),
    AxisSpec(
        axis_id="ACQ-DELAY",
        domain=Domain.ACQUISITION,
        members=frozenset({"zero-delay", "positive-delay"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-POST-REQUIREMENT"}),
    ),
    AxisSpec(
        axis_id="ACQ-RAW",
        domain=Domain.ACQUISITION,
        members=frozenset({"schedule-file", "requirement-file", "distinct-uuid-filenames"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-OUTPUT-ID"}),
    ),
    AxisSpec(
        axis_id="ACQ-CLEAN",
        domain=Domain.ACQUISITION,
        members=frozenset({"success", "schedule-exception", "terminal-requirement-failure"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-PROCESS-SCOUT", "ACQ-B-ASYNC-MAIN"}),
    ),
    AxisSpec(
        axis_id="ACQ-ASSET",
        domain=Domain.ACQUISITION,
        members=frozenset({"dead-asset-aborted", "allowed-dead-asset"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-PROCESS-SCOUT"}),
    ),
    AxisSpec(
        axis_id="ACQ-IDENTITY",
        domain=Domain.ACQUISITION,
        members=frozenset({"missing-id-fails-closed", "uuidv4-stable", "runs-unlinkable"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-OUTPUT-ID"}),
    ),
    AxisSpec(
        axis_id="ACQ-BREAKER",
        domain=Domain.ACQUISITION,
        members=frozenset({"below-threshold", "threshold-opens", "recovery-resets"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
    AxisSpec(
        axis_id="ACQ-RESUME",
        domain=Domain.ACQUISITION,
        members=frozenset(
            {
                "new-checkpoint",
                "completed-not-repeated",
                "uuid-survives-resume",
                "corrupt-checkpoint-fails-closed",
            }
        ),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
    AxisSpec(
        axis_id="FAKE-STRICT",
        domain=Domain.ACQUISITION,
        members=frozenset(
            {
                "wrong-attendee-id",
                "wrong-class-id",
                "wrong-order",
                "wrong-delay",
                "unexpected-retry",
                "extra-call",
                "unconsumed-response",
            }
        ),
        min_focused_cases=7,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
    AxisSpec(
        axis_id="BROWSER-LOCAL",
        domain=Domain.ACQUISITION,
        members=frozenset(
            {
                "capture-schedule-post",
                "serve-requirement-json",
                "real-interception",
                "full-local-success",
            }
        ),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
    AxisSpec(
        axis_id="BROWSER-EGRESS",
        domain=Domain.ACQUISITION,
        members=frozenset(
            {"navigation", "redirect", "frame", "popup", "worker-fetch", "websocket", "download"}
        ),
        min_focused_cases=7,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
    AxisSpec(
        axis_id="NET-POLICY",
        domain=Domain.ACQUISITION,
        members=frozenset({"loopback-allowed", "non-loopback-denied", "opt-in-allowed"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ACQ-B-EGRESS"}),
    ),
    AxisSpec(
        axis_id="NET-WIRE",
        domain=Domain.ACQUISITION,
        members=frozenset({"http-gateway-consults-policy", "playwright-gateway-consults-policy"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
)

# Requirement-domain axes (Task 20): the requirement-inference seams in scout_schedule_cli
# (requirement_path, choice_requirement_count, annotate_requirement_statuses,
# build_missing_requirements, render_email_text, render_email_html).
_REQUIREMENT_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="REQ-SHAPE",
        domain=Domain.REQUIREMENT,
        members=frozenset({f"shape-{i:02d}" for i in range(1, 27)}),
        min_focused_cases=26,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"REQ-B-PATH", "REQ-B-ANNOTATE"}),
    ),
    AxisSpec(
        axis_id="REQ-FLAG",
        domain=Domain.REQUIREMENT,
        members=frozenset(
            {
                "req-true-class-true",
                "req-true-class-false",
                "req-false-class-true",
                "req-false-class-false",
            }
        ),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"REQ-B-ANNOTATE"}),
    ),
    AxisSpec(
        axis_id="REQ-TYPE",
        domain=Domain.REQUIREMENT,
        members=frozenset({"type-1", "type-2", "type-3"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"REQ-B-ANNOTATE"}),
    ),
    AxisSpec(
        axis_id="REQ-CLASS",
        domain=Domain.REQUIREMENT,
        members=frozenset({"incomplete-class", "complete-class"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
    AxisSpec(
        axis_id="REQ-EMPTY",
        domain=Domain.REQUIREMENT,
        members=frozenset({"no-top-level-seen", "after-top-level-seen"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"REQ-B-PATH"}),
    ),
    AxisSpec(
        axis_id="REQ-NOTE",
        domain=Domain.REQUIREMENT,
        members=frozenset({"after-numbered", "at-beginning"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"REQ-B-PATH", "REQ-B-ANNOTATE"}),
    ),
    AxisSpec(
        axis_id="REQ-TREE",
        domain=Domain.REQUIREMENT,
        members=frozenset(
            {"leaf", "parent", "grandparent", "missing-parent", "malformed-numbering", "label-only"}
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"REQ-B-ANNOTATE"}),
    ),
    AxisSpec(
        axis_id="REQ-CHOICE",
        domain=Domain.REQUIREMENT,
        members=frozenset(
            f"{verb}-{phrasing}-{relation}"
            for verb in ("do", "complete", "choose", "select", "perform")
            for phrasing in ("digit", "word")
            for relation in ("below", "equal", "above")
        ),
        min_focused_cases=30,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"REQ-B-CHOICE", "REQ-B-ANNOTATE"}),
    ),
    AxisSpec(
        axis_id="REQ-EXCLUDE",
        domain=Domain.REQUIREMENT,
        members=frozenset({"not-used", "type-3"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"REQ-B-MISSING"}),
    ),
    AxisSpec(
        axis_id="REQ-NONMUTATE",
        domain=Domain.REQUIREMENT,
        members=frozenset({"valid-tree", "malformed-tree"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"REQ-B-ANNOTATE"}),
    ),
    AxisSpec(
        axis_id="REQ-IDENTITY",
        domain=Domain.REQUIREMENT,
        members=frozenset({"same-name-different-id", "same-id-groups", "blank-id-fallback"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"REQ-B-ANNOTATE"}),
    ),
)

# Artifact-domain axes (Task 20): output writers, HTML/email rendering safety, filename
# generation, formula-injection surface, and publication-failure injection seams.
_ARTIFACT_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="ART-SCHEMA",
        domain=Domain.ARTIFACT,
        members=frozenset(
            {
                "scouts-json",
                "classes-csv",
                "requirements-csv",
                "errors-csv",
                "summary-json",
                "report-data",
                "email-csv",
                "email-text-html",
            }
        ),
        min_focused_cases=8,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ART-B-WRITE-OUTPUTS", "ART-B-HTML-REPORT", "ART-B-EMAIL"}),
    ),
    AxisSpec(
        axis_id="ART-HTML",
        domain=Domain.ARTIFACT,
        members=frozenset(
            {
                "xss-sentinel",
                "script-close-tag",
                "angle-amp",
                "line-para-separators",
                "non-ascii-unicode",
            }
        ),
        min_focused_cases=5,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ART-B-JSON-FOR-HTML"}),
    ),
    AxisSpec(
        axis_id="ART-EMAIL",
        domain=Domain.ARTIFACT,
        members=frozenset(
            {"missing-requirements", "all-complete", "no-data", "same-name-disambiguation"}
        ),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ART-B-EMAIL"}),
    ),
    AxisSpec(
        axis_id="ART-NAME",
        domain=Domain.ARTIFACT,
        members=frozenset(
            {
                "path-traversal",
                "absolute-path",
                "unicode-name",
                "case-collision",
                "windows-reserved",
                "empty-name",
                "symlinked-root",
                "duplicate-display-name",
                "duplicate-html-filename",
            }
        ),
        min_focused_cases=9,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ART-B-FILENAME"}),
    ),
    AxisSpec(
        axis_id="ART-FORMULA",
        domain=Domain.ARTIFACT,
        members=frozenset(
            {"eq-prefix", "plus-prefix", "minus-prefix", "at-prefix", "tab-prefix", "cr-prefix"}
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ART-B-WRITE-CSV"}),
    ),
    AxisSpec(
        axis_id="ART-FAIL",
        domain=Domain.ARTIFACT,
        members=frozenset(
            {
                "before-render",
                "during-temp-write",
                "before-atomic-replace",
                "after-atomic-replace",
                "during-cleanup",
                "partial-multi-file",
            }
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"ART-B-ATOMIC-WRITE"}),
    ),
    AxisSpec(
        axis_id="PRIV-SURFACE",
        domain=Domain.ARTIFACT,
        members=frozenset(
            {
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
            }
        ),
        min_focused_cases=12,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
    AxisSpec(
        axis_id="PRIV-EGRESS",
        domain=Domain.ARTIFACT,
        members=frozenset(
            {
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
            }
        ),
        min_focused_cases=10,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
    AxisSpec(
        axis_id="PRIV-CONTAIN",
        domain=Domain.ARTIFACT,
        members=frozenset({"adapter-file-stays-in-root", "no-private-field-reaches-shareable"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset(),
    ),
)

# Platform-domain axes (Task 21): the pure Windows/macOS path-shaped characterization of
# scout_schedule_cli.safe_slug (see tests/matrix/cases/platform_cases.py's module docstring for
# the full hand-traced algorithm). PURE simulated observations only -- no sys.platform
# monkeypatching, no real OS/filesystem/installer claims.
_PLATFORM_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="PLAT-WIN",
        domain=Domain.PLATFORM,
        members=frozenset(
            {
                "reserved-device-name",
                "trailing-dot-space",
                "case-collision",
                "slash-backslash",
                "drive-letter",
                "unc-path",
                "extended-length-path",
                "traversal",
            }
        ),
        min_focused_cases=8,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"PLAT-B-SLUG"}),
    ),
    AxisSpec(
        axis_id="PLAT-MAC",
        domain=Domain.PLATFORM,
        members=frozenset(
            {
                "nfc-nfd-equivalence",
                "case-collision",
                "volume-root",
                "spaces-and-unicode",
                "traversal",
            }
        ),
        min_focused_cases=5,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"PLAT-B-SLUG"}),
    ),
)

# Interface-domain axes (Task 21): ui/server.py's FastAPI app. UI-ROUTE now covers all 30 members:
# the original 23 whose contract doesn't require draining a background worker, the 6 that do
# (PDF/schedule "accepted"/"worker-error", events "success"/"disconnect"), plus one
# INTENTIONAL_CHANGE member (open_report's unvalidated persisted-JSON report_name). SSE-FRAME and
# SSE-CLEAN characterize the real StreamingResponse.body_iterator's frame sequence and lifecycle
# cleanup. Every member declared here IS backed by a real, passing case in
# tests/matrix/cases/interface_cases.py.
_INTERFACE_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="UI-IMPORT",
        domain=Domain.INTERFACE,
        members=frozenset({"sandbox-root-only", "real-root-untouched"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"UI-B-IMPORT"}),
    ),
    AxisSpec(
        axis_id="UI-METHOD",
        domain=Domain.INTERFACE,
        members=frozenset(
            {
                "/api/health",
                "/api/status",
                "/api/scouts",
                "/api/pdf-extract",
                "/api/schedule-download",
                "/api/schedule-download/pause",
                "/api/schedule-download/resume",
                "/api/operations/OP-ID/events",
                "/api/runs",
                "/api/runs/RUN-ID/open-report",
                "/api/runs/RUN-ID/generate-emails",
                "/api/runs/RUN-ID/open-emails-folder",
            }
        ),
        min_focused_cases=12,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"UI-B-ROUTES"}),
    ),
    AxisSpec(
        axis_id="RUN-ID",
        domain=Domain.INTERFACE,
        members=frozenset({"valid", "traversal", "absolute", "separator-containing"}),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"UI-B-SAFE-RUN-ID"}),
    ),
    AxisSpec(
        axis_id="RUN-LIST",
        domain=Domain.INTERFACE,
        members=frozenset(
            {
                "empty",
                "reverse-sorted-multiple",
                "corrupt-summary-ignored",
                "missing-optional-report",
            }
        ),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"UI-B-LIST-RUNS"}),
    ),
    AxisSpec(
        axis_id="CLI-SCHED",
        domain=Domain.INTERFACE,
        members=frozenset(
            {
                "defaults-help",
                "empty-success",
                "one-scout-success",
                "partial-failure",
                "top-level-exception",
                "keyboard-interrupt",
            }
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        # PDF-B-MAIN is referenced here (not just under the PDF-domain axes) to give the
        # interface domain's CLI accounting a cross-reference to pdf_to_scouts.main's own
        # already-fully-characterized PDF-CLI-* cases (Task 18) -- this axis's OWN member set
        # only claims scout_schedule_cli.main's 6 members above; PDF-B-MAIN's required_case_ids
        # remain PDF-domain cases and are not duplicated or re-asserted here. A boundary's
        # domain describes the case domain it maps to (registry.py's _validate_boundaries), not
        # which axis/task references it, so referencing a PDF-domain boundary from an
        # INTERFACE-domain axis is registry-valid: _validate_axes only checks that the boundary
        # id exists, never that its domain matches the referencing axis.
        boundaries=frozenset({"CLI-B-MAIN", "PDF-B-MAIN"}),
    ),
    AxisSpec(
        axis_id="UI-ROUTE",
        domain=Domain.INTERFACE,
        members=frozenset(
            {
                "health-success",
                "status-absent",
                "status-present",
                "scouts-absent",
                "scouts-present",
                "pdf-no-files",
                "pdf-busy",
                "schedule-missing",
                "schedule-busy",
                "pause-inactive",
                "pause-active",
                "resume-inactive",
                "resume-active",
                "events-missing",
                "runs-empty",
                "open-report-missing",
                "open-report-no-report",
                "open-report-success",
                "email-missing",
                "email-success",
                "email-corrupt-json",
                "open-folder-missing",
                "open-folder-success",
                "pdf-accepted",
                "pdf-worker-error",
                "schedule-accepted",
                "schedule-worker-error",
                "events-success",
                "events-disconnect",
                "open-report-unvalidated-report-name",
            }
        ),
        min_focused_cases=30,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"UI-B-ROUTES"}),
    ),
    AxisSpec(
        axis_id="SSE-FRAME",
        domain=Domain.INTERFACE,
        members=frozenset(
            {
                "zero-scouts-immediate-done",
                "single-scout-success",
                "pause-then-resume",
                "two-scouts-no-pause",
                "worker-exception-mid-batch",
                "two-scouts-one-non-fatal-error",
            }
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"SSE-B-FRAMES"}),
    ),
    AxisSpec(
        axis_id="SSE-CLEAN",
        domain=Domain.INTERFACE,
        members=frozenset(
            {"success", "worker-exception", "terminal-attendee-failure", "client-disconnect"}
        ),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"SSE-B-CLEANUP"}),
    ),
)

# Desktop-launcher and bootstrap axes (Task 21, final slice): run_app.py's free_port /
# wait_until_ready / main dispatch, and bootstrap/paths.py / marker.py / source_sync.py. Reuses
# Domain.PLATFORM (see tests/matrix/cases/desktop_cases.py and bootstrap_cases.py module
# docstrings for the documented reasoning) rather than adding a new Domain member.
_DESKTOP_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="DESK-PORT",
        domain=Domain.PLATFORM,
        members=frozenset({"free-port-closed-cleanly", "bind-conflict-surfaces"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"DESK-B-PORT"}),
    ),
    AxisSpec(
        axis_id="DESK-READY",
        domain=Domain.PLATFORM,
        members=frozenset({"immediate-success", "retries-then-success", "timeout-gives-up"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"DESK-B-READY"}),
    ),
    AxisSpec(
        axis_id="DESK-MODE",
        domain=Domain.PLATFORM,
        members=frozenset(
            {
                "browser-mode",
                "native-mode",
                "server-start-failure-propagates",
                "keyboard-interrupt-during-browser-wait",
            }
        ),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"DESK-B-MODE"}),
    ),
)

_BOOTSTRAP_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="BOOT-PATH",
        domain=Domain.PLATFORM,
        members=frozenset({"override", "default", "spaces-in-path", "unicode-in-path"}),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"BOOT-B-PATH"}),
    ),
    AxisSpec(
        axis_id="BOOT-MARK",
        domain=Domain.PLATFORM,
        members=frozenset(
            {
                "missing",
                "valid",
                "corrupt-json",
                "schema-version-mismatch",
                "python-version-mismatch",
                "requirements-hash-mismatch",
            }
        ),
        min_focused_cases=6,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"BOOT-B-MARKER"}),
    ),
    AxisSpec(
        axis_id="BOOT-SYNC",
        domain=Domain.PLATFORM,
        members=frozenset(
            {
                "single-file",
                "whole-directory",
                "missing-source-raises",
                "frozen-vs-unfrozen-source-root",
            }
        ),
        min_focused_cases=4,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"BOOT-B-SYNC"}),
    ),
)

# Scale-profile axes (Task 22, Slice 1b Phase A): the deterministic synthetic-data-profile and
# pairing characterization in tests/scale/test_profiles.py, driving tests/matrix/scale_profile.py
# and tests/factories/scale.py directly (never the legacy application).
_SCALE_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="SCALE-PROFILE",
        domain=Domain.SCALE,
        members=frozenset(
            {
                "zero",
                "one",
                "shared-name-distinct-ids",
                "small-grouped",
                "small-reversed",
                "small-interleaved",
                "canonical-022",
                "large-050",
                "prop-001",
                "prop-002",
            }
        ),
        min_focused_cases=10,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"SCALE-B-BUILD-DATASET"}),
    ),
    AxisSpec(
        axis_id="SCALE-PAIR",
        domain=Domain.SCALE,
        members=frozenset({"reorder-independent", "correlation-unsupported"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"SCALE-B-PAIRING"}),
    ),
)

# Vertical-flow and performance-baseline axes (Task 22, Slice 1b Phase A): the real 5-stage
# end-to-end wire-up in tests/vertical/test_legacy_flows.py, plus the request-count/growth-bound
# characterization in tests/performance/test_phase_a_baseline.py. FLOW-BROWSER-001 is a
# new-acceptance placeholder (see tests/matrix/cases/scale_cases.py's module docstring) owned by
# the second part of Task 22 -- out of scope here.
_FLOW_AXES: tuple[AxisSpec, ...] = (
    AxisSpec(
        axis_id="FLOW-VERTICAL",
        domain=Domain.FLOW,
        members=frozenset({"success", "partial-failure", "browser-e2e"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"FLOW-B-END-TO-END"}),
    ),
    AxisSpec(
        axis_id="PERF-REQUEST",
        domain=Domain.FLOW,
        members=frozenset({"zero", "canonical", "large"}),
        min_focused_cases=3,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"FLOW-B-REQUEST-COUNT"}),
    ),
    AxisSpec(
        axis_id="PERF-GROWTH",
        domain=Domain.FLOW,
        members=frozenset({"growth-bound", "artifact-rows"}),
        min_focused_cases=2,
        interactions=_NO_INTERACTIONS,
        boundaries=frozenset({"FLOW-B-GROWTH"}),
    ),
)

# Domain axes are declared by later slices (Tasks 19-21) and appended here.
AXES: tuple[AxisSpec, ...] = (
    _CORPUS_AXES
    + _REGISTRY_AXES
    + _INPUT_AXES
    + _PDF_AXES
    + _ACQUISITION_AXES
    + _REQUIREMENT_AXES
    + _ARTIFACT_AXES
    + _PLATFORM_AXES
    + _INTERFACE_AXES
    + _DESKTOP_AXES
    + _BOOTSTRAP_AXES
    + _SCALE_AXES
    + _FLOW_AXES
)
