"""Scale-profile and vertical-flow characterization catalog (Task 22, Slice 1b Phase A).

There is no dedicated ``ScaleCase``/``FlowCase`` shape here -- like ``FAKE-STRICT-*`` /
``BROWSER-EGRESS-*`` in ``tests/matrix/cases/acquisition_cases.py``, these are plain
``CaseMetadata`` rows; the matching test modules (``tests/scale/test_profiles.py``,
``tests/vertical/test_legacy_flows.py``, ``tests/performance/test_phase_a_baseline.py``) each
drive the real ``tests.matrix.scale_profile`` / ``tests.factories.scale`` primitives and/or the
real production pipeline directly, dispatching by hand rather than through
``tests.matrix.pytest_support.execution_params``.

``FLOW-BROWSER-001`` is a ``NEW_ACCEPTANCE`` placeholder: it belongs to the SECOND part of Task 22
(a real Playwright browser drives the acquisition layer end to end), which is out of scope here.
"""

from __future__ import annotations

from tests.matrix.model import CaseMetadata, Classification, Domain, EvidenceKind


def _meta(
    case_id: str,
    axis_id: str,
    member: str,
    context: str,
    rationale: str,
    evidence_reference: str,
    *,
    domain: Domain = Domain.SCALE,
    classification: Classification = Classification.PRESERVE,
    target_owner: str | None = None,
    target_observation: str | None = None,
) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id=axis_id,
        member=member,
        domain=domain,
        classification=classification,
        evidence=EvidenceKind.CORPUS_AGGREGATE,
        rationale=rationale,
        contexts=() if classification is Classification.NEW_ACCEPTANCE else (context,),
        evidence_reference=evidence_reference,
        target_owner=target_owner,
        target_observation=target_observation,
    )


SCALE_PROFILE_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "SCALE-000",
        "SCALE-PROFILE",
        "zero",
        "run",
        "A profile with zero attendees builds an empty dataset: no attendees, no deduplicated "
        "classes, no requirement rows -- the base case every partition-total assertion "
        "must hold trivially for.",
        "tests/factories/scale.py build_dataset, zero-attendee profile",
    ),
    _meta(
        "SCALE-001",
        "SCALE-PROFILE",
        "one",
        "run",
        "A profile with one attendee and several classes builds the expected single-attendee "
        "dataset with the requested class/requirement counts.",
        "tests/factories/scale.py build_dataset, one-attendee profile",
    ),
    _meta(
        "SCALE-002",
        "SCALE-PROFILE",
        "shared-name-distinct-ids",
        "run",
        "Two attendees forced to share a display name still get distinct upstream_id and "
        "output_id values and independent class allocations -- a shared name never merges "
        "identity.",
        "tests/factories/scale.py build_dataset name_overrides",
    ),
    _meta(
        "SCALE-SMALL-001",
        "SCALE-PROFILE",
        "small-grouped",
        "run",
        "3 attendees in grouped (natural) ordering is repeatable by profile version and seed: "
        "the same version+seed produces byte-identical output.",
        "tests/factories/scale.py build_dataset, 3-attendee profile, grouped ordering",
    ),
    _meta(
        "SCALE-SMALL-002",
        "SCALE-PROFILE",
        "small-reversed",
        "run",
        "7 attendees in reversed ordering is repeatable by profile version and seed; a "
        "different seed changes ordering-sensitive detail but not partition totals.",
        "tests/factories/scale.py build_dataset, 7-attendee profile, reversed ordering",
    ),
    _meta(
        "SCALE-SMALL-003",
        "SCALE-PROFILE",
        "small-interleaved",
        "run",
        "11 attendees in interleaved ordering is repeatable by profile version and seed, "
        "same as the grouped/reversed members.",
        "tests/factories/scale.py build_dataset, 11-attendee profile, interleaved ordering",
    ),
    _meta(
        "SCALE-CANON-022",
        "SCALE-PROFILE",
        "canonical-022",
        "run",
        "22 attendees / 103 raw / 98 deduplicated classes / 98 requirement payloads / 4858 "
        "requirements reproduces every authoritative Task 16 corpus marginal (flag/type/"
        "shape/raw-completion/deduped-completion/has-req) EXACTLY, as synthetic data.",
        "tools/verify_corpus.py aggregate contract; tests/factories/scale.py canonical_profile",
    ),
    _meta(
        "SCALE-LARGE-050",
        "SCALE-PROFILE",
        "large-050",
        "run",
        "50 attendees with deterministic class allocation/order; the request-count formula "
        "(schedule requests + one requirement request per nonblank deduplicated class id) is "
        "characterized directly against this profile in PERF-REQ-003.",
        "tests/factories/scale.py build_dataset, 50-attendee profile",
    ),
    _meta(
        "SCALE-PROP-001",
        "SCALE-PROFILE",
        "prop-001",
        "run",
        "Bounded Hypothesis-style attendee counts (0-60): stable ordering/grouping with "
        "identity isolation (every attendee's upstream_id/output_id is distinct) for every "
        "generated count.",
        "tests/factories/scale.py build_dataset, Hypothesis-bounded attendee_count",
    ),
    _meta(
        "SCALE-PROP-002",
        "SCALE-PROFILE",
        "prop-002",
        "run",
        "Bounded Hypothesis-style attendee counts (0-60): partition totals (per-attendee class "
        "counts, per-class requirement counts) always sum to the profile's declared totals.",
        "tests/factories/scale.py build_dataset, Hypothesis-bounded attendee_count",
    ),
)

