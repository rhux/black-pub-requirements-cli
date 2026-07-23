# Slice 1b Full Phase A Characterization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers-extended-cc:subagent-driven-development` (recommended) or
> `superpowers-extended-cc:executing-plans` to implement this plan task-by-task. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable, privacy-safe behavior oracle for every legacy boundary moved by
Slice 2, backed by focused synthetic rows, variable-attendee profiles, read-only authentic
aggregates, guarded browser tests, and fail-closed coverage and execution gates.

**Architecture:** A data-only typed catalog under `tests/matrix/` owns stable case metadata,
independent axis/boundary manifests, surface policies, and context-aware execution keys.
Domain-specific builders, strict fakes, and legacy harnesses execute the same cases without
importing optional dependencies into the catalog. Pytest plugins enforce lane completeness;
checked-in aggregate baselines and reviewed branch exclusions make Gate 1b reproducible.

**Tech Stack:** Python 3.12, pytest 8, pytest-asyncio, pytest-socket, Hypothesis, coverage.py,
Playwright, FastAPI TestClient/httpx, PyMuPDF, OpenCV, openpyxl, Ruff, Mypy, GitHub Actions.

---

**Status:** READY FOR EXECUTION
**Parent spec:** `docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`
**Matrix spec:** `docs/superpowers/specs/2026-07-22-phase-a-characterization-matrix-design.md`
**Companion:** `docs/superpowers/plans/2026-07-22-slice-1a-in-place-correctness.md`
**Dependency:** Gate 1a is complete. Gate 1b unblocks Slice 2.

## Scope and locked decisions

- Slice 1b changes production behavior only in `tools/verify_corpus.py`, whose current
  `requirements` label conflates schedule and requirement rows. Every other production
  observation is recorded as `preserve` or as an `intentional-change` tripwire.
- Slice 1b infrastructure `new-acceptance` rows are executable self-tests owned by Slice 1b.
  Future application `new-acceptance` rows are metadata-only and name their later implementing
  slice. Circuit breaker, resumable checkpoint, persistent output identity, and wiring the
  existing application network policy into the extracted gateway are owned by Slice 2. Native
  installer/filesystem acceptance is owned by Slices 3 and 4.
- A case ID identifies one behavior row. An `ExecutionKey(case_id, context_id)` identifies one
  required execution. Reusing a case through path, tree, HTML, email, CLI, or browser contexts
  creates distinct execution keys without duplicating the case or its expected data.
- Full lane accounting is enabled only when `--matrix-lane` is present. Task-local commands do
  not pass that option. Gate 1b is the only place that asserts the complete default, browser,
  or authentic lane.
- Every independent axis has two focused synthetic rows. Finite sets are exhaustive. Retry,
  async cleanup, publication failure, and other high-risk failure axes have success,
  recoverable/interrupted, and terminal rows.
- The canonical scale profile reproduces privacy-safe marginals only. Pairing separate
  marginals on the same synthetic rows is intentionally synthetic and cannot support a
  cross-axis assertion.
- `raw_data/` is read-only evidence. No private path, filename, value, token, payload, PDF,
  hash, or derived row is serialized into a test, baseline, log, failure message, or commit.
- Default and browser lanes deny external requests. Browser tests use loopback HTTP and WS
  endpoints only. Live-service tests require their existing marker and environment opt-in and
  are outside Gate 1b.
- Scoped branch evidence is checked from coverage JSON against a checked-in per-area baseline
  and an independently reviewed exclusion manifest. Updating a baseline is an explicit
  command; the Gate always uses check mode.

## Authoritative aggregate contracts

One canonical private snapshot has the following aggregate-only contract:

| Aggregate | Exact value |
| --- | ---: |
| JSON payloads | 120 |
| Schedule payloads / raw class rows | 22 / 103 |
| Requirement payloads / requirement rows | 98 / 4,858 |
| Total `data` rows | 4,961 |
| Per-payload deduplicated classes | 98 (five duplicates removed) |
| Requirement schemas / number shapes | 1 / 26 |
| Empty display numbers / `Note.` rows | 31 / 125 |
| Source PDFs / pages / extracted attendees / errors | 1 / 26 / 26 / 0 |
| PDF decode tier | 26 `embedded-image`, 0 rendered |

The exact safe marginals used by `SCALE-CANON-022` are:

```python
FLAG_MARGINAL = {("0", "0"): 1409, ("0", "1"): 904, ("1", "0"): 1150, ("1", "1"): 1395}
TYPE_MARGINAL = {"1": 2225, "2": 1535, "3": 1098}
RAW_CLASS_COMPLETION_MARGINAL = {"0": 41, "1": 62}
DEDUPED_CLASS_COMPLETION_MARGINAL = {"0": 36, "1": 62}
HAS_REQUIREMENTS_MARGINAL = {"1": 103}
SHAPE_MARGINAL = {
    "": 31,
    "#(N)": 30,
    "#(a)": 72,
    "#A.": 12,
    "#N": 229,
    "#N(a)": 697,
    "#N(a)(N)": 104,
    "#N.": 545,
    "#N..Aaa.A.(N)": 50,
    "#N..Aaa.A.(N)(a)": 10,
    "#N..Aaa.A.(N)(a)(N)": 40,
    "#N.Aaaaaa.A(N)": 74,
    "#N.Aaaaaa.A.(N)": 140,
    "#N.Aaaaaa.A.(N)(a)": 56,
    "#N.AaaaaaA.(N)": 4,
    "#Na": 1064,
    "#Na(N)": 44,
    "#Na.": 469,
    "#Na[N]": 32,
    "Aaaa.": 125,
    "Aaaa.Aaaa.": 35,
    "Aaaa.N.": 30,
    "N": 65,
    "N.": 255,
    "N.a.": 520,
    "N.a.N.": 125,
}
```

`RAW_CLASS_COMPLETION_MARGINAL` applies before per-payload deduplication;
`DEDUPED_CLASS_COMPLETION_MARGINAL` applies after the legacy completed-row preference.

## File responsibility map

| Path | Responsibility |
| --- | --- |
| `tests/matrix/model.py` | Shared enums, metadata, execution keys, runner protocols, normalized outcomes. |
| `tests/matrix/axes.py` | Independent finite/equivalence axes and required interactions. |
| `tests/matrix/boundaries.py` | Scoped public boundaries, critical flows, coverage areas, reviewed exclusions. |
| `tests/matrix/policies.py` | Six privacy surface classes and field/egress policies. |
| `tests/matrix/registry.py` | Explicit case imports, execution-key expansion, structural validation. |
| `tests/matrix/pytest_support.py` | Pytest parameters and marks generated from declared execution keys. |
| `tests/matrix/cases/*.py` | Domain-specific frozen case/input/observation records; no legacy imports. |
| `tests/matrix/scale_profile.py` | Versioned scale profile metadata and correlation guard. |
| `tests/plugins/matrix_gate.py` | Pytest options, capability preflight, collection/execution lane accounting. |
| `tests/factories/*.py` | Deterministic synthetic source files, payloads, PDFs, records, and scale rows. |
| `tests/fakes/*.py` | Strict acquisition/browser/clock fakes and self-tests. |
| `tests/harnesses/*.py` | Legacy, subprocess, browser, and private-corpus adapters. |
| `tests/characterization/test_*_matrix.py` | Focused legacy runners, one pytest item per execution key. |
| `tests/private_corpus/test_authentic.py` | Aggregate-only, read-only authentic checks. |
| `tests/scale/test_profiles.py` | Variable attendee and marginal tests. |
| `tests/vertical/test_legacy_flows.py` | Real-boundary success and partial-failure flows. |
| `tests/performance/test_phase_a_baseline.py` | Request-count and algorithmic-growth assertions. |
| `tools/verify_corpus.py` | Privacy-safe schedule/requirement/unrecognized classification. |
| `tools/measure_baseline.py` | Deterministic aggregate baseline generation/checking. |
| `tools/check_phase_a_coverage.py` | Coverage JSON area/exclusion/no-regression enforcement. |
| `tests/baselines/phase_a.json` | Safe versioned expected aggregates and per-area coverage floors. |
| `tests/conftest.py` | Pre-collection data sandbox, plugin registration, offline policy. |
| `pyproject.toml` | Markers, plugin-facing pytest settings, Mypy scope, coverage collection. |
| `.github/workflows/ci.yml` | Static, default matrix, Windows seam, browser, and egress-denied jobs. |

Helper directories imported as packages receive empty `__init__.py` files:
`tests/matrix/`, `tests/matrix/cases/`, `tests/fakes/`, `tests/harnesses/`, and
`tests/plugins/`.

## Shared implementation contracts

Use these exact public types throughout the plan:

```python
# tests/matrix/model.py
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Generic, Protocol, TypeVar


class Classification(StrEnum):
    PRESERVE = "preserve"
    INTENTIONAL_CHANGE = "intentional-change"
    NEW_ACCEPTANCE = "new-acceptance"


class EvidenceKind(StrEnum):
    CORPUS_AGGREGATE = "corpus-aggregate"
    CURRENT_BRANCH = "current-branch"
    PUBLIC_CONTRACT = "public-contract"
    PROPERTY_BOUNDARY = "property-boundary"


class Domain(StrEnum):
    CORPUS = "corpus"
    INPUT = "input"
    PDF = "pdf"
    ACQUISITION = "acquisition"
    REQUIREMENT = "requirement"
    ARTIFACT = "artifact"
    INTERFACE = "interface"
    PLATFORM = "platform"
    SCALE = "scale"
    FLOW = "flow"


class Lane(StrEnum):
    DEFAULT = "default"
    BROWSER = "browser"
    AUTHENTIC = "authentic"


class SurfaceClass(StrEnum):
    INPUT_PRIVATE = "input-private"
    ADAPTER_PRIVATE = "adapter-private"
    OPERATIONAL_PRIVATE = "operational-private"
    AUDIENCE_SHAREABLE = "audience-shareable"
    LOCAL_UI = "local-ui"
    DIAGNOSTIC = "diagnostic"


@dataclass(frozen=True, slots=True, order=True)
class ExecutionKey:
    case_id: str
    context_id: str


@dataclass(frozen=True, slots=True)
class CaseMetadata:
    case_id: str
    axis_id: str
    member: str
    domain: Domain
    classification: Classification
    evidence: EvidenceKind
    rationale: str
    contexts: tuple[str, ...]
    lane: Lane = Lane.DEFAULT
    evidence_reference: str = ""
    interaction_ids: frozenset[str] = frozenset()
    surface_id: str | None = None
    target_owner: str | None = None
    target_observation: str | None = None

    def execution_keys(self) -> tuple[ExecutionKey, ...]:
        if self.classification is Classification.NEW_ACCEPTANCE:
            return ()
        return tuple(ExecutionKey(self.case_id, context) for context in self.contexts)


InputT = TypeVar("InputT")
ObservationT = TypeVar("ObservationT")


class Runner(Protocol, Generic[InputT, ObservationT]):
    def run(self, value: InputT, *, root: Path) -> ObservationT: ...
```

Each domain case exposes `.meta`, its domain input, and an exact normalized legacy
observation. It does not store an assertion callback or import the legacy application.

Generate pytest parameters in one pytest-aware support module rather than importing pytest in
case data:

