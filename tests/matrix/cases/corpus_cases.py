"""Corpus/registry characterization catalog (Task 16 backfill, Slice 1b Phase A Gate).

Task 16 built the typed matrix kernel (``tests/matrix/model.py``) and wrote real, passing
pytest tests characterizing ``tools/verify_corpus.py`` (``tests/tools/test_verify_corpus.py``,
``tests/private_corpus/test_authentic.py``) plus registry/plugin self-tests
(``tests/matrix/test_registry.py``, ``tests/plugins/test_matrix_gate.py``) BEFORE the
``CaseMetadata``-catalog-per-domain pattern (Tasks 17-21) existed, so none of those tests were
ever registered as ``CaseMetadata`` rows or marked with ``@pytest.mark.matrix_case``. This module
closes that gap so ``tests.matrix.cases.ALL_CASES`` (and therefore ``--matrix-lane`` fail-closed
accounting, in particular the ``authentic`` lane) can see them.

Like ``FAKE-STRICT-*`` / ``BROWSER-EGRESS-*`` / the ``SCALE-*``/``FLOW-*`` catalogs, there is no
dedicated per-domain dataclass here -- these are plain ``CaseMetadata`` rows. The matching test
functions in ``tests/tools/test_verify_corpus.py`` and ``tests/private_corpus/test_authentic.py``
carry ``@pytest.mark.matrix_case(...)`` marks directly (Task 16's tests are one-off named
functions, never parametrized via ``tests.matrix.pytest_support.execution_params``).

This module holds only frozen data -- it never imports ``tools.verify_corpus``,
``tests.harnesses.corpus``, or any other application/harness code.

The ``REG-ID-*`` / ``REG-AXIS-*`` / ``REG-META-*`` / ``REG-LANE-*`` rows are structural
self-tests of ``tests/matrix/registry.py`` itself (``tests/matrix/test_registry.py``,
``tests/plugins/test_matrix_gate.py``). They are already implemented and passing directly as
plain pytest functions, driving ``validate_registry``/the real ``matrix_gate`` plugin by hand
rather than through the ``CaseMetadata`` context/lane execution mechanism -- so, matching
``ACQ-BREAKER-*``/``ACQ-RESUME-*`` in ``tests/matrix/cases/acquisition_cases.py``, they are
declared ``NEW_ACCEPTANCE`` with ``contexts=()``: ``CaseMetadata.execution_keys()`` returns
``()`` for any ``NEW_ACCEPTANCE`` row regardless of declared contexts, so registering them
contributes zero required execution keys to lane accounting while still proving each row is
accounted for in the registry (``REG-META``/``REG-AXIS`` validation still runs over them).
"""

from __future__ import annotations

from tests.matrix.model import CaseMetadata, Classification, Domain, EvidenceKind, Lane


def _meta(
    case_id: str,
    axis_id: str,
    member: str,
    context: str,
    rationale: str,
    evidence_reference: str,
    *,
    classification: Classification = Classification.PRESERVE,
    evidence: EvidenceKind = EvidenceKind.CURRENT_BRANCH,
    lane: str = "default",
    target_owner: str | None = None,
    target_observation: str | None = None,
) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id=axis_id,
        member=member,
        domain=Domain.CORPUS,
        classification=classification,
        evidence=evidence,
        rationale=rationale,
        contexts=() if classification is Classification.NEW_ACCEPTANCE else (context,),
        lane=Lane(lane),
        evidence_reference=evidence_reference,
        target_owner=target_owner,
        target_observation=target_observation,
    )


