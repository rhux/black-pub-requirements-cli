"""Request-count and growth-bound performance baselines (Task 22, Slice 1b Phase A).

Covers ``PERF-REQ-001..003`` and ``PERF-GROWTH-001..002``. Every assertion here is a
deterministic COUNT or BOUND derived from instrumenting real production code (a real
``StrictScript`` call ledger, or a counting monkeypatch wrapper around real package inference
functions) -- never a wall-clock timing threshold. Nothing here is stored as a benchmark
baseline; these are characterization assertions like every other matrix row.

Repointed off scout_schedule_cli.py in Slice 2b B10.4 (Step 2, one of three files an independent
review found still importing the flat module directly): process_scout's package equivalent is
AcquisitionService.process, a keyword-only call built through the same gateway/retry_policy/sink
wiring tests/integration/test_acquisition_pipeline.py already uses -- not a 4-positional-arg
call. annotate_requirement_statuses' package equivalent is
scoutmb.features.reporting.service._annotate_requirement_statuses, which reaches
requirement_path/choice_requirement_count through scoutmb.core.inference.tree/status's own
bound module-level imports -- the counting monkeypatch must target THOSE modules, not
scoutmb.core.inference.numbering itself, or the patched name is never the one actually called.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from tests.factories.scale import SyntheticDataset, build_dataset, canonical_profile, profile
from tests.fakes.acquisition import StrictScript
from tests.fakes.browser import StrictFakeBrowser
from tests.fakes.clock import FakeClock
from tests.matrix.cases.acquisition_cases import ExpectedRequest, ScriptedResponse

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutInput, ScoutResult
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
from scoutmb.features.reporting import service as reporting_service
from scoutmb.interfaces.cli.composition import build_reporting_service

pytestmark = pytest.mark.vertical


class _RecordingSleeper:
    async def sleep(self, seconds: float) -> None:
        pass

    def monotonic(self) -> float:
        return 0.0


class _ZeroJitter:
    def jitter(self, low: float, high: float) -> float:
        return low


# ---------------------------------------------------------------------------------------------
# PERF-REQ-001..003: request count == schedule requests + one requirement request per nonblank
# deduplicated class id (including HAS_REQ="0" classes -- ACQ-HASREQ-002's characterized current
# legacy behavior: process_scout never gates a requirement request on HAS_REQ).
# ---------------------------------------------------------------------------------------------


def _schedule_row_for(
    class_id: str, dataset: SyntheticDataset, completion: str
) -> dict[str, object]:
    return {
        "classP4ID": class_id,
        "CLASS_NAME": f"MoTuWeTh - Chess - {class_id} (Pavilion)",
        "CLASS_NAME_ONLY": "Chess",
        "CLASS_NBR": class_id,
        "PERIOD_NAME": "A Block",
        "CLASS_STIME": "09:00 AM",
        "STIME": "09:00:00",
        "LOCATION_ROOM_NAME": "Pavilion",
        "HAS_REQ": "1",
        "CLASS_COMPLETED": completion,
        "SES_LKP_PERIOD_TYPE_ID": "1",
    }


def _build_full_script(dataset: SyntheticDataset) -> tuple[StrictScript, list[ScoutInput]]:
    """Builds one StrictScript covering the ENTIRE dataset (every attendee's schedule request,
    raw duplicated rows included, followed by one requirement request per that attendee's
    DEDUPLICATED class id) plus the matching ``ScoutInput`` list -- real AcquisitionService
    dedup logic (schedule_rows dict-keyed by classP4ID) is what collapses the raw duplicates back
    down to ``len(deduped_class_ids)`` requests, exactly proving the request-count formula
    against the real service rather than against the factory's own bookkeeping."""
    scouts: list[ScoutInput] = []
    pairs: list[tuple[ExpectedRequest, ScriptedResponse]] = []
    for attendee in dataset.attendees:
        scouts.append(
            ScoutInput(
                name=attendee.name,
                url=f"https://scoutingevent.com/mobile/x?t=TESTTOKEN_SYN{attendee.index:06d}",
            )
        )
        raw_rows = [
            _schedule_row_for(class_id, dataset, completion)
            for class_id, completion in zip(
                attendee.raw_class_ids,
                attendee.raw_completions,
                strict=True,
            )
        ]
        pairs.append(
            (
                ExpectedRequest("schedule", attendee.upstream_id),
                ScriptedResponse(value={"status": {"status": 1}, "data": raw_rows}),
            )
        )
        for class_id in attendee.deduped_class_ids:
            pairs.append(
                (
                    ExpectedRequest("requirement", attendee.upstream_id, class_id),
                    ScriptedResponse(value={"status": {"status": 1}, "data": []}),
                )
            )
    return StrictScript(tuple(pairs)), scouts