```python
# tests/matrix/pytest_support.py
from __future__ import annotations

from typing import Protocol, TypeVar

import pytest
from _pytest.mark.structures import ParameterSet

from tests.matrix.model import CaseMetadata, Classification


class HasMetadata(Protocol):
    meta: CaseMetadata


CaseT = TypeVar("CaseT", bound=HasMetadata)


def execution_params(cases: tuple[CaseT, ...]) -> list[ParameterSet]:
    return [
        pytest.param(
            case,
            context_id,
            id=f"{case.meta.case_id}[{context_id}]",
            marks=pytest.mark.matrix_case(
                case_id=case.meta.case_id,
                context_id=context_id,
                lane=case.meta.lane.value,
            ),
        )
        for case in cases
        for context_id in case.meta.contexts
        if case.meta.classification is not Classification.NEW_ACCEPTANCE
    ]
```

## Specification coverage index

| Specification requirement | Owning task |
| --- | --- |
| Corpus discrepancy, schema partition, private modes, fingerprint, authentic JSON/PDF aggregates | Task 16 |
| Typed catalog, independent completeness manifests, policies, plugin, execution-key lanes | Task 16 |
| CSV/XLSX/JSON/text formats, aliases, filtering, ordering, properties, dependency profiles | Task 17 |
| PDF discovery/extraction/decode/filter/schema/CLI/error behavior | Task 18 |
| Acquisition payloads, identity, retries, cleanup, strict fakes, browser and network-policy rows | Task 19 |
| Requirement shapes/flags/types/trees/choices/consumers and non-mutation | Task 20 |
| Artifact schemas, atomic failures, formulas, names, privacy surfaces and egress | Task 20 |
| CLI, HTTP methods/routes/states, SSE, async cleanup, static UI, desktop, bootstrap | Task 21 |
| Windows/macOS simulated seams and deferred native boundary | Task 21 |
| Variable attendees, canonical marginals, synthetic pairing guard, request/growth formulas | Task 22 |
| Success/partial/browser vertical flows, per-area coverage, checked baseline, CI egress | Task 22 |

---

## Task 16: Correct corpus truth and build the matrix kernel

**Depends on:** Gate 1a

**Files:**

- Create: `tests/matrix/__init__.py`
- Create: `tests/matrix/cases/__init__.py`
- Create: `tests/fakes/__init__.py`
- Create: `tests/harnesses/__init__.py`
- Create: `tests/plugins/__init__.py`
- Create: `tests/matrix/model.py`
- Create: `tests/matrix/axes.py`
- Create: `tests/matrix/policies.py`
- Create: `tests/matrix/boundaries.py`
- Create: `tests/matrix/registry.py`
- Create: `tests/matrix/pytest_support.py`
- Create: `tests/matrix/test_registry.py`
- Create: `tests/plugins/matrix_gate.py`
- Create: `tests/plugins/test_matrix_gate.py`
- Create: `tests/harnesses/corpus.py`
- Create: `tests/harnesses/subprocess.py`
- Create: `tests/private_corpus/test_authentic.py`
- Modify: `tools/verify_corpus.py`
- Modify: `tests/tools/test_verify_corpus.py`
- Modify: `tests/conftest.py`
- Modify: `pyproject.toml`

### Task 16 case contract

| IDs | Classification and exact contract |
| --- | --- |
| `CORP-SPLIT-001` | preserve: one schedule plus one requirement row gives `data_rows=2`, `schedule_rows=1`, `requirement_rows=1`, `unrecognized_rows=0`; requirement marginals exclude the schedule row. |
| `CORP-SPLIT-002` | preserve: a complete ten-field requirement row whose flags are both absent remains a requirement. |
| `CORP-SPLIT-003` | preserve: a mapping matching both predicates is unrecognized and required mode fails with a redacted reason. |
| `CORP-SPLIT-004` | preserve: a non-mapping `data` member is unrecognized and required mode fails without echoing it. |
| `CORP-CLI-001` | preserve: valid aggregate output exits 0, prints counts/schema names only, and contains no input directory or description. |
| `CORP-CLI-002` | preserve: missing corpus exits 2 and writes one bounded stderr line. |
| `CORP-CANON-001` | preserve/authentic: exact 120/103/4,858/4,961 payload split, 98 per-payload deduplicated classes, four flag pairs, three types, 26 shapes, 31 empty and 125 note rows. |
| `CORP-PDF-001` | preserve/authentic: one PDF, 26 pages, 26 attendees, zero errors, and 26 embedded-image decodes. |
| `CORP-SNAPSHOT-001` | preserve/authentic: three raw-payload multisets match while results use one canonical snapshot. |
| `CORP-SNAPSHOT-002` | preserve: a synthetic changed payload makes multiset equality fail. |
| `CORP-FP-001` | preserve: unchanged content fingerprint compares equal. |
| `CORP-FP-002` | preserve: one changed byte compares unequal without printing path/hash. |
| `CORP-FP-003` | preserve: a symlink/non-regular entry raises `UnsafeCorpusEntry`. |
| `CORP-FP-004` | preserve: timestamp/mode changes do not alter the content fingerprint. |
| `CORP-READ-001` | preserve: an injected `PermissionError` becomes `UnreadableCorpusEntry` with no path/value. |
| `CORP-MODE-001` | preserve: absent corpus in automatic mode skips with `private corpus unavailable`. |
| `CORP-MODE-002` | preserve: present corpus in automatic mode executes. |
| `CORP-MODE-003` | preserve: `--require-corpus` fails absent, empty, or wrong-layout corpus. |
| `CORP-MODE-004` | preserve: `--corpus-dir` selects an alternate valid root. |
| `REG-ID-001/002` | new-acceptance (1b): unique IDs pass; duplicate case IDs fail. |
| `REG-AXIS-001..006` | new-acceptance (1b): unknown axis, missing member, fewer than two cases, missing interaction, unmapped boundary, and unreviewed exclusion each fail. |
| `REG-META-001..005` | new-acceptance (1b): blank rationale, incomplete evidence, missing implementing owner, incomplete intentional change, and policy mismatch each fail. |
| `REG-LANE-001..005` | new-acceptance (1b): empty, deselected, skipped, duplicated, or missing execution keys fail; the same case in two declared contexts passes. |

- [ ] **Step 1: Add exact schema-partition tests**

```python
# tests/tools/test_verify_corpus.py
from pathlib import Path

from tests.factories.payloads import requirement_row, schedule_payload


def write_raw_payload(root: Path, rows: list[object]) -> Path:
    raw = root / "raw"
    raw.mkdir()
    path = raw / "payload.json"
    path.write_text(json.dumps({"data": rows}), encoding="utf-8")
    return path


def test_mixed_payload_partitions_schedule_and_requirement(tmp_path):
    schedule = schedule_payload()["data"][0]
    write_raw_payload(tmp_path, [schedule, requirement_row()])
    summary = summarize_run(tmp_path)
    assert summary["data_rows"] == 2
    assert summary["schedule_rows"] == 1
    assert summary["requirement_rows"] == 1
    assert summary["unrecognized_rows"] == 0
    assert summary["flag_combos"] == {"('0', '0')": 1}


def test_requirement_schema_does_not_depend_on_flags(tmp_path):
    row = requirement_row(COMPLETED_REQ_FLAG=None, COMPLETED_CLASS_FLAG=None)
    write_raw_payload(tmp_path, [row])
    assert summarize_run(tmp_path)["requirement_rows"] == 1
```

- [ ] **Step 2: Run the partition tests and verify the current bug**

Run: `uv run pytest tests/tools/test_verify_corpus.py -k "mixed_payload or does_not_depend" -q`

Expected: FAIL because `summarize_run` returns only the old `requirements` count.

- [ ] **Step 3: Implement exact schema predicates and partitioning**

```python
# tools/verify_corpus.py
SCHEDULE_FIELDS = frozenset({
    "CLASS_COMPLETED", "CLASS_NAME", "CLASS_NAME_ONLY", "CLASS_NBR", "CLASS_STIME",
    "HAS_REQ", "LOCATION_ROOM_NAME", "PERIOD_NAME", "SES_LKP_PERIOD_TYPE_ID", "STIME",
    "classP4ID",
})
REQUIREMENT_FIELDS = frozenset({
    "COMPLETED_CLASS_FLAG", "COMPLETED_REQ_FLAG", "MDM_LKP_BADGE_REQ_ID",
    "MDM_LKP_BADGE_REQ_TYPE_ID", "MERIT_BADGE_NAME", "PRESENT_DAYS", "REQ_DESCR",
    "REQ_NBR", "REQ_NBR_WEB_DISPLAY", "REQ_ON_EVENT",
})


def is_schedule_row(row: object) -> bool:
    return isinstance(row, dict) and frozenset(row) == SCHEDULE_FIELDS


def is_requirement_row(row: object) -> bool:
    return isinstance(row, dict) and frozenset(row) == REQUIREMENT_FIELDS


def classify_row(row: object) -> str:
    if not isinstance(row, dict):
        return "unrecognized"
    fields = frozenset(row)
    if SCHEDULE_FIELDS <= fields and REQUIREMENT_FIELDS <= fields:
        return "unrecognized"
    schedule = is_schedule_row(row)
    requirement = is_requirement_row(row)
    if schedule == requirement:
        return "unrecognized"
    return "schedule" if schedule else "requirement"
```

Update `summarize_run` to count `data_rows`, the three partitions, flag/type/shape marginals
for requirement rows only, raw and per-payload-deduplicated class completion, and redacted
schema field names. JSON/read failures increment `unreadable_payloads`; they are never ignored.

- [ ] **Step 4: Run all verifier tests**

Run: `uv run pytest tests/tools/test_verify_corpus.py -q`

Expected: PASS; mixed and malformed rows prove all partitions.

- [ ] **Step 5: Add the shared model and failing registry tests**

Create `model.py` exactly as defined in “Shared implementation contracts.” Define these
manifest records in their named files:

```python
@dataclass(frozen=True, slots=True)
class AxisSpec:
    axis_id: str
    domain: Domain
    members: frozenset[str]
    min_focused_cases: int
    interactions: frozenset[str]
    boundaries: frozenset[str]


@dataclass(frozen=True, slots=True)
class BoundarySpec:
    boundary_id: str
    qualified_name: str
    domain: Domain
    required_case_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class BranchExclusion:
    exclusion_id: str
    area_id: str
    file: str
    line: int
    branch_to: int | None
    rationale: str
    review_reference: str


@dataclass(frozen=True, slots=True)
class CoverageAreaSpec:
    area_id: str
    files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SurfacePolicy:
    surface_id: str
    surface_class: SurfaceClass
    allowed_fields: frozenset[str]
    forbidden_sentinels: frozenset[str]
```

`tests/matrix/test_registry.py` must construct minimal valid cases and then mutate one field
per `REG-*` ID. Assert the complete ordered error tuple, not a substring.

- [ ] **Step 6: Run the registry tests and verify missing implementation**

Run: `uv run pytest tests/matrix/test_registry.py -q`

Expected: collection ERROR because `tests.matrix.registry` is absent.

- [ ] **Step 7: Implement structural validation and execution-key expansion**