# --------------------------------------------------------------------------------------------
# CORP-SPLIT-001..004: tools.verify_corpus.classify_row / is_schedule_row / is_requirement_row,
# driving summarize_run's partition of a mixed raw payload (tests/tools/test_verify_corpus.py).
# --------------------------------------------------------------------------------------------
_CORP_SPLIT_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "CORP-SPLIT-001",
        "CORP-SPLIT",
        "mixed-partition",
        "corpus",
        "A raw payload mixing one schedule row and one requirement row partitions cleanly: "
        "summarize_run counts one schedule row, one requirement row, and zero unrecognized "
        "rows, with requirement flag_combos excluding the schedule row.",
        "tools.verify_corpus.summarize_run / classify_row",
    ),
    _meta(
        "CORP-SPLIT-002",
        "CORP-SPLIT",
        "schema-independent",
        "corpus",
        "A requirement row with both completion flags set to None is still classified and "
        "counted as a requirement row -- the requirement schema does not depend on the flag "
        "fields being present.",
        "tools.verify_corpus.is_requirement_row",
    ),
    _meta(
        "CORP-SPLIT-003",
        "CORP-SPLIT",
        "both-predicates-unrecognized",
        "corpus",
        "A row whose fields satisfy both is_schedule_row and is_requirement_row is classified "
        "as unrecognized rather than double-counted or arbitrarily assigned to one side.",
        "tools.verify_corpus.classify_row",
    ),
    _meta(
        "CORP-SPLIT-004",
        "CORP-SPLIT",
        "non-mapping-row",
        "corpus",
        "A non-mapping raw data row (a bare string or int) is classified as unrecognized "
        "without ever being echoed into the unrecognized-reason text.",
        "tools.verify_corpus.classify_row / unrecognized_reason",
    ),
)

# --------------------------------------------------------------------------------------------
# CORP-CLI-001..002: tools.verify_corpus.main's exit codes and bounded stdout/stderr.
# --------------------------------------------------------------------------------------------
_CORP_CLI_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "CORP-CLI-001",
        "CORP-CLI",
        "valid-output",
        "corpus",
        "Running main() against a valid corpus tree exits zero and prints only aggregate "
        "counts -- never the input directory path, the run directory name, or the argparse "
        "description text.",
        "tools.verify_corpus.main / _print_summary",
    ),
    _meta(
        "CORP-CLI-002",
        "CORP-CLI",
        "missing-corpus",
        "corpus",
        "Running main() against a missing corpus directory exits 2 with exactly one bounded "
        "stderr line that never echoes the missing path.",
        "tools.verify_corpus.main",
    ),
)

# --------------------------------------------------------------------------------------------
# CORP-FP-001..004: tests.harnesses.corpus.fingerprint_tree's read-only content fingerprinting
# (tests/private_corpus/test_authentic.py).
# --------------------------------------------------------------------------------------------
_CORP_FP_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "CORP-FP-001",
        "CORP-FP",
        "unchanged-equal",
        "corpus",
        "Fingerprinting the same unchanged directory tree twice yields two equal fingerprints.",
        "tests.harnesses.corpus.fingerprint_tree",
    ),
    _meta(
        "CORP-FP-002",
        "CORP-FP",
        "changed-unequal",
        "corpus",
        "Changing a single byte in one file changes the tree fingerprint, and neither the "
        "fingerprint's repr nor its digest exposes the file path or the raw file bytes.",
        "tests.harnesses.corpus.fingerprint_tree",
    ),
    _meta(
        "CORP-FP-003",
        "CORP-FP",
        "symlink-unsafe",
        "corpus",
        "A symlink inside the fingerprinted tree raises UnsafeCorpusEntry rather than being "
        "silently followed or fingerprinted.",
        "tests.harnesses.corpus.fingerprint_tree",
    ),
    _meta(
        "CORP-FP-004",
        "CORP-FP",
        "timestamp-mode-invariant",
        "corpus",
        "Changing a file's mtime/atime and permission bits without changing its content leaves "
        "the tree fingerprint unchanged -- only content is fingerprinted.",
        "tests.harnesses.corpus.fingerprint_tree",
    ),
)

# --------------------------------------------------------------------------------------------
# CORP-READ-001: tests.harnesses.corpus.fingerprint_tree's redacted PermissionError handling.
# --------------------------------------------------------------------------------------------
_CORP_READ_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "CORP-READ-001",
        "CORP-READ",
        "permission-denied-unreadable",
        "corpus",
        "An injected PermissionError while fingerprinting a file becomes UnreadableCorpusEntry "
        "with a bare 'permission-denied' reason code that never repeats the file name or the "
        "tree path.",
        "tests.harnesses.corpus.fingerprint_tree",
    ),
)