SCALE_PAIR_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "SCALE-PAIR-001",
        "SCALE-PAIR",
        "reorder-independent",
        "run",
        "Reordering one synthetic marginal pairing (changing the seed, which reorders every "
        "SHA-256 pairing) leaves each independent marginal/topology assertion (flag, type, "
        "shape, class-completion) unchanged -- the three requirement-row marginals are paired "
        "independently, not correlated.",
        "tests/matrix/scale_profile.py pairing_order; tests/factories/scale.py _assign_marginal",
    ),
    _meta(
        "SCALE-PAIR-002",
        "SCALE-PAIR",
        "correlation-unsupported",
        "run",
        "Requesting correlation evidence between two independently-generated marginals raises "
        "UnsupportedSyntheticCorrelation -- the generator makes no claim about any relationship "
        "between the flag/type/shape marginals beyond their independently-pinned totals.",
        "tests/matrix/scale_profile.py require_supported CORRELATION guard",
    ),
)

ALL_SCALE_METADATA: tuple[CaseMetadata, ...] = SCALE_PROFILE_METADATA + SCALE_PAIR_METADATA


FLOW_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "FLOW-SUCCESS-001",
        "FLOW-VERTICAL",
        "success",
        "run",
        "A generated PDF (Task 18's build_pdf) flows through the REAL "
        "pdf_to_scouts.extract_pdf/write_attendees_csv, the REAL "
        "scout_schedule_cli.load_inputs, REAL process_scout driven by Task 19's strict "
        "acquisition fakes, REAL annotate_requirement_statuses/write_outputs, and REAL UI "
        "read routes (Task 21's load_legacy_ui harness) reading the generated output "
        "directory -- five real production stages wired end to end, never mocked.",
        "scout_schedule_cli.py process_scout/write_outputs; pdf_to_scouts.py extract_pdf; "
        "ui/server.py read routes",
        domain=Domain.FLOW,
    ),
    _meta(
        "FLOW-PARTIAL-001",
        "FLOW-VERTICAL",
        "partial-failure",
        "run",
        "Two attendees where one hits a terminal (non-retryable) acquisition failure: the "
        "batch still completes with a partial result -- exact exit code, exact error record "
        "for the failed attendee, exact per-attendee artifact presence, and clean fake-context "
        "closure for both attendees.",
        "scout_schedule_cli.py process_scout error handling; async_main partial-batch behavior",
        domain=Domain.FLOW,
    ),
    _meta(
        "FLOW-BROWSER-001",
        "FLOW-VERTICAL",
        "browser-e2e",
        "run",
        "A real-Playwright-browser-driven end-to-end acquisition flow is owned by the SECOND "
        "part of Task 22 (out of scope for this Slice 1b Phase A part) -- declared here only "
        "as a metadata placeholder so the FLOW-VERTICAL axis's member set stays exhaustive.",
        "Task 22 plan: 'do NOT attempt it, it needs a Playwright browser'",
        domain=Domain.FLOW,
        classification=Classification.NEW_ACCEPTANCE,
        target_owner="Task 22 part 2 (Slice 1b Phase B)",
        target_observation="A guarded real-Chromium acquisition round trip against a loopback "
        "fake service, reusing tests/harnesses/browser.py, exercising the full "
        "pdf->csv->acquire->report pipeline.",
    ),
)

PERF_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "PERF-REQ-001",
        "PERF-REQUEST",
        "zero",
        "run",
        "Zero attendees produce zero schedule requests and zero requirement requests -- the "
        "request-count formula's base case.",
        "scout_schedule_cli.py process_scout request sequence",
        domain=Domain.FLOW,
    ),
    _meta(
        "PERF-REQ-002",
        "PERF-REQUEST",
        "canonical",
        "run",
        "The canonical (22-attendee) profile's real strict-fake call count equals schedule "
        "requests (one per attendee) plus one requirement request per nonblank deduplicated "
        "class id -- including HAS_REQ='0' classes, matching ACQ-HASREQ-002's characterized "
        "current legacy behavior (requirements are requested regardless of HAS_REQ).",
        "scout_schedule_cli.py process_scout, ACQ-HASREQ-002",
        domain=Domain.FLOW,
    ),
    _meta(
        "PERF-REQ-003",
        "PERF-REQUEST",
        "large",
        "run",
        "The large (50-attendee) profile's real strict-fake call count equals schedule "
        "requests plus one requirement request per nonblank deduplicated class id, same "
        "formula as the canonical and zero cases -- a growth check across three scales.",
        "scout_schedule_cli.py process_scout request sequence",
        domain=Domain.FLOW,
    ),
    _meta(
        "PERF-GROWTH-001",
        "PERF-GROWTH",
        "growth-bound",
        "run",
        "For profiles of 11, 22, and 50 requirement rows, path/tree node visits during real "
        "annotate_requirement_statuses execution (instrumented via a counting monkeypatch "
        "wrapper around requirement_path/choice_requirement_count) are at most "
        "6*requirement_rows + 2*class_rows -- a growth-bound check, not an exact count.",
        "scout_schedule_cli.py annotate_requirement_statuses recursive calculate()",
        domain=Domain.FLOW,
    ),
    _meta(
        "PERF-GROWTH-002",
        "PERF-GROWTH",
        "artifact-rows",
        "run",
        "Generated artifact data rows (scouts.json entries + classes.csv + requirements.csv + "
        "errors.csv rows) equal attendees + classes + requirements + errors; serialized files "
        "remain the fixed schema count plus one conditional email file per attendee with "
        "missing requirements.",
        "scout_schedule_cli.py write_outputs / write_email_reports",
        domain=Domain.FLOW,
    ),
)

ALL_FLOW_METADATA: tuple[CaseMetadata, ...] = FLOW_METADATA + PERF_METADATA