```python
# tests/matrix/registry.py
from collections import Counter
from collections.abc import Iterable, Sequence

from tests.matrix.axes import AxisSpec
from tests.matrix.boundaries import BoundarySpec, BranchExclusion
from tests.matrix.model import CaseMetadata, Classification, ExecutionKey, Lane
from tests.matrix.policies import SurfacePolicy


def execution_keys(cases: Iterable[CaseMetadata], lane: Lane) -> frozenset[ExecutionKey]:
    return frozenset(
        key
        for case in cases
        if case.lane is lane
        for key in case.execution_keys()
    )


def validate_registry(
    cases: Sequence[CaseMetadata],
    axes: Sequence[AxisSpec],
    boundaries: Sequence[BoundarySpec],
    exclusions: Sequence[BranchExclusion],
    policies: Sequence[SurfacePolicy],
) -> tuple[str, ...]:
    errors: list[str] = []
    forbidden_metadata_terms = (
        "t" + "bd",
        "t" + "odo",
        "implement " + "later",
        "optionally " + "extend",
        "represen" + "tative",
    )

    case_ids = [case.case_id for case in cases]
    duplicate_ids = sorted(case_id for case_id, count in Counter(case_ids).items() if count > 1)
    errors.extend(f"REG-ID duplicate case: {case_id}" for case_id in duplicate_ids)

    axis_by_id = {axis.axis_id: axis for axis in axes}
    case_by_id = {case.case_id: case for case in cases}
    boundary_by_id = {boundary.boundary_id: boundary for boundary in boundaries}
    policy_ids = {policy.surface_id for policy in policies}
    for case in cases:
        axis = axis_by_id.get(case.axis_id)
        if axis is None:
            errors.append(f"REG-AXIS unknown axis: {case.case_id}:{case.axis_id}")
            continue
        if case.member not in axis.members:
            errors.append(f"REG-AXIS unknown member: {case.case_id}:{case.member}")
        if not case.rationale.strip() or not case.evidence_reference.strip():
            errors.append(f"REG-META incomplete evidence: {case.case_id}")
        metadata_text = " ".join(
            (case.rationale, case.evidence_reference, case.target_observation or "")
        ).casefold()
        if any(term in metadata_text for term in forbidden_metadata_terms):
            errors.append(f"REG-META unresolved text: {case.case_id}")
        needs_target = case.classification is not Classification.PRESERVE
        if needs_target and (not case.target_owner or not case.target_observation):
            errors.append(f"REG-META incomplete target: {case.case_id}")
        if case.surface_id is not None and case.surface_id not in policy_ids:
            errors.append(f"REG-META unknown surface: {case.case_id}:{case.surface_id}")
        if len(case.contexts) != len(set(case.contexts)):
            errors.append(f"REG-LANE duplicate context: {case.case_id}")
        if case.classification is Classification.NEW_ACCEPTANCE and case.contexts:
            errors.append(f"REG-LANE future acceptance is executable: {case.case_id}")
        if case.classification is not Classification.NEW_ACCEPTANCE and not case.contexts:
            errors.append(f"REG-LANE missing context: {case.case_id}")

    for axis in axes:
        axis_cases = [case for case in cases if case.axis_id == axis.axis_id]
        observed_members = {case.member for case in axis_cases}
        for member in sorted(axis.members - observed_members):
            errors.append(f"REG-AXIS missing member: {axis.axis_id}:{member}")
        if len(axis_cases) < axis.min_focused_cases:
            errors.append(f"REG-AXIS too few cases: {axis.axis_id}")
        observed_interactions = frozenset().union(*(case.interaction_ids for case in axis_cases))
        for interaction in sorted(axis.interactions - observed_interactions):
            errors.append(f"REG-AXIS missing interaction: {axis.axis_id}:{interaction}")
        for boundary_id in sorted(axis.boundaries - boundary_by_id.keys()):
            errors.append(f"REG-AXIS unknown boundary: {axis.axis_id}:{boundary_id}")

    for boundary in boundaries:
        if not boundary.required_case_ids:
            errors.append(f"REG-AXIS unmapped boundary: {boundary.boundary_id}")
        for case_id in sorted(boundary.required_case_ids - case_by_id.keys()):
            errors.append(f"REG-AXIS unmapped boundary: {boundary.boundary_id}:{case_id}")
        for case_id in sorted(boundary.required_case_ids & case_by_id.keys()):
            if case_by_id[case_id].domain is not boundary.domain:
                errors.append(f"REG-AXIS boundary domain mismatch: {boundary.boundary_id}:{case_id}")

    for exclusion in exclusions:
        if not exclusion.rationale.strip() or not exclusion.review_reference.strip():
            errors.append(f"REG-AXIS unreviewed exclusion: {exclusion.exclusion_id}")

    return tuple(sorted(errors))
```

Extract the five loops into named private predicates `_validate_ids`, `_validate_axes`,
`_validate_metadata`, `_validate_boundaries`, and `_validate_policies` without changing the
messages or sort order. Each returns `list[str]`; no predicate imports legacy or optional
packages.

- [ ] **Step 8: Run registry tests and type-check the kernel**

Run: `uv run pytest tests/matrix/test_registry.py -q`

Expected: PASS for every `REG-*` tripwire.

Run: `uv run mypy tests/matrix`

Expected: success with no issues.

- [ ] **Step 9: Add the pre-collection sandbox and register the plugin**

```python
# top of tests/conftest.py, before imports that can reach ui.server
import os
import tempfile

_TEST_DATA_ROOT = tempfile.TemporaryDirectory(prefix="scoutmb-pytest-")
os.environ["SCOUTMB_DATA_DIR"] = _TEST_DATA_ROOT.name

pytest_plugins = ("tests.plugins.matrix_gate",)


def pytest_unconfigure(config: pytest.Config) -> None:
    _TEST_DATA_ROOT.cleanup()
```

Keep the existing pytest-socket hook. Do not set `SCOUTMB_DEV` and do not rely on a fixture,
because fixtures run after test-module import.

- [ ] **Step 10: Add lane-plugin self-tests before the plugin implementation**

Use `pytester` to execute tiny temporary suites for `REG-LANE-001..005`. Mark items with:

```python
pytest.mark.matrix_case(case_id="CASE-001", context_id="legacy", lane="default")
```

Assert exact exit codes and the stable summary
`matrix lane default: required=N passed=N failed=N skipped=N missing=N duplicated=N`.

- [ ] **Step 11: Run plugin self-tests and verify failure**

Run: `uv run pytest tests/plugins/test_matrix_gate.py -q`

Expected: FAIL because the options and accounting hooks do not exist.

- [ ] **Step 12: Implement plugin options, preflight, and execution accounting**

Implement `pytest_addoption`, `pytest_configure`, `pytest_collection_modifyitems`,
`pytest_runtest_logreport`, and `pytest_sessionfinish` in `tests/plugins/matrix_gate.py`.
`--matrix-lane` has choices `default`, `browser`, and `authentic`; no default value. When it
is absent, task-local suites do not perform full-lane accounting. When present, load the
registry’s required execution keys, compare them with collected marks, and fail on an empty
set, deselection, skip, duplicate, missing key, or non-passing call report. Capability absence
is an exact ordinary skip; `--require-browser` and `--require-corpus` convert it to usage error.

- [ ] **Step 13: Configure markers, Mypy scope, and coverage sources**

Add `private_corpus`, `scale`, `vertical`, `intentional_change`, and `matrix_case` markers.
Add `pytester` to pytest’s enabled plugins for the self-test module. Change Mypy’s `files` to:

```toml
files = [
    "src", "tools", "tests/matrix", "tests/fakes", "tests/harnesses",
    "tests/factories", "tests/plugins",
]
```

Change coverage collection to include the scoped legacy files by path. `include` avoids
importing `ui.server` during coverage initialization before pytest installs the data sandbox:

```toml
[tool.coverage.run]
branch = true
include = [
    "scout_schedule_cli.py", "pdf_to_scouts.py", "ui/server.py", "run_app.py",
    "bootstrap/paths.py", "bootstrap/marker.py", "bootstrap/source_sync.py",
    "src/scoutmb/*.py", "tools/*.py",
]
```

- [ ] **Step 14: Implement read-only corpus fingerprinting and authentic cases**

`tests/harnesses/corpus.py` defines `CorpusFingerprint`, `UnsafeCorpusEntry`,
`UnreadableCorpusEntry`, `fingerprint_tree(root, read_bytes=Path.read_bytes)`, canonical-run
multiset comparison, and aggregate PDF extraction. Fingerprints contain relative path, entry
kind, size, and digest in memory; exception strings contain reason codes only. The authentic
test captures a fingerprint before and after and writes every generated result below
`tmp_path`.

- [ ] **Step 15: Run Task 16 verification**

Run: `uv run pytest tests/tools/test_verify_corpus.py tests/matrix/test_registry.py tests/plugins/test_matrix_gate.py -q`

Expected: PASS.

Run: `uv run pytest tests/private_corpus/test_authentic.py --corpus-dir raw_data --require-corpus -q`

Expected: PASS with `CORP-CANON-001` and `CORP-PDF-001` executed, no private value printed.

Run: `uv run python tools/check_private_data.py --corpus raw_data tests`

Expected: `private-data findings: 0`.

Run: `uv run ruff check tests/matrix tests/harnesses tests/plugins tools/verify_corpus.py`

Expected: exit 0.

Run: `uv run mypy tests/matrix tests/harnesses tests/plugins tools/verify_corpus.py`

Expected: success with no issues.

- [ ] **Step 16: Commit Task 16**

```bash
git add pyproject.toml tools/verify_corpus.py tests/conftest.py tests/tools/test_verify_corpus.py tests/matrix tests/harnesses tests/plugins tests/private_corpus
git commit -m "test: add typed matrix kernel and correct corpus oracle"
```

---

## Task 17: Complete the input-loader matrix

**Depends on:** Task 16

**Files:**

- Create: `tests/matrix/cases/input_cases.py`
- Create: `tests/factories/inputs.py`
- Create: `tests/characterization/test_input_matrix.py`
- Modify: `tests/harnesses/subprocess.py`
- Modify: `tests/matrix/axes.py`
- Modify: `tests/matrix/boundaries.py`

### Task 17 exact member map

| IDs | Ordered members |
| --- | --- |
| `IN-FORMAT-001..008` | CSV; XLSX; JSON list; JSON `scouts`; JSON `data`; one JSON mapping; JSON string row; text. |
| `IN-ALIAS-NAME-001..003` | `Attendee Name`; `Name`; `Scout Name`. |
| `IN-ALIAS-URL-001..004` | `QR Code Contents`; `URL`; `QR URL`; `Link`. |
| `IN-ALIAS-TYPE-001..002` | `Registrant Type`; `Type`. |
| `IN-HEADER-001..004` | UTF-8 BOM; case/punctuation normalization; surrounding whitespace; unknown header. |
| `IN-XLSX-SHEET-001..003` | requested sheet; `Scouts Only`; first sheet. |
| `IN-XLSX-ERR-001..002` | empty workbook; missing URL column. |
| `IN-JSON-001..006` | name aliases; URL aliases; type aliases; string item; ignored invalid item; malformed top level. |
| `IN-TEXT-001..004` | URL-only; `name,url`; blank/comment; comma without HTTPS. |
| `IN-FILTER-001..006` | valid prefix; invalid scheme; invalid host/path; Adult; Part-Time Adult; include adults/all-filtered boundary. |
| `IN-DEDUP-001..002` | duplicate URL keeps first; same name with distinct URLs stays distinct. |
| `IN-EMPTY-001..002` | physically empty; parsed rows all filtered. |
| `IN-IMPORT-001..004` | clean subprocess `base`; `pdf`; `acquisition`; `all`. |