# --------------------------------------------------------------------------------------------
# CORP-CANON-001 / CORP-PDF-001 / CORP-SNAPSHOT-001: the three authentic-lane cases that run
# against the real private corpus (--corpus-dir, marked @pytest.mark.private_corpus). Everything
# else in this module runs against synthetic tmp_path trees; only these three read the real
# corpus, and only under a fingerprint-proven read-only contract.
# --------------------------------------------------------------------------------------------
_CORP_AUTHENTIC_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "CORP-CANON-001",
        "CORP-CANON",
        "canonical-payload-split",
        "corpus",
        "The real private corpus's canonical run directory splits into the exact expected "
        "aggregate counts (raw payloads, schedule/requirement rows, deduped classes, number "
        "shapes, flag combos) with read-only access proven by a before/after fingerprint match.",
        "tools.verify_corpus.summarize_run against the real --corpus-dir",
        evidence=EvidenceKind.CORPUS_AGGREGATE,
        lane="authentic",
    ),
    _meta(
        "CORP-PDF-001",
        "CORP-PDF",
        "pdf-extraction-aggregate",
        "corpus",
        "Extracting the real corpus's single class-schedule PDF yields the exact expected "
        "aggregate (pages, attendees, embedded/rendered decode counts, zero errors), with "
        "read-only access proven by a before/after fingerprint match.",
        "tests.harnesses.corpus.extract_pdf_aggregate against the real --corpus-dir",
        evidence=EvidenceKind.CORPUS_AGGREGATE,
        lane="authentic",
    ),
    _meta(
        "CORP-SNAPSHOT-001",
        "CORP-SNAPSHOT",
        "three-runs-share-multiset",
        "corpus",
        "Every run directory in the real corpus shares an identical raw-payload multiset "
        "(the corpus is several equivalent copies of one canonical snapshot), with read-only "
        "access proven by a before/after fingerprint match.",
        "tests.harnesses.corpus.raw_multisets_all_match against the real --corpus-dir",
        evidence=EvidenceKind.CORPUS_AGGREGATE,
        lane="authentic",
    ),
)

# --------------------------------------------------------------------------------------------
# CORP-SNAPSHOT-002: the synthetic (non-authentic) half of the raw-multiset-equality axis.
# --------------------------------------------------------------------------------------------
_CORP_SNAPSHOT_SYNTHETIC_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "CORP-SNAPSHOT-002",
        "CORP-SNAPSHOT",
        "changed-payload-breaks-equality",
        "corpus",
        "Two synthetic run directories whose raw payloads differ by one requirement field "
        "compare unequal as multisets, and raw_multisets_all_match reports False for the tree "
        "containing them.",
        "tests.harnesses.corpus.raw_payload_multiset / raw_multisets_all_match",
    ),
)

# --------------------------------------------------------------------------------------------
# CORP-MODE-001..004: tests.harnesses.corpus.corpus_status / canonical_run_dirs's directory-
# layout classification.
# --------------------------------------------------------------------------------------------
_CORP_MODE_METADATA: tuple[CaseMetadata, ...] = (
    _meta(
        "CORP-MODE-001",
        "CORP-MODE",
        "absent",
        "corpus",
        "A corpus root that does not exist on disk reports status 'absent'.",
        "tests.harnesses.corpus.corpus_status",
    ),
    _meta(
        "CORP-MODE-002",
        "CORP-MODE",
        "present",
        "corpus",
        "A corpus root containing at least one well-formed run directory reports status 'ok'.",
        "tests.harnesses.corpus.corpus_status",
    ),
    _meta(
        "CORP-MODE-003",
        "CORP-MODE",
        "empty-and-wrong-layout",
        "corpus",
        "An existing-but-empty corpus root reports 'empty'; a root whose only child is not a "
        "recognized run directory reports 'wrong-layout'.",
        "tests.harnesses.corpus.corpus_status",
    ),
    _meta(
        "CORP-MODE-004",
        "CORP-MODE",
        "alternate-root",
        "corpus",
        "corpus_status/canonical_run_dirs operate correctly against a corpus root passed at an "
        "alternate (non-default) path, not just the default location.",
        "tests.harnesses.corpus.corpus_status / canonical_run_dirs",
    ),
)