async def _run_request_count_case(dataset: SyntheticDataset, raw_dir: Path) -> int:
    script, scouts = _build_full_script(dataset)
    clock = FakeClock()
    browser = StrictFakeBrowser(script, clock)
    gateway = PlaywrightScoutingEventGateway(browser, allow_dead_assets=False)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99)
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
    config = AcquisitionConfig(timeout_seconds=5, request_delay_ms=0)
    run_identity = RunIdentity()
    for scout in scouts:
        result = await service.process(
            scout=scout, config=config, raw_dir=raw_dir, run_identity=run_identity
        )
        assert not result.errors  # every scripted response is a clean success
    script.assert_consumed()
    return len(script.calls)


def _expected_request_count(dataset: SyntheticDataset) -> int:
    return len(dataset.attendees) + len(dataset.deduped_class_ids)


@pytest.mark.parametrize(
    ("case_id", "make_profile"),
    [
        pytest.param(
            "PERF-REQ-001",
            lambda: profile("SCALE-000", attendee_count=0, deduplicated_class_count=0),
            marks=pytest.mark.matrix_case(case_id="PERF-REQ-001", context_id="run", lane="default"),
        ),
        pytest.param(
            "PERF-REQ-002",
            canonical_profile,
            marks=pytest.mark.matrix_case(case_id="PERF-REQ-002", context_id="run", lane="default"),
        ),
        pytest.param(
            "PERF-REQ-003",
            lambda: profile("SCALE-LARGE-050", attendee_count=50, deduplicated_class_count=150),
            marks=pytest.mark.matrix_case(case_id="PERF-REQ-003", context_id="run", lane="default"),
        ),
    ],
)
def test_perf_req_request_count_formula(case_id: str, make_profile, tmp_path: Path) -> None:
    dataset = build_dataset(make_profile())
    actual = asyncio.run(_run_request_count_case(dataset, tmp_path / "raw"))
    expected = _expected_request_count(dataset)
    assert actual == expected, f"{case_id}: {actual} != {expected}"


# ---------------------------------------------------------------------------------------------
# PERF-GROWTH-001: path/tree node visits during real annotate_requirement_statuses execution are
# at most 6*requirement_rows + 2*class_rows.
# ---------------------------------------------------------------------------------------------