All success rows normalize to an exact tuple of `(name, url, registrant_type)`; use synthetic
names `Avery Example` and `Bailey Example`, URLs ending in `?t=TESTTOKEN_A/B`, and types
`Youth`/`Adult`. Error rows compare exception type and the complete bounded message.

```python
# tests/matrix/cases/input_cases.py
@dataclass(frozen=True, slots=True)
class InputSpec:
    format: str
    variant: str
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    json_value: object | None = None
    text_lines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InputObservation:
    records: tuple[tuple[str, str, str], ...] = ()
    exception_type: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class InputCase:
    meta: CaseMetadata
    input: InputSpec
    expected_legacy: InputObservation
```

- [ ] **Step 1: Add axes and verify the independent audit fails**

Declare one `AxisSpec` for each table row and its exact member set. Add boundary entries for
`load_inputs`, `load_csv`, `load_xlsx`, `load_json`, and `load_text`.

Run: `uv run pytest tests/matrix/test_registry.py -q`

Expected: FAIL listing the missing `IN-*` members.

- [ ] **Step 2: Add deterministic input builders**

```python
# tests/factories/inputs.py
@dataclass(frozen=True, slots=True)
class SyntheticInputRow:
    name: str = "Avery Example"
    url: str = "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_A"
    registrant_type: str = "Youth"


def write_csv_input(path: Path, headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)
    return path
```

Add equivalent `write_xlsx_input`, `write_json_input`, and `write_text_input`; every builder
writes only below its supplied path and returns that path.

- [ ] **Step 3: Add the first failing CSV/XLSX/JSON/text execution items**

```python
@pytest.mark.parametrize(("case", "context_id"), execution_params(INPUT_CASES))
def test_input_case(case: InputCase, context_id: str, tmp_path: Path) -> None:
    observed = LegacyInputRunner(context_id).run(case.input, root=tmp_path)
    assert observed == case.expected_legacy
```

`execution_params` expands each case’s declared contexts; it never invents contexts in the
test module.

- [ ] **Step 4: Run focused rows before filling the catalog**

Run: `uv run pytest tests/characterization/test_input_matrix.py -q`

Expected: FAIL on the first unimplemented builder or missing case row.

- [ ] **Step 5: Implement every table member as frozen input/observation data**

Use distinct contexts `csv`, `xlsx`, `json`, `text`, and `subprocess`. CSV/XLSX alias members
execute in both `csv` and `xlsx` contexts and therefore have two execution keys. Case data
contains no legacy import. Hypothesis uses `max_examples=40`, `derandomize=True`, and bounded
strings of at most 80 characters for header punctuation/whitespace and text rows.

- [ ] **Step 6: Implement clean optional-import subprocess probes**

The probe launches `sys.executable -I -c <script>` with an import blocker, imports the actual
legacy symbol, and returns JSON containing `profile`, `returncode`, `exception_type`, and
`imported_modules`. It must not inspect the parent process’s `sys.modules` and must not modify
`sys.path`.

- [ ] **Step 7: Run Task 17 verification**

Run: `uv run pytest tests/characterization/test_input_matrix.py tests/matrix/test_registry.py -q`

Expected: every declared `IN-*` execution key passes; no skip.

Run: `uv run pytest tests/characterization/test_input_matrix.py -k import -q`

Expected: four subprocess profiles pass.

Run: `uv run ruff check tests/matrix/cases/input_cases.py tests/factories/inputs.py tests/characterization/test_input_matrix.py`

Expected: exit 0.

Run: `uv run mypy tests/matrix/cases/input_cases.py tests/factories/inputs.py tests/harnesses/subprocess.py`

Expected: success with no issues.

- [ ] **Step 8: Commit Task 17**

```bash
git add tests/matrix/cases/input_cases.py tests/matrix/axes.py tests/matrix/boundaries.py tests/factories/inputs.py tests/harnesses/subprocess.py tests/characterization/test_input_matrix.py
git commit -m "test: characterize the complete legacy input matrix"
```

---

## Task 18: Complete the PDF and PDF-CLI matrix

**Depends on:** Task 16

**Files:**

- Create: `tests/matrix/cases/pdf_cases.py`
- Create: `tests/factories/pdf_builder.py`
- Create: `tests/characterization/test_pdf_matrix.py`
- Modify: `tests/matrix/axes.py`
- Modify: `tests/matrix/boundaries.py`

### Task 18 exact member map

| IDs | Ordered members |
| --- | --- |
| `PDF-DISC-001..006` | file; directory; glob; recursive directory; overlapping inputs; missing/non-PDF. |
| `PDF-ID-001..008` | all fields; missing name; missing type; missing QR; missing name+type; name+QR; type+QR; all missing/blank. |
| `PDF-CASE-001..004` | normalize `MIles`; normalization disabled; preserve `McDonald`; preserve `AJ`. |
| `PDF-QR-001..006` | embedded; rendered; preferred ScoutingEvent value; first other value; multi-symbol dedup/order; total failure. |
| `PDF-PAGE-001..002` | multipage order; multi-PDF order. |
| `PDF-CORRUPT-001..002` | corrupt PDF returns one bounded open error; corrupt embedded image is ignored and rendered QR fallback succeeds. |
| `PDF-DEBUG-001..002` | failed decode with debug root; failed decode without debug root. |
| `PDF-FILTER-001..006` | default Adult; custom adult; include adults; ScoutingEvent-only; duplicate QR removed; duplicates retained. |
| `PDF-SCHEMA-001..002` | exact seven-column attendee CSV; exact five-column error CSV. |
| `PDF-CLI-001..008` | defaults/help; no match; DPI below bound; DPI above bound; success; strict warning exit 1; quiet success; stale error removal. |

```python
# tests/matrix/cases/pdf_cases.py
@dataclass(frozen=True, slots=True)
class PdfPageSpec:
    name: str
    registrant_type: str
    qr_value: str
    qr_mode: Literal["embedded", "vector", "none"]


@dataclass(frozen=True, slots=True)
class ExtractedAttendeeObservation:
    attendee_name: str
    name_as_printed: str
    registrant_type: str
    qr_data: str
    source_pdf: str
    pdf_page: int
    qr_decode_method: str


@dataclass(frozen=True, slots=True)
class ExtractionErrorObservation:
    source_pdf: str
    pdf_page: int
    attendee_name: str
    registrant_type: str
    error: str


@dataclass(frozen=True, slots=True)
class PdfObservation:
    attendees: tuple[ExtractedAttendeeObservation, ...] = ()
    errors: tuple[ExtractionErrorObservation, ...] = ()
    return_code: int = 0
    stdout: tuple[str, ...] = ()
    stderr: tuple[str, ...] = ()
    relative_files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PdfCase:
    meta: CaseMetadata
    pages: tuple[PdfPageSpec, ...]
    argv: tuple[str, ...]
    expected_legacy: PdfObservation
```

- [ ] **Step 1: Register PDF members and verify missing-member failures**

Add exact `AxisSpec` entries and boundaries for `expand_pdf_inputs`, `extract_page_identity`,
`normalize_obvious_case`, `decode_embedded_qr`, `decode_rendered_qr`, `extract_pdf`,
`write_attendees_csv`, `write_errors_csv`, and `main`.

Run: `uv run pytest tests/matrix/test_registry.py -q`

Expected: FAIL listing every missing PDF member.

- [ ] **Step 2: Add a deterministic test-time PDF builder**

```python
from tests.matrix.cases.pdf_cases import PdfPageSpec


def build_pdf(path: Path, pages: tuple[PdfPageSpec, ...]) -> Path:
    document = fitz.open()
    try:
        for spec in pages:
            page = document.new_page(width=612, height=792)
            page.insert_textbox(
                fitz.Rect(54, 54, 360, 180),
                f"Attendee Information\n{spec.name}\nRegistrant\n{spec.registrant_type}",
                fontsize=12,
            )
            if spec.qr_mode == "none":
                continue
            matrix = cv2.QRCodeEncoder_create().encode(spec.qr_value)
            if spec.qr_mode == "embedded":
                ok, encoded = cv2.imencode(".png", matrix)
                if not ok:
                    raise RuntimeError("synthetic QR encoding failed")
                page.insert_image(fitz.Rect(400, 54, 540, 194), stream=encoded.tobytes())
            else:
                module = 120 / matrix.shape[0]
                for row, column in zip(*np.where(matrix == 0), strict=True):
                    x0 = 410 + column * module
                    y0 = 64 + row * module
                    page.draw_rect(
                        fitz.Rect(x0, y0, x0 + module, y0 + module),
                        color=(0, 0, 0),
                        fill=(0, 0, 0),
                        width=0,
                    )
        document.save(path)
    finally:
        document.close()
    return path
```

The function accepts no source PDF and writes only below `tmp_path`; corrupt fixtures are byte
strings created in the test process.

- [ ] **Step 3: Add failing embedded and rendered decoder tests**

Build one page of each mode, call real `extract_pdf`, and compare all seven attendee fields,
the complete error tuple, and `qr_decode_method` (`embedded-image:xref-<normalized>` or
`rendered:<dpi>:<region>` after normalizing only the xref).

Run: `uv run pytest tests/characterization/test_pdf_matrix.py -k "embedded or rendered" -q`

Expected: FAIL until the builder produces both tiers correctly.

- [ ] **Step 4: Fill every PDF member and exact CLI channel observation**

Invoke `pdf_to_scouts.main(argv, progress_callback=record_progress)` directly with real extraction. Mock
only an OpenCV decoder exception for `PDF-CORRUPT-002`; never replace `extract_pdf`. Capture
complete stdout/stderr line tuples, exit code, generated relative paths, schemas, rows, and
cleanup state. Quiet success stdout is exactly one final output path.

- [ ] **Step 5: Add bounded PDF properties**

Use `max_examples=20`, `derandomize=True`, DPI lists of one to four values within accepted
bounds, filenames at most 60 Unicode characters, and two to five overlapping discovery
inputs. Assert deterministic ordering, deduplication, and no writes outside `tmp_path`.

- [ ] **Step 6: Run Task 18 verification**

Run: `uv run pytest tests/characterization/test_pdf_matrix.py tests/matrix/test_registry.py -q`

Expected: every PDF execution key passes; no committed PDF or PNG exists.

Run: `uv run ruff check tests/matrix/cases/pdf_cases.py tests/factories/pdf_builder.py tests/characterization/test_pdf_matrix.py`

Expected: exit 0.

Run: `uv run mypy tests/matrix/cases/pdf_cases.py tests/factories/pdf_builder.py`

Expected: success with no issues.

- [ ] **Step 7: Commit Task 18**