ALL_CORPUS_METADATA: tuple[CaseMetadata, ...] = (
    _CORP_SPLIT_METADATA
    + _CORP_CLI_METADATA
    + _CORP_FP_METADATA
    + _CORP_READ_METADATA
    + _CORP_AUTHENTIC_METADATA
    + _CORP_SNAPSHOT_SYNTHETIC_METADATA
    + _CORP_MODE_METADATA
)


def _reg_meta(
    case_id: str,
    axis_id: str,
    member: str,
    rationale: str,
    evidence_reference: str,
    target_observation: str,
) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id=axis_id,
        member=member,
        domain=Domain.CORPUS,
        classification=Classification.NEW_ACCEPTANCE,
        evidence=EvidenceKind.CURRENT_BRANCH,
        rationale=rationale,
        contexts=(),
        evidence_reference=evidence_reference,
        target_owner="Task 16 (already implemented)",
        target_observation=target_observation,
    )


_REG_TARGET_OBSERVATION = (
    "This structural self-test validates tests/matrix/registry.py directly via a plain pytest "
    "test function; it does not execute through the CaseMetadata context/lane mechanism the "
    "matrix kernel accounts for, so it deliberately carries no execution keys of its own."
)

# --------------------------------------------------------------------------------------------
# REG-ID-001/002: tests/matrix/test_registry.py's case-identity structural self-tests.
# --------------------------------------------------------------------------------------------
_REG_ID_METADATA: tuple[CaseMetadata, ...] = (
    _reg_meta(
        "REG-ID-001",
        "REG-ID",
        "same-case-two-contexts",
        "A valid registry where one case declares two contexts produces zero validation "
        "errors, and each declared context yields its own execution key.",
        "tests.matrix.test_registry.test_reg_id_001_valid_registry_has_no_errors",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-ID-002",
        "REG-ID",
        "duplicate-case-ids",
        "Two registry rows sharing one case_id produce exactly one REG-ID duplicate-case error "
        "naming the shared id.",
        "tests.matrix.test_registry.test_reg_id_002_duplicate_case_ids_fail",
        _REG_TARGET_OBSERVATION,
    ),
)

# --------------------------------------------------------------------------------------------
# REG-AXIS-001..006: tests/matrix/test_registry.py's axis-consistency structural self-tests.
# --------------------------------------------------------------------------------------------
_REG_AXIS_METADATA: tuple[CaseMetadata, ...] = (
    _reg_meta(
        "REG-AXIS-001",
        "REG-AXIS",
        "unknown-axis",
        "A case referencing an axis_id absent from the axis registry produces a REG-AXIS "
        "unknown-axis error naming the case and the ghost axis.",
        "tests.matrix.test_registry.test_reg_axis_001_unknown_axis_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-AXIS-002",
        "REG-AXIS",
        "missing-member",
        "An axis whose declared member set is not fully observed across its cases produces a "
        "REG-AXIS missing-member error naming the unobserved member.",
        "tests.matrix.test_registry.test_reg_axis_002_missing_member_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-AXIS-003",
        "REG-AXIS",
        "too-few-cases",
        "An axis whose min_focused_cases exceeds the number of cases actually declared for it "
        "produces a REG-AXIS too-few-cases error.",
        "tests.matrix.test_registry.test_reg_axis_003_too_few_cases_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-AXIS-004",
        "REG-AXIS",
        "missing-interaction",
        "An axis declaring an interaction id that no case actually claims produces a REG-AXIS "
        "missing-interaction error.",
        "tests.matrix.test_registry.test_reg_axis_004_missing_interaction_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-AXIS-005",
        "REG-AXIS",
        "unmapped-boundary",
        "A boundary whose required_case_ids set is empty produces a REG-AXIS unmapped-boundary "
        "error naming the boundary.",
        "tests.matrix.test_registry.test_reg_axis_005_unmapped_boundary_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-AXIS-006",
        "REG-AXIS",
        "unreviewed-exclusion",
        "A branch exclusion with a blank review_reference produces a REG-AXIS "
        "unreviewed-exclusion error naming the exclusion.",
        "tests.matrix.test_registry.test_reg_axis_006_unreviewed_exclusion_fails",
        _REG_TARGET_OBSERVATION,
    ),
)