def _synthetic_requirement_rows(row_count: int, class_rows: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for i in range(row_count):
        class_id = f"C{i % class_rows}"
        rows.append(
            {
                "scout_name": "Synthetic Scout",
                "attendee_id": "9000000",
                "class_p4_id": class_id,
                "requirement_number": str((i % 9) + 1),
                "requirement_type_id": "1",
                "completed_requirement": False,
                "description": "",
            }
        )
    return rows


@pytest.mark.parametrize(
    ("row_count", "class_rows"),
    [
        (11, 3),
        # Only ONE of these three growth-bound instances carries the PERF-GROWTH-001 matrix_case
        # mark -- the case is declared once (member "growth-bound"), and marking every
        # parametrized instance would make matrix_gate see it as executed more than once.
        pytest.param(
            22,
            5,
            marks=pytest.mark.matrix_case(
                case_id="PERF-GROWTH-001", context_id="run", lane="default"
            ),
        ),
        (50, 10),
    ],
    ids=["profile-11", "profile-22", "profile-50"],
)
def test_perf_growth_001_bounded_node_visits(
    row_count: int, class_rows: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scoutmb.core.inference import status as status_module
    from scoutmb.core.inference import tree as tree_module

    visits = {"count": 0}
    real_requirement_path = tree_module.requirement_path
    real_choice_count = status_module.choice_requirement_count

    def counting_requirement_path(number: str, current_top_level: str | None):
        visits["count"] += 1
        return real_requirement_path(number, current_top_level)

    def counting_choice_count(description: str):
        visits["count"] += 1
        return real_choice_count(description)

    # These monkeypatches must target scoutmb.core.inference.tree/status's OWN bound names, not
    # scoutmb.core.inference.numbering -- both modules import requirement_path/
    # choice_requirement_count at module scope (`from ... import name`), which binds the name
    # into their own namespace at import time. Patching numbering.py's copy would leave the name
    # tree.py/status.py actually call untouched.
    monkeypatch.setattr(tree_module, "requirement_path", counting_requirement_path)
    monkeypatch.setattr(status_module, "choice_requirement_count", counting_choice_count)

    rows = _synthetic_requirement_rows(row_count, class_rows)
    annotated = reporting_service._annotate_requirement_statuses(rows)
    assert len(annotated) == row_count

    bound = 6 * row_count + 2 * class_rows
    assert visits["count"] <= bound, f"{visits['count']} visits exceeds bound {bound}"


# ---------------------------------------------------------------------------------------------
# PERF-GROWTH-002: generated artifact data rows == attendees + classes + requirements + errors;
# serialized files == fixed schema count + per-attendee conditional email files.
# ---------------------------------------------------------------------------------------------


@pytest.mark.matrix_case(case_id="PERF-GROWTH-002", context_id="run", lane="default")
def test_perf_growth_002_artifact_row_and_file_counts(tmp_path: Path) -> None:
    scout_a = ScoutResult(
        name="Avery Archer",
        qr_url="https://scoutingevent.com/mobile/x?t=TESTTOKEN_A",
        attendee_id="90000001",
        classes=[
            ClassRecord(
                scout_name="Avery Archer",
                attendee_id="90000001",
                class_number="26MB1",
                class_p4_id="2000001",
                class_name="Chess",
                days="MoTuWeTh",
                period_name="A",
                start_time="9:00 AM",
                start_time_24h="09:00:00",
                location="Pavilion",
                has_requirements=True,
                class_completed=False,
                raw_class_name="Chess",
            )
        ],
        requirements=[
            RequirementRecord(
                scout_name="Avery Archer",
                attendee_id="90000001",
                class_number="26MB1",
                class_p4_id="2000001",
                merit_badge_name="Chess",
                requirement_id="r1",
                requirement_type_id="1",
                requirement_number="1",
                description="Do a thing.",
                completed_requirement=False,
                completed_class=False,
                requirement_on_event=True,
                present_days="MoTuWeTh",
            ),
            RequirementRecord(
                scout_name="Avery Archer",
                attendee_id="90000001",
                class_number="26MB1",
                class_p4_id="2000001",
                merit_badge_name="Chess",
                requirement_id="r2",
                requirement_type_id="1",
                requirement_number="2",
                description="Do another.",
                completed_requirement=True,
                completed_class=False,
                requirement_on_event=True,
                present_days="MoTuWeTh",
            ),
        ],
        errors=[],
    )
    scout_b = ScoutResult(
        name="Bo Baker",
        qr_url="https://scoutingevent.com/mobile/x?t=TESTTOKEN_B",
        attendee_id="90000002",
        classes=[
            ClassRecord(
                scout_name="Bo Baker",
                attendee_id="90000002",
                class_number="26MB2",
                class_p4_id="2000002",
                class_name="Fire Safety",
                days="MoTuWeTh",
                period_name="B",
                start_time="10:00 AM",
                start_time_24h="10:00:00",
                location="Pavilion",
                has_requirements=True,
                class_completed=True,
                raw_class_name="Fire Safety",
            )
        ],
        requirements=[
            RequirementRecord(
                scout_name="Bo Baker",
                attendee_id="90000002",
                class_number="26MB2",
                class_p4_id="2000002",
                merit_badge_name="Fire Safety",
                requirement_id="r1",
                requirement_type_id="1",
                requirement_number="1",
                description="Done.",
                completed_requirement=True,
                completed_class=True,
                requirement_on_event=True,
                present_days="MoTuWeTh",
            )
        ],
        errors=[],
    )
    scout_c = ScoutResult(
        name="Casey Carter",
        qr_url="https://scoutingevent.com/mobile/x?t=TESTTOKEN_C",
        attendee_id="90000003",
        classes=[],
        requirements=[],
        errors=["schedule request failed"],
    )
    results = [scout_a, scout_b, scout_c]

    attendees = len(results)
    classes = sum(len(r.classes) for r in results)
    requirements = sum(len(r.requirements) for r in results)
    errors = sum(len(r.errors) for r in results)

    output_dir = tmp_path / "run-perf-growth-002"
    build_reporting_service().publish(
        output_dir,
        results,
        generated_at_local="2026-01-01 00:00:00",
        generated_at_iso="2026-01-01T00:00:00",
        run_identity=RunIdentity(),
        generate_html=False,
        generate_email_report=True,
    )

    scouts_json = json.loads((output_dir / "scouts.json").read_text(encoding="utf-8"))
    assert len(scouts_json) == attendees

    with (output_dir / "classes.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        import csv

        classes_rows = list(csv.DictReader(stream))
    with (output_dir / "requirements.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        import csv

        requirements_rows = list(csv.DictReader(stream))
    with (output_dir / "errors.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        import csv

        errors_rows = list(csv.DictReader(stream))

    assert len(classes_rows) == classes == 2
    assert len(requirements_rows) == requirements == 3
    assert len(errors_rows) == errors == 1
    total_data_rows = (
        len(scouts_json) + len(classes_rows) + len(requirements_rows) + len(errors_rows)
    )
    assert total_data_rows == attendees + classes + requirements + errors == 9

    # Fixed schema files (generate_html=False -> no report.html).
    fixed_files = {"scouts.json", "classes.csv", "requirements.csv", "errors.csv", "summary.json"}
    top_level_files = {p.name for p in output_dir.iterdir() if p.is_file()}
    assert top_level_files == fixed_files

    # Conditional email files: only scout_a has an actionable incomplete leaf requirement
    # (requirement "1"), so exactly one .txt + one .html are written for it, plus the
    # always-present (when generate_email_report=True) missing_requirements.csv.
    emails_dir = output_dir / "emails"
    email_files = {p.name for p in emails_dir.iterdir() if p.is_file()}
    assert "missing_requirements.csv" in email_files
    per_attendee_email_files = email_files - {"missing_requirements.csv"}
    assert len(per_attendee_email_files) == 2  # one .txt + one .html for scout_a only
    assert all(name.endswith((".txt", ".html")) for name in per_attendee_email_files)


def test_performance_registry_is_structurally_valid() -> None:
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.scale_cases import ALL_FLOW_METADATA
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    flow_axes = [axis for axis in AXES if axis.domain is Domain.FLOW]
    flow_boundaries = [b for b in BOUNDARIES if b.domain is Domain.FLOW]

    errors = validate_registry(ALL_FLOW_METADATA, flow_axes, flow_boundaries, [], list(POLICIES))
    assert errors == ()