```bash
git add tests/matrix/cases/pdf_cases.py tests/matrix/axes.py tests/matrix/boundaries.py tests/factories/pdf_builder.py tests/characterization/test_pdf_matrix.py
git commit -m "test: characterize PDF extraction and CLI behavior"
```

---

## Task 19: Complete acquisition, strict-fake, retry, and guarded-browser coverage

**Depends on:** Tasks 16 and 17

**Files:**

- Create: `tests/matrix/cases/acquisition_cases.py`
- Create: `tests/fakes/acquisition.py`
- Create: `tests/fakes/browser.py`
- Create: `tests/fakes/clock.py`
- Create: `tests/fakes/test_strict_fakes.py`
- Create: `tests/harnesses/browser.py`
- Create: `tests/characterization/test_acquisition_matrix.py`
- Create: `tests/characterization/test_browser_matrix.py`
- Modify: `tests/matrix/axes.py`
- Modify: `tests/matrix/boundaries.py`
- Modify: `tests/matrix/policies.py`

### Task 19 exact member map

| IDs | Ordered members |
| --- | --- |
| `ACQ-RESP-001..004` | correct schedule URL+POST; wrong URL; wrong method; wrong form body. |
| `ACQ-ID-001..004` | present attendee ID; absent key; blank value; repeated key where last wins. |
| `ACQ-SCHED-001..005` | empty data; one class; multiple classes; failed status; missing/falsey data. |
| `ACQ-DEDUP-001..005` | unique IDs; missing IDs; incomplete→complete; complete→incomplete; equal duplicate. |
| `ACQ-HASREQ-001..003` | `HAS_REQ=1`; `HAS_REQ=0`; blank class ID. |
| `ACQ-REQ-001..006` | success; failed status; empty data; missing required fields; unknown fields; non-list data. |
| `ACQ-RETRY-001..003` | immediate success/no wait; two transient failures then success/waits 500,1000; three failures/waits 500,1000,1500. |
| `ACQ-DELAY-001..002` | zero request delay; positive configured delay. |
| `ACQ-RAW-001..003` | schedule raw file; requirement raw file; same-name attendees receive distinct UUID filenames. |
| `ACQ-CLEAN-001..003` | success; schedule exception; terminal requirement failure. |
| `ACQ-ASSET-001..002` | dead asset aborted; allowed dead asset continued. |
| `ACQ-IDENTITY-001..003` | missing ID fails closed; UUIDv4 stable within one run; two runs are unlinkable. |
| `ACQ-BREAKER-001..003` | new-acceptance/Slice 2: below threshold remains closed; threshold opens; successful recovery resets. |
| `ACQ-RESUME-001..004` | new-acceptance/Slice 2: new checkpoint; completed requests not repeated; output UUID survives resume; corrupt/version-mismatched checkpoint fails closed. |
| `FAKE-STRICT-001..007` | wrong attendee ID; wrong class ID; wrong order; wrong delay; unexpected retry; extra call; unconsumed response. |
| `BROWSER-LOCAL-001..004` | capture schedule POST; serve requirement JSON; real browser interception; full local acquisition success. |
| `BROWSER-EGRESS-001..006` | external navigation; redirect; frame; popup; worker/fetch; WebSocket. |
| `NET-POLICY-001..003` | preserve: loopback allowed; non-loopback denied without environment opt-in; service host allowed with environment opt-in while live tests still require the marker. |
| `NET-WIRE-001..002` | new-acceptance/Slice 2: extracted HTTP gateway consults policy before I/O; extracted Playwright gateway consults policy before navigation. |

`ACQ-HASREQ-002` is `intentional-change`: legacy requests requirements for a nonblank class ID
even when `HAS_REQ="0"`; Slice 2’s target does not. `ACQ-REQ-004` pins legacy coercion of
missing fields and records Slice 2’s schema-validation target. The breaker, resume, and
policy-wiring rows validate metadata/ownership only in Slice 1b and therefore have no execution
keys. `NET-POLICY-*` executes the existing `src.scoutmb.network_policy.assert_egress_allowed`
boundary created in Slice 1a.

```python
# tests/matrix/cases/acquisition_cases.py
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
    result: tuple[object, ...]
    calls: tuple[ExpectedRequest, ...]
    waits_ms: tuple[int, ...]
    relative_files: tuple[str, ...]
    closed: bool


@dataclass(frozen=True, slots=True)
class AcquisitionCase:
    meta: CaseMetadata
    scout_name: str
    qr_url: str
    script: tuple[tuple[ExpectedRequest, ScriptedResponse], ...]
    expected_legacy: AcquisitionObservation | None
```

- [ ] **Step 1: Add acquisition axes, boundaries, and new-acceptance ownership tests**

Add boundaries for `form_values`, `is_schedule_response`, `navigate_and_trigger_schedule`,
`post_requirement`, `process_scout`, `RunIdentity.output_id`, `assert_egress_allowed`, and the
`async_main` acquisition loop. Add exact target observations for every `ACQ-BREAKER`,
`ACQ-RESUME`, and `NET-WIRE` row with `target_owner="Slice 2"`.

Run: `uv run pytest tests/matrix/test_registry.py -q`

Expected: FAIL listing missing acquisition members; no missing-owner failure.

- [ ] **Step 2: Add strict fake self-tests before fake implementation**

```python
from tests.matrix.cases.acquisition_cases import ExpectedRequest, ScriptedResponse
```

Each strict fake owns a deque of `(ExpectedRequest, ScriptedResponse)`, compares the next
complete request, appends an immutable call log, raises `UnexpectedFakeCall` on mismatch or
extra call, and raises `UnconsumedFakeResponses` from `assert_consumed()`.

- [ ] **Step 3: Run fake self-tests and verify failure**

Run: `uv run pytest tests/fakes/test_strict_fakes.py -q`

Expected: collection ERROR because strict fakes are absent.

- [ ] **Step 4: Implement strict acquisition and clock fakes**

`tests/fakes/acquisition.py` supplies strict response, request, page, context, and browser
objects implementing only the attributes used by the legacy functions. `tests/fakes/clock.py`
records exact millisecond and second waits and never sleeps. Every fake implements
`assert_consumed()` and `assert_closed()` where it owns resources.

- [ ] **Step 5: Run fake self-tests**

Run: `uv run pytest tests/fakes/test_strict_fakes.py -q`

Expected: seven `FAKE-STRICT-*` cases pass by proving each misuse fails the fake.

- [ ] **Step 6: Add failing immediate/recovery/terminal acquisition tests**

Drive real `process_scout` with the strict browser and fake clock. Do not patch
`process_scout`, `post_requirement`, deduplication, or record construction. Compare the full
`ScoutResult` observation, ordered requests, raw relative files/content, waits, resource
state, and remaining script.

Run: `uv run pytest tests/characterization/test_acquisition_matrix.py -k retry -q`

Expected: FAIL until the harness connects the strict page responses and waits.

- [ ] **Step 7: Implement every acquisition row**

Use one pytest item per declared execution key. `ACQ-RETRY-003` must observe all three waits,
including the legacy wait after the terminal third failure. `ACQ-CLEAN-*` asserts context and
page closure plus an empty script on success and each failure. Normalize UUID filenames only
after separately proving UUIDv4 format and same-run stability.

- [ ] **Step 8: Add the guarded browser harness**

```python
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def assert_loopback(url: str) -> None:
    host = urlsplit(url).hostname
    if host not in LOOPBACK_HOSTS:
        raise ExternalBrowserRequest(f"external browser request blocked: {host or '<none>'}")
```

Install listeners and route guards on the browser context before creating the first page.
Guard request, navigation, redirect response, frame, popup, worker/service-worker, fetch/XHR,
WebSocket, and download events. The failure message contains scheme/host only, never path,
query, request body, or header.

- [ ] **Step 9: Add a loopback fake service and browser egress tests**

Start one ephemeral loopback server that serves deterministic HTML, schedule POST JSON,
requirement POST JSON, redirect/frame/worker/fetch routes, and a local WS endpoint. Each
`BROWSER-EGRESS-*` row also attempts one non-loopback URL and asserts `ExternalBrowserRequest`.
No test reaches DNS or a live service.

- [ ] **Step 10: Run Task 19 verification without a full lane audit**

Run: `uv run pytest tests/fakes/test_strict_fakes.py tests/characterization/test_acquisition_matrix.py tests/matrix/test_registry.py -q`

Expected: every executable `ACQ-*` and `FAKE-*` row passes; new-acceptance rows have owners.

Run: `uv run pytest tests/characterization/test_browser_matrix.py -m playwright --require-browser -q`

Expected: every `BROWSER-*` row passes and the harness reports zero external requests.

Run: `uv run ruff check tests/fakes tests/harnesses/browser.py tests/matrix/cases/acquisition_cases.py tests/characterization/test_acquisition_matrix.py tests/characterization/test_browser_matrix.py`

Expected: exit 0.

Run: `uv run mypy tests/fakes tests/harnesses/browser.py tests/matrix/cases/acquisition_cases.py`

Expected: success with no issues.

- [ ] **Step 11: Commit Task 19**

```bash
git add tests/matrix/cases/acquisition_cases.py tests/matrix/axes.py tests/matrix/boundaries.py tests/matrix/policies.py tests/fakes tests/harnesses/browser.py tests/characterization/test_acquisition_matrix.py tests/characterization/test_browser_matrix.py
git commit -m "test: characterize acquisition and guarded browser contracts"
```

---

## Task 20: Complete requirement, artifact, publication-failure, and privacy coverage

**Depends on:** Task 16

**Files:**

- Create: `tests/matrix/cases/requirement_cases.py`
- Create: `tests/matrix/cases/artifact_cases.py`
- Create: `tests/characterization/test_requirement_matrix.py`
- Create: `tests/characterization/test_artifact_matrix.py`
- Create: `tests/privacy/test_surface_policies.py`
- Modify: `tests/factories/payloads.py`
- Modify: `tests/factories/records.py`
- Modify: `tests/factories/test_factories_smoke.py`
- Modify: `tests/matrix/axes.py`
- Modify: `tests/matrix/policies.py`
- Modify: `tests/matrix/boundaries.py`

### Task 20 requirement contract

`REQ-SHAPE-001..026` map in order to:

```text
#Na, #N(a), #N., N.a., #Na., N., #N, #N.Aaaaaa.A.(N), <empty>, Aaaa.,
N.a.N., #N(a)(N), #N.Aaaaaa.A(N), #(a), N, #N.Aaaaaa.A.(N)(a),
#N..Aaa.A.(N), #Na(N), #N..Aaa.A.(N)(a)(N), Aaaa.Aaaa., #Na[N],
Aaaa.N., #(N), #A., #N..Aaa.A.(N)(a), #N.AaaaaaA.(N)
```

Each shape has execution contexts `requirement_path` and `tree_consumer`. Shapes used by
HTML and email additionally use `html_consumer` and `email_consumer`; these are distinct
execution keys for the same case data.