# --------------------------------------------------------------------------------------------
# REG-META-001..005: tests/matrix/test_registry.py's case-metadata-completeness structural
# self-tests.
# --------------------------------------------------------------------------------------------
_REG_META_METADATA: tuple[CaseMetadata, ...] = (
    _reg_meta(
        "REG-META-001",
        "REG-META",
        "blank-rationale",
        "A case with a blank (whitespace-only) rationale produces a REG-META "
        "incomplete-evidence error.",
        "tests.matrix.test_registry.test_reg_meta_001_blank_rationale_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-META-002",
        "REG-META",
        "incomplete-evidence",
        "A case with an empty evidence_reference produces a REG-META incomplete-evidence error.",
        "tests.matrix.test_registry.test_reg_meta_002_incomplete_evidence_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-META-003",
        "REG-META",
        "missing-owner",
        "A non-preserve case with a target_owner of None produces a REG-META incomplete-target "
        "error even when target_observation is present.",
        "tests.matrix.test_registry.test_reg_meta_003_missing_owner_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-META-004",
        "REG-META",
        "incomplete-intentional-change",
        "A non-preserve case with a target_observation of None produces a REG-META "
        "incomplete-target error even when target_owner is present.",
        "tests.matrix.test_registry.test_reg_meta_004_incomplete_intentional_change_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-META-005",
        "REG-META",
        "policy-mismatch",
        "A case whose surface_id names a surface absent from the policy list produces a "
        "REG-META unknown-surface error; a case whose surface_id names a known policy produces "
        "no error.",
        "tests.matrix.test_registry.test_reg_meta_005_policy_mismatch_fails",
        _REG_TARGET_OBSERVATION,
    ),
)

# --------------------------------------------------------------------------------------------
# REG-LANE-001..005: tests/plugins/test_matrix_gate.py's lane-accounting structural self-tests,
# driven through real pytester subprocess suites against the live matrix_gate plugin.
# --------------------------------------------------------------------------------------------
_REG_LANE_METADATA: tuple[CaseMetadata, ...] = (
    _reg_meta(
        "REG-LANE-001",
        "REG-LANE",
        "empty-required-set",
        "A --matrix-lane run whose registry declares zero required keys for that lane fails "
        "closed (nonzero exit) with 'required=0' in its summary line.",
        "tests.plugins.test_matrix_gate.test_empty_required_set_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-LANE-002",
        "REG-LANE",
        "deselected-required-key",
        "A required execution key deselected via -k (never collected) is reported as "
        "'missing=1' and the run fails.",
        "tests.plugins.test_matrix_gate.test_deselected_key_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-LANE-003",
        "REG-LANE",
        "skipped-required-key",
        "A required execution key whose test is collected but skipped is reported as "
        "'skipped=1' and the run fails.",
        "tests.plugins.test_matrix_gate.test_skipped_key_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-LANE-004",
        "REG-LANE",
        "duplicated-required-key",
        "Two test items both declaring the same required execution key are reported as "
        "'duplicated=1' and the run fails.",
        "tests.plugins.test_matrix_gate.test_duplicated_key_fails",
        _REG_TARGET_OBSERVATION,
    ),
    _reg_meta(
        "REG-LANE-005",
        "REG-LANE",
        "missing-required-key",
        "A required execution key that no collected test item ever declares is reported as "
        "'missing=1' and the run fails.",
        "tests.plugins.test_matrix_gate.test_missing_key_fails",
        _REG_TARGET_OBSERVATION,
    ),
)

ALL_REGISTRY_METADATA: tuple[CaseMetadata, ...] = (
    _REG_ID_METADATA + _REG_AXIS_METADATA + _REG_META_METADATA + _REG_LANE_METADATA
)