| IDs | Ordered members |
| --- | --- |
| `REQ-FLAG-001..008` | all four `(req,class)` pairs in `leaf`; the same four in `parent_consumer`. |
| `REQ-TYPE-001..003` | types `1`; `2`; `3`. |
| `REQ-CLASS-001..002` | incomplete; complete class. |
| `REQ-EMPTY-001..002` | empty display with no top level; empty display after top level. |
| `REQ-NOTE-001..002` | note after numbered row; note at beginning. |
| `REQ-TREE-001..006` | leaf; parent; grandparent; missing parent; malformed numbering; label row. |
| `REQ-CHOICE-001..030` | verbs `do/complete/choose/select/perform` × below/equal/above threshold × digit/word count. |
| `REQ-EXCLUDE-001..002` | `(not used)`; type 3. |
| `REQ-NONMUTATE-001..002` | valid tree input; malformed input. |
| `REQ-IDENTITY-001..003` | same name/different IDs; same ID groups; blank-ID defensive legacy fallback. |

### Task 20 artifact and privacy contract

| IDs | Ordered members |
| --- | --- |
| `ART-SCHEMA-001..008` | scouts JSON; classes CSV; requirements CSV; errors CSV; summary JSON; report data; email CSV; email text/HTML. |
| `ART-HTML-001..005` | sentinel once; `</script>`; `<>&`; U+2028/U+2029; Unicode. |
| `ART-EMAIL-001..004` | missing requirements; all complete; no data; same-name attendees. |
| `ART-NAME-001..009` | traversal; absolute; Unicode; case-only collision; Windows reserved; empty; symlink output root; duplicate display name; duplicate requested HTML filename. |
| `ART-FORMULA-001..006` | prefixes `=`; `+`; `-`; `@`; tab; carriage return in every outward CSV/XLSX field. |
| `ART-FAIL-001..006` | before render; temp write; before replace; after replace; cleanup; between sibling writers. |
| `PRIV-INPUT/ADAPTER/OPS/SHARE/UI/DIAG-001..002` | one allowed-field case and one forbidden-sentinel case for each of six surface classes. |
| `PRIV-EGRESS-001..010` | filename; JSON; CSV; HTML; email; stdout; stderr; API error; SSE; diagnostics. |
| `PRIV-CONTAIN-001..002` | adapter-private file remains inside selected root; no private field reaches shareable/support surfaces. |

`ART-NAME-007` is an intentional-change tripwire: legacy follows a symlinked output root;
Slice 2 rejects it before publication. Case-only, Windows-reserved, and macOS normalization
rows remain simulated pure-contract cases; they do not claim native filesystem behavior.

```python
# tests/matrix/cases/requirement_cases.py
@dataclass(frozen=True, slots=True)
class RequirementCase:
    meta: CaseMetadata
    rows: tuple[Mapping[str, object], ...]
    expected_by_context: Mapping[str, object]


# tests/matrix/cases/artifact_cases.py
@dataclass(frozen=True, slots=True)
class ArtifactObservation:
    files: tuple[tuple[str, bytes], ...]
    stdout: tuple[str, ...] = ()
    stderr: tuple[str, ...] = ()
    exception_type: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactCase:
    meta: CaseMetadata
    input_rows: tuple[Mapping[str, object], ...]
    expected_legacy: ArtifactObservation
```

- [ ] **Step 1: Replace the shape fixture and add exact marginal smoke tests**

Replace the 18-value list in `tests/factories/payloads.py` with 26 concrete synthetic values
whose normalized forms match the ordered shape contract. `test_factories_smoke.py` asserts
the complete normalized tuple and count 26. Remove `sys.path.insert` from
`tests/factories/records.py`; imports work from repository-root pytest collection.

Run: `uv run pytest tests/factories/test_factories_smoke.py -q`

Expected: FAIL at 18 versus 26 before the fixture update, then PASS.

- [ ] **Step 2: Add requirement axes and verify missing executions**

Add exact members, interactions, and boundaries for `requirement_path`,
`choice_requirement_count`, `annotate_requirement_statuses`, `build_missing_requirements`,
`render_email_text`, and `render_email_html`.

Run: `uv run pytest tests/matrix/test_registry.py -q`

Expected: FAIL listing the missing requirement execution keys.

- [ ] **Step 3: Add path and tree tests before case data**

```python
@pytest.mark.parametrize(("case", "context_id"), execution_params(REQUIREMENT_CASES))
def test_requirement_execution(case: RequirementCase, context_id: str) -> None:
    before = deepcopy(case.rows)
    observed = LegacyRequirementRunner(context_id).run(case.rows, root=Path("synthetic"))
    assert observed == case.expected_by_context[context_id]
    assert case.rows == before
```

Run: `uv run pytest tests/characterization/test_requirement_matrix.py -q`

Expected: FAIL until all case observations and contexts exist.

- [ ] **Step 4: Implement the full requirement catalog**

Store complete ordered normalized observations: path tuple/current top, annotated row keys and
values, selected tree nodes/depth/order, email text lines, and parsed HTML structure. Do not
derive expected ancestry or completion with the production function under test. Generate the
30 choice rows from an explicit immutable table of verb, text count, required count, and
expected boolean.

- [ ] **Step 5: Add surface policies and failing policy tests**

Materialize the six matrix-spec surface rows in `policies.py`. Use synthetic sentinels for
display name, upstream ID, QR token, session, payload fragment, and absolute path. The test
scans committed case/factory source plus generated operational/shareable/UI/diagnostic files.
Adapter-private outputs use exact field allowlists, output-UUID filenames, containment, and
no-copy assertions instead of a blanket forbidden-token scan.

Run: `uv run pytest tests/privacy/test_surface_policies.py -q`

Expected: FAIL until every surface and egress member is registered.

- [ ] **Step 6: Add exact artifact/schema tests**

For every `ART-SCHEMA-*` row compare ordered keys/headers, complete rows, encoding, newline,
and file-presence tuple. HTML cases parse the embedded JSON and assert no residual
`__REPORT_DATA__`. Formula cases place each prefix in each outward spreadsheet column and
record legacy output plus Slice 2’s escaped target.

- [ ] **Step 7: Add publication-failure injection tests**

Inject failures only at `Path.write_text`, temporary file write, `os.replace`, and cleanup
seams. Capture prior bytes, final bytes, temporary files, sibling files, and reported error.
Do not mock the serializer or writer being tested.

- [ ] **Step 8: Run Task 20 verification**

Run: `uv run pytest tests/characterization/test_requirement_matrix.py tests/characterization/test_artifact_matrix.py tests/privacy/test_surface_policies.py tests/matrix/test_registry.py -q`

Expected: all required execution keys pass; each of 26 shapes runs in both required contexts.

Run: `uv run python tools/check_private_data.py --corpus raw_data tests`

Expected: `private-data findings: 0`.

Run: `uv run ruff check tests/matrix/cases/requirement_cases.py tests/matrix/cases/artifact_cases.py tests/factories tests/characterization/test_requirement_matrix.py tests/characterization/test_artifact_matrix.py tests/privacy/test_surface_policies.py`

Expected: exit 0.

Run: `uv run mypy tests/matrix/cases/requirement_cases.py tests/matrix/cases/artifact_cases.py tests/factories`

Expected: success with no issues.

- [ ] **Step 9: Commit Task 20**

```bash
git add tests/matrix/cases/requirement_cases.py tests/matrix/cases/artifact_cases.py tests/matrix/axes.py tests/matrix/policies.py tests/matrix/boundaries.py tests/factories tests/characterization/test_requirement_matrix.py tests/characterization/test_artifact_matrix.py tests/privacy/test_surface_policies.py
git commit -m "test: characterize inference artifacts and privacy surfaces"
```

---

## Task 21: Complete interfaces, lifecycle, desktop, and scoped-platform coverage

**Depends on:** Tasks 16 and 19

**Files:**

- Create: `tests/matrix/cases/interface_cases.py`
- Create: `tests/matrix/cases/platform_cases.py`
- Create: `tests/characterization/test_interface_matrix.py`
- Create: `tests/characterization/test_platform_matrix.py`
- Create: `tests/characterization/test_static_ui.py`
- Create: `tests/harnesses/legacy.py`
- Modify: `tests/harnesses/browser.py`
- Modify: `tests/matrix/axes.py`
- Modify: `tests/matrix/boundaries.py`
- Modify: `tests/matrix/policies.py`
- Modify: `tests/characterization/test_inference.py`
- Modify: `tests/characterization/test_inputs_and_outputs.py`
- Modify: `tests/characterization/test_process_scout.py`
- Modify: `tests/characterization/test_requirement_path.py`
- Modify: `tests/unit/test_atomic_write.py`
- Modify: `tests/unit/test_identity.py`
- Modify: `tests/unit/test_inference_identity.py`
- Modify: `tests/unit/test_migrate.py`
- Modify: `tests/unit/test_output_filenames.py`
- Modify: `tests/unit/test_ui_settings.py`

### Task 21 exact interface member map

| IDs | Ordered members |
| --- | --- |
| `CLI-SCHED-001..006` | defaults/help; empty success; one-scout success; partial failure; top-level exception; keyboard interrupt. |
| `CLI-PDF-001..008` | registry references Task 18’s eight PDF-CLI cases and contexts; it does not create a second expectation. |
| `UI-IMPORT-001..002` | import with sandbox root creates only that tree; plain collection never writes to platform data root. |
| `UI-METHOD-001..012` | wrong HTTP method returns 405 for health, status, scouts, PDF start, schedule start, pause, resume, events, runs, open report, generate emails, open email folder. |
| `UI-ROUTE-001..031` | health success; status absent/present; scouts absent/present; PDF no-files/busy/accepted/worker-error; schedule missing/busy/accepted/worker-error; pause inactive/active; resume inactive/active; events missing/success/disconnect; runs empty/multiple/corrupt; open-report missing/no-report/success; email missing/success/corrupt-JSON; open-folder missing/success. |
| `SSE-FRAME-001..006` | batch start; scout start/done; pause/resume; batch done; error followed by terminal end. |
| `SSE-CLEAN-001..004` | success; worker exception; terminal attendee failure; client disconnect. |
| `RUN-LIST-001..004` | empty; reverse-sorted multiple; corrupt summary ignored; missing optional report. |
| `RUN-ID-001..004` | valid; traversal; absolute; separator-containing. |
| `UI-ACTION-001..004` | browser open; Windows-only folder open; email generation; unguarded persisted JSON. |
| `STATIC-UI-001..003` | successful terminal DOM; progress then paused/resumed; error terminal DOM. |
| `DESK-PORT-001..002` | free loopback port closes probe; bind failure surfaces. |
| `DESK-READY-001..003` | immediate readiness; two failures then success; timeout. |
| `DESK-MODE-001..004` | browser mode; native mode; server-start failure; keyboard interrupt. |
| `BOOT-PATH-001..004` | override; default; spaces; Unicode. |
| `BOOT-MARK-001..006` | missing; valid; corrupt JSON; schema mismatch; Python mismatch; requirements-hash mismatch. |
| `BOOT-SYNC-001..004` | file copy; directory copy; missing optional source; frozen/unfrozen source roots and copied startup. |
| `PLAT-WIN-001..008` | reserved device; trailing dot/space; case collision; slash/backslash; drive; UNC; extended path; traversal. |
| `PLAT-MAC-001..005` | NFC/NFD equivalence; case collision; volume root; spaces/Unicode; traversal. |

`UI-IMPORT-001`, `UI-ACTION-*`, and unguarded JSON cases that differ from target behavior are
intentional-change rows owned by Slice 2. Platform rows are pure simulated observations over
strings and `PureWindowsPath`/`PurePosixPath`; they do not monkeypatch `sys.platform` and do
not claim a native filesystem or installer result.

```python
# tests/matrix/cases/interface_cases.py
@dataclass(frozen=True, slots=True)
class InterfaceObservation:
    status: int
    body: object
    headers: tuple[tuple[str, str], ...] = ()
    events: tuple[str, ...] = ()
    remaining_resources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InterfaceCase:
    meta: CaseMetadata
    method: str
    route: str
    state: str
    expected_legacy: InterfaceObservation


# tests/matrix/cases/platform_cases.py
@dataclass(frozen=True, slots=True)
class PlatformCase:
    meta: CaseMetadata
    raw: str
    expected_components: tuple[str, ...]
    expected_collision_key: str
    expected_safe: bool
    expected_reason: str
```

- [ ] **Step 1: Add interface/platform axes and boundary inventory**

The route boundary list contains the exact 12 live FastAPI routes and methods. Add boundaries
for `scout_schedule_cli.main/async_main`, `pdf_to_scouts.main`, `ui.server` handlers,
`run_app.free_port/start_server/wait_until_ready/main`, `bootstrap.paths.resolve_root/get_paths`,
`bootstrap.marker.read_marker/is_environment_valid`, and `bootstrap.source_sync.sync_app_source`.

Run: `uv run pytest tests/matrix/test_registry.py -q`

Expected: FAIL listing missing interface/platform members and contexts.

- [ ] **Step 2: Add the isolated legacy UI harness**

```python
@contextmanager
def load_legacy_ui(data_root: Path) -> Iterator[ModuleType]:
    old = os.environ.get("SCOUTMB_DATA_DIR")
    os.environ["SCOUTMB_DATA_DIR"] = str(data_root)
    sys.modules.pop("ui.server", None)
    try:
        module = importlib.import_module("ui.server")
        module.operations.clear()
        module.busy.update({"pdf-extract": False, "schedule-download": False})
        module.current_download.clear()
        yield module
    finally:
        sys.modules.pop("ui.server", None)
        if old is None:
            os.environ.pop("SCOUTMB_DATA_DIR", None)
        else:
            os.environ["SCOUTMB_DATA_DIR"] = old
```

The harness also cancels and awaits tasks it starts, closes TestClient/browser resources, and
asserts empty operations/current-download state on exit.

- [ ] **Step 3: Add failing route/method tests**

Use FastAPI `TestClient` for synchronous routes and `httpx.AsyncClient` with ASGI transport for
streaming/disconnect cases. For every route case compare exact status, ordered JSON object,
side effects, task state, and generated relative files. For every method case compare 405 and
the exact `allow` header.

Run: `uv run pytest tests/characterization/test_interface_matrix.py -k "route or method" -q`

Expected: FAIL until all 43 route/method rows are populated.

- [ ] **Step 4: Execute real SSE generators and cleanup paths**

Iterate `StreamingResponse.body_iterator`; compare complete ordered `data: <json>\n\n`
frames and one terminal end. Disconnect by closing the async iterator, then assert the
operation is removed and no task, queue item, busy flag, browser context, or current download
remains. Source-text searches for event names are forbidden.

- [ ] **Step 5: Add static UI browser rows**

Serve the real `ui/static` directory with loopback fake API/SSE routes through the Task 19
guarded context. Compare DOM status text, progress values, disabled controls, terminal state,
and browser-console errors. Task-local verification omits `--matrix-lane browser` because the
complete browser registry also contains Task 19 and Task 22 execution keys.

- [ ] **Step 6: Add desktop and bootstrap tests at external seams**

Inject socket bind, `urllib.request.urlopen`, monotonic clock, sleeper, server launcher,
webbrowser, and webview seams; do not sleep or open a real window. Build `AppPaths` entirely
under `tmp_path`. For source sync, construct the exact `_FILES`, `_DIRS`, and support-file
tree and compare bytes and relative destinations.

- [ ] **Step 7: Add pure Windows and macOS cases**

Define domain observations containing normalized component tuple, safe/unsafe decision,
collision key, and bounded reason. Windows uses `PureWindowsPath`; macOS uses Unicode
`normalize("NFC", value)` plus casefolded collision keys. Expected values are explicit case
data and do not call the normalizer being tested.

- [ ] **Step 8: Remove every remaining test `sys.path.insert` and private fake import**

Delete the path mutation from the ten existing files listed under this task. Replace imports
of `_Browser`/`_Resp` from `test_process_scout.py` with `tests.fakes.acquisition`. Keep each
existing assertion until its named matrix execution is present and passing; then delete only
the exact duplicate test in the same commit.

- [ ] **Step 9: Run Task 21 verification**

Run: `uv run pytest tests/characterization/test_interface_matrix.py tests/characterization/test_platform_matrix.py tests/matrix/test_registry.py -q`

Expected: every non-browser interface/platform execution passes with no task leak.

Run: `uv run pytest tests/characterization/test_static_ui.py -m playwright --require-browser -q`

Expected: three `STATIC-UI-*` executions pass with zero external requests.

Run: `uv run pytest tests/unit tests/characterization -m "not playwright" -q`

Expected: existing Slice 1a behavior remains green after helper migration.

Run: `uv run ruff check tests/matrix/cases/interface_cases.py tests/matrix/cases/platform_cases.py tests/harnesses tests/characterization tests/unit`

Expected: exit 0.

Run: `uv run mypy tests/matrix/cases/interface_cases.py tests/matrix/cases/platform_cases.py tests/harnesses`

Expected: success with no issues.

- [ ] **Step 10: Commit Task 21**

```bash
git add tests/matrix/cases/interface_cases.py tests/matrix/cases/platform_cases.py tests/matrix/axes.py tests/matrix/boundaries.py tests/matrix/policies.py tests/harnesses tests/characterization tests/unit
git commit -m "test: characterize interfaces lifecycle and platform seams"
```

---

## Task 22: Add variable/scale profiles, vertical flows, baselines, CI, and Gate 1b

**Depends on:** Tasks 17–21

**Files:**

- Create: `tests/matrix/scale_profile.py`
- Create: `tests/factories/scale.py`
- Create: `tests/scale/test_profiles.py`
- Create: `tests/vertical/test_legacy_flows.py`
- Create: `tests/performance/test_phase_a_baseline.py`
- Create: `tools/measure_baseline.py`
- Create: `tools/check_phase_a_coverage.py`
- Create: `tests/baselines/phase_a.json`
- Modify: `tests/matrix/axes.py`
- Modify: `tests/matrix/boundaries.py`
- Modify: `tests/matrix/registry.py`
- Modify: `tests/conftest.py`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`

### Task 22 exact profile and flow map

| IDs | Exact contract |
| --- | --- |
| `SCALE-000/001/002` | zero; one; two same-name/different-ID attendees. |
| `SCALE-SMALL-001..003` | 3 attendees/grouped; 7 attendees/reversed; 11 attendees/interleaved; repeatable by profile version and seed. |
| `SCALE-CANON-022` | 22 attendees; 103 raw/98 deduplicated classes; 98 requirement payloads; 4,858 requirements; every authoritative marginal above. |
| `SCALE-LARGE-050` | 50 attendees; deterministic allocation/order; request count equals nonblank deduplicated class IDs. |
| `SCALE-PROP-001..002` | bounded counts 0–60; arbitrary stable ordering/grouping with identity isolation and partition totals. |
| `SCALE-PAIR-001` | reordering one synthetic marginal pairing leaves each independent marginal/topology assertion unchanged. |
| `SCALE-PAIR-002` | requesting correlation evidence raises `UnsupportedSyntheticCorrelation`. |
| `FLOW-SUCCESS-001` | generated PDF → attendee CSV → real loader → strict acquisition → real inference/writers → real UI read routes; all boundaries and artifacts proven. |
| `FLOW-PARTIAL-001` | two attendees, one terminal acquisition failure; exact exit/events/partial artifacts/cleanup. |
| `FLOW-BROWSER-001` | local Playwright schedule interception → acquisition → static UI terminal success; loopback only. |
| `PERF-REQ-001..003` | zero, canonical, and large request counts equal schedule requests plus one requirement request per nonblank deduplicated class ID; legacy includes `HAS_REQ=0`. |
| `PERF-GROWTH-001` | for profiles 11, 22, and 50, path/tree node visits are at most `6 * requirement_rows + 2 * class_rows`. |
| `PERF-GROWTH-002` | generated artifact data rows equal `attendees + classes + requirements + errors`; serialized files remain the fixed schema count plus per-attendee conditional email files. |

### Deterministic generator algorithm

`SCALE-CANON-022` allocates 98 deduplicated classes across 22 attendees as ten attendees with
five and twelve with four. Add one duplicate to each of the first five attendees, producing
103 raw rows. Each added duplicate is the incomplete member of an incomplete→complete pair
sharing one class ID; legacy dedup retains the completed member. This yields raw completion
`{"0": 41, "1": 62}` and deduplicated completion `{"0": 36, "1": 62}` exactly. Allocate
4,858 requirements across the 98 deduplicated class payloads as the first 56 with 50 and the
remaining 42 with 49.

Use this exact largest-remainder function for smaller profiles:

```python
def allocate(total: int, weighted_keys: tuple[tuple[str, int], ...]) -> dict[str, int]:
    denominator = sum(weight for _, weight in weighted_keys)
    exact = [(key, Fraction(total * weight, denominator)) for key, weight in weighted_keys]
    result = {key: value.numerator // value.denominator for key, value in exact}
    remainder = total - sum(result.values())
    ranked = sorted(
        enumerate(exact),
        key=lambda item: (
            -(item[1][1] - result[item[1][0]]),
            item[0],
        ),
    )
    for _, (key, _) in ranked[:remainder]:
        result[key] += 1
    return result
```

Pair independent marginals by sorting row indices with
`sha256(f"{profile_version}:{seed}:{axis_id}:{row_index}".encode()).digest()` and assign each
expanded marginal in that order. This is stable across Python versions and never copies a
private row or string.

Synthetic output IDs are deterministic UUIDs with RFC 4122 variant and version-4 bits; they
are test identities, not a claim that production UUIDv4 generation is deterministic:

```python
def synthetic_uuid4(profile_version: int, seed: str, attendee_index: int) -> UUID:
    raw = bytearray(
        sha256(f"{profile_version}:{seed}:attendee:{attendee_index}".encode()).digest()[:16]
    )
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return UUID(bytes=bytes(raw))
```

```python
class EvidenceKindForProfile(StrEnum):
    MARGINAL = "marginal"
    TOPOLOGY = "topology"
    ORDERING = "ordering"
    REQUEST_COUNT = "request-count"
    CORRELATION = "correlation"


@dataclass(frozen=True, slots=True)
class ScaleProfile:
    profile_id: str
    schema_version: int
    profile_version: int
    seed: str
    attendee_count: int
    raw_class_count: int
    deduplicated_class_count: int
    requirement_count: int
    pairing_is_synthetic: bool = True


class UnsupportedSyntheticCorrelation(RuntimeError):
    pass


def require_supported(profile: ScaleProfile, evidence: EvidenceKindForProfile) -> None:
    if evidence is EvidenceKindForProfile.CORRELATION:
        raise UnsupportedSyntheticCorrelation(profile.profile_id)
```

- [ ] **Step 1: Add scale/flow axes and verify missing-member failures**

Add every profile, pairing, performance, and flow row to independent manifests. Add boundaries
for every edge in both vertical flows and the local-browser flow.

Run: `uv run pytest tests/matrix/test_registry.py -q`

Expected: FAIL listing missing scale/flow execution keys.

- [ ] **Step 2: Write failing allocation and pairing tests**

Assert the exact canonical topology, every marginal dictionary, small-profile totals, stable
same-seed bytes, different-seed ordering with equal marginals, and correlation rejection.

Run: `uv run pytest tests/scale/test_profiles.py -q`

Expected: FAIL because scale factories are absent.

- [ ] **Step 3: Implement versioned deterministic profiles**

Define `ScaleProfile(profile_id, schema_version, profile_version, seed, attendee_count,
raw_class_count, deduplicated_class_count, requirement_count, pairing_is_synthetic=True)`.
Implement the exact topology, `allocate`, SHA-256 pairing order, output UUID generation from a
synthetic deterministic namespace, and bounded Hypothesis builders. Serialization contains
profile metadata and aggregates only, never generated names, IDs, descriptions, or paths.

- [ ] **Step 4: Run scale tests**

Run: `uv run pytest tests/scale/test_profiles.py tests/matrix/test_registry.py -q`

Expected: all scale, pair, and property rows pass.

- [ ] **Step 5: Add failing success and partial vertical flows**

Each flow asserts preconditions before execution: generated PDF exists; attendee CSV has exact
headers/rows; strict fake script is nonempty; all real boundary probes begin at zero. After
execution, assert each required probe is positive, exact requests/events/artifacts/schemas,
truthful return code, and complete cleanup. Do not replace loader, inference, writer, or route.

Run: `uv run pytest tests/vertical/test_legacy_flows.py -k "success or partial" -q`

Expected: FAIL until every real boundary is wired.

- [ ] **Step 6: Implement the browser vertical flow**

Reuse the guarded browser context and loopback service; execute real interception and static
UI behavior. Assert all required `FLOW-BROWSER-001` probes and zero egress. Do not pass a full
lane option in this task-local command.

Run: `uv run pytest tests/vertical/test_legacy_flows.py -m playwright --require-browser -q`

Expected: `FLOW-BROWSER-001` passes when browser capability is present.

- [ ] **Step 7: Add exact request and growth tests**

Instrument runner/harness counters rather than wall time. Assert the two formulas in the task
map for named profiles and require all strict scripts to be consumed. No timing threshold is
stored.

Run: `uv run pytest tests/performance/test_phase_a_baseline.py -q`

Expected: all five `PERF-*` rows pass.

- [ ] **Step 8: Implement coverage area checking before capturing a baseline**

Define these exact area patterns in `tests/matrix/boundaries.py`:

```python
COVERAGE_AREAS = (
    CoverageAreaSpec("schedule", ("scout_schedule_cli.py",)),
    CoverageAreaSpec("pdf", ("pdf_to_scouts.py",)),
    CoverageAreaSpec("ui", ("ui/server.py",)),
    CoverageAreaSpec("desktop", ("run_app.py",)),
    CoverageAreaSpec(
        "bootstrap",
        ("bootstrap/paths.py", "bootstrap/marker.py", "bootstrap/source_sync.py"),
    ),
)
```

`tools/check_phase_a_coverage.py` reads coverage JSON, computes statement and branch percent
per area, fails if either is below the checked-in floor, and fails if a missing line/branch is
not matched by an exact `BranchExclusion(file, line, branch_to)` with stable ID and rationale.
`branch_to=None` denotes a missing statement; an integer identifies one missing branch arc.
It also fails on stale exclusions that no longer match a missing location. Initial exclusions are
empty. If execution exposes a structurally unreachable branch, stop for maintainer review
before adding its exact line and rationale; do not weaken a floor or add a broad range.

- [ ] **Step 9: Run scoped coverage and close every unreviewed gap**

Run: `uv run coverage erase`

Expected: exit 0.

Run: `uv run coverage run --branch -m pytest -m "not live_service and not playwright and not private_corpus" -q`

Expected: default synthetic suite passes.

Run: `uv run coverage json -o build/phase-a-coverage.json`

Expected: `build/phase-a-coverage.json` is created.

Run: `uv run python tools/check_phase_a_coverage.py --coverage-json build/phase-a-coverage.json --exclusions tests/matrix/boundaries.py --require-complete`

Expected: FAIL listing exact uncovered lines/branches until each gains a case or a reviewed
stable exclusion; final rerun exits 0.

- [ ] **Step 10: Implement aggregate baseline update/check modes**

`tools/measure_baseline.py` accepts exactly one of `--update PATH` or `--check PATH` and
`--profile canonical-22`. The JSON schema is:

```json
{
  "schema_version": 1,
  "profile_version": 1,
  "profile_id": "canonical-22",
  "case_ids": [],
  "request_counts": {},
  "row_counts": {},
  "coverage_areas": {},
  "branch_exclusion_ids": []
}
```

The generated file replaces the empty containers with sorted aggregate values from the named
profile and coverage JSON. It rejects absolute paths, host/user names, timestamps, hashes,
private values, free-form descriptions, and unknown keys. Check mode recomputes in memory and
prints only `phase-a baseline: match` or a sorted aggregate-key mismatch.

- [ ] **Step 11: Capture and verify the checked-in baseline explicitly**

Run: `uv run python tools/measure_baseline.py --profile canonical-22 --coverage-json build/phase-a-coverage.json --update tests/baselines/phase_a.json`

Expected: one deterministic aggregate-only baseline is written.

Run: `uv run python tools/measure_baseline.py --profile canonical-22 --coverage-json build/phase-a-coverage.json --check tests/baselines/phase_a.json`

Expected: `phase-a baseline: match`.

Run: `uv run python tools/check_private_data.py --corpus raw_data tests tools/measure_baseline.py`

Expected: `private-data findings: 0`.

- [ ] **Step 12: Add CI jobs for every non-private capability**

Update CI so static quality runs Ruff, format, Mypy, lock check, and registry audit; the
default matrix runs on Ubuntu and Windows. A `coverage-baseline` job runs the default suite
under coverage, writes coverage JSON, then invokes both check-mode tools. Playwright runs
`uv run playwright install --with-deps chromium` and the full browser lane on Ubuntu. Add
`egress-denied` after dependency installation:

```yaml
- name: Deny new non-loopback egress
  run: sudo iptables -I OUTPUT 1 ! -o lo -m conntrack --ctstate NEW -j REJECT
- name: Run offline default lane
  run: uv run pytest -m "not live_service and not playwright and not private_corpus" --matrix-lane default -q
```

CI never requires `raw_data/`; the authentic lane remains required locally for Gate 1b.

- [ ] **Step 13: Run the complete Gate 1b commands**

Run each command exactly as written in “Gate 1b” below. Do not replace lane commands with one
combined marker expression.

- [ ] **Step 14: Regenerate the sidecar after the Markdown is final**

Update every sidecar file list and verification command, set its digest to the SHA-256 of this
Markdown file’s exact bytes, parse it with `json.loads`, and verify task IDs/headings match.

- [ ] **Step 15: Commit Task 22 and Gate 1b**

```bash
git add .github/workflows/ci.yml pyproject.toml tests/conftest.py tests/matrix tests/factories/scale.py tests/scale tests/vertical tests/performance tests/baselines/phase_a.json tools/measure_baseline.py tools/check_phase_a_coverage.py docs/superpowers/plans/2026-07-22-slice-1b-full-phase-a-characterization.md.tasks.json
git commit -m "test: close exhaustive Phase A characterization gate"
```

## Gate 1b — go/no-go

### Static quality and registry integrity

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv lock --check
uv run pytest tests/matrix/test_registry.py tests/plugins/test_matrix_gate.py -q
uv run python tools/check_private_data.py tests
```

### Default synthetic lane

```bash
uv run pytest -m "not live_service and not playwright and not private_corpus" --matrix-lane default -q
```

### Required local-browser lane

```bash
uv run pytest -m playwright --require-browser --matrix-lane browser -q
```

### Required authentic read-only lane

```bash
uv run pytest -m private_corpus --corpus-dir raw_data --require-corpus --matrix-lane authentic -q
uv run python tools/check_private_data.py --corpus raw_data tests
```

### Scoped legacy branch evidence and checked-in baseline

```bash
uv run coverage erase
uv run coverage run --branch -m pytest -m "not live_service and not playwright and not private_corpus" --matrix-lane default -q
uv run coverage json -o build/phase-a-coverage.json
uv run python tools/check_phase_a_coverage.py --coverage-json build/phase-a-coverage.json --baseline tests/baselines/phase_a.json --exclusions tests/matrix/boundaries.py --require-complete
uv run python tools/measure_baseline.py --profile canonical-22 --coverage-json build/phase-a-coverage.json --check tests/baselines/phase_a.json
```

### GO conditions

- [ ] Every command exits 0.
- [ ] Every required preserve/intentional-change execution key passes exactly once in its lane.
- [ ] Every new-acceptance case has an exact target observation and implementing owner;
  infrastructure rows are owned by Slice 1b and future application rows by a later slice.
- [ ] Every finite member, material interaction, public boundary, and critical flow maps to a
  case ID and all declared contexts map to execution keys.
- [ ] No required key is skipped, deselected, duplicated, missing, or drawn from an empty lane.
- [ ] All 26 shapes execute through path and tree/consumer contexts; HTML/email reuse is
  visible as separate context keys.
- [ ] Default/browser lanes report zero external requests; the existing application-policy
  cases execute, future gateway wiring is owned by Slice 2, and the CI egress-denied job passes.
- [ ] Authentic tests report the exact JSON/PDF aggregates and identical before/after content
  fingerprints. Git status is not used as evidence because `raw_data/` is ignored.
- [ ] All six surface classes, ten egress paths, formula prefixes, platform seams, strict-fake
  misuse cases, publication failures, async cleanup paths, and vertical flows execute.
- [ ] Every missing scoped line/branch has a stable reviewed exclusion, and every exclusion
  still matches a missing location; each area meets its checked-in no-regression floors.
- [ ] `tests/baselines/phase_a.json` matches recomputation and contains only allowed aggregate
  keys; no private/machine-identifying value or wall-clock threshold exists.
- [ ] Slice 1a tests remain green.

Any failed condition is **NO-GO**. Slice 2 must not start until Gate 1b is green.

## Recovery and compatibility

- Generated inputs and outputs are synthetic and disposable; only aggregate baseline JSON is
  committed.
- An unexpected legacy observation does not authorize a production fix. Stop, record the
  exact normalized observation, classify it, and obtain review before changing target intent.
- If authentic aggregates differ, stop and inspect schema/provenance. Do not weaken the oracle
  or copy a private row into a test.
- Ordinary development may use the plugin’s exact capability skip. Gate commands convert
  missing browser/corpus capabilities to failure.
- Baseline updates are never part of the Gate command. Review the aggregate diff before an
  explicit `--update` and commit it with the behavior change that explains it.
