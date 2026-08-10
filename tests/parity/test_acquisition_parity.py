"""Parity contract (D13): PackageAcquisitionRunner mirrors LegacyAcquisitionRunner's
process/raw contexts (tests/characterization/test_acquisition_matrix.py), driving
scoutmb.features.acquisition.service.AcquisitionService through the SAME strict fakes instead of
scout_schedule_cli.process_scout directly. Both runners are measured against the same
hand-computed AcquisitionCase.expected_legacy; neither is the other's oracle.

form/identity/asset contexts are skipped here -- they characterize scout_schedule_cli's own
module-level functions and AcquisitionService does not re-expose that surface; the process/raw
contexts are where the two implementations actually diverge and where this parity test earns
its keep. RetryPolicy is constructed with a very high breaker_threshold here specifically so
this per-scout test never trips it -- the breaker's cross-scout behavior is Task B5.5's test's
job, not this one's.

Two cases (ACQ-HASREQ-002, ACQ-REQ-004) are classification=INTENTIONAL_CHANGE: their
expected_legacy pins scout_schedule_cli.process_scout's CURRENT (unchanged-by-this-task)
behavior, per acquisition_cases.py's own module docstring -- "they pin the CURRENT legacy
behavior as the observation but record what Slice 2 will do instead." AcquisitionService is
DELIBERATELY built to diverge from expected_legacy for exactly these two cases (skip on
HAS_REQ='0'; reject a schema-drifted row instead of silently coercing it to blanks), so this
test skips the exact-match assertion for them -- the AC's own scope is "every PRESERVE ACQ-*
case's expected_legacy exactly," not every case. The new behavior is proven directly by
test_has_req_zero_skips_the_requirement_fetch and test_schema_drift_row_produces_bounded_error
below instead.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
from pathlib import Path

import pytest

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ScoutInput
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
from tests.fakes.acquisition import StrictScript
from tests.fakes.browser import StrictFakeBrowser
from tests.fakes.clock import FakeClock
from tests.matrix.cases.acquisition_cases import (
    ACQUISITION_CASES,
    AcquisitionCase,
    AcquisitionObservation,
)
from tests.matrix.model import Classification
from tests.matrix.pytest_support import execution_params

# _project/_normalize_raw_names/_UUID_HEX_RE are local copies of
# tests/characterization/test_acquisition_matrix.py's own helpers of the same name --
# deliberately NOT imported from there. That file is a Slice-2a-era characterization runner
# against the legacy flat script, which Slice 2b's retirement plan (sub-plan 4, Task B10.4)
# deletes once scout_schedule_cli.py itself retires; importing test-to-test across that boundary
# would leave this parity test's collection broken the moment that deletion lands, entirely
# independent of anything actually wrong with THIS test. Both copies must stay byte-for-byte
# identical to their source until that deletion, since they exist to prove the SAME projection
# function is being asked the same question of both the legacy and package runners.
_UUID_HEX_RE = re.compile(r"(?<=-)[0-9a-f]{32}(?=[-.])")


def _project(result: object) -> tuple:
    classes = tuple(
        ("class", c.class_number, c.class_p4_id, c.has_requirements, c.class_completed)
        for c in result.classes  # type: ignore[attr-defined]
    )
    reqs = tuple(
        ("req", r.class_p4_id, r.requirement_number, r.completed_requirement)
        for r in result.requirements  # type: ignore[attr-defined]
    )
    errs = tuple(("error", e) for e in result.errors)  # type: ignore[attr-defined]
    return (("attendee_id", result.attendee_id),) + classes + reqs + errs  # type: ignore[attr-defined]


def _normalize_raw_names(root: Path) -> tuple[str, ...]:
    raw_dir = root / "raw"
    if not raw_dir.is_dir():
        return ()
    names = [
        _UUID_HEX_RE.sub("<uuid>", path.relative_to(root).as_posix())
        for path in raw_dir.rglob("*")
        if path.is_file()
    ]
    return tuple(sorted(names))


class _RecordingSleeper:
    """Delegates to FakeClock AND consumes StrictScript's scripted "wait" entries via
    script.next_wait(), exactly like the legacy path's page.wait_for_timeout does. An earlier
    draft only recorded to the clock and never called next_wait() -- every scripted wait entry
    (the retry backoff, the inter-class request_delay_ms wait) went unconsumed, so
    script.assert_consumed() failed on any case exercising either. next_wait() can itself raise
    a scripted error (a case testing a mid-retry failure injected via the wait step), which must
    propagate exactly as the legacy page.wait_for_timeout path already does."""

    def __init__(self, clock: FakeClock, script: StrictScript) -> None:
        self._clock = clock
        self._script = script

    async def sleep(self, seconds: float) -> None:
        milliseconds = round(seconds * 1000)
        self._clock.record(milliseconds)
        response = self._script.next_wait(milliseconds)
        if response.error_type is not None:
            raise response.error_type(response.error_message)

    def monotonic(self) -> float:
        return 0.0


class _ZeroJitter:
    def jitter(self, low: float, high: float) -> float:
        return low


class PackageAcquisitionRunner:
    """Runner[AcquisitionCase, AcquisitionObservation] over
    scoutmb.features.acquisition.service.AcquisitionService, driven through the identical
    StrictFakeBrowser/StrictScript/FakeClock LegacyAcquisitionRunner uses."""

    def __init__(self, context_id: str) -> None:
        self.context_id = context_id

    def run(self, case: AcquisitionCase, *, root: Path) -> AcquisitionObservation:
        if self.context_id not in {"process", "raw"}:
            pytest.skip(f"{self.context_id} exercises legacy-only surface (form/identity/asset)")
        if case.meta.member == "distinct-uuid-filenames":
            return self._run_raw_distinct(case, root)

        clock = FakeClock()
        script = StrictScript(case.script)
        browser = StrictFakeBrowser(script, clock)
        gateway = PlaywrightScoutingEventGateway(
            browser,  # type: ignore[arg-type] - StrictFakeBrowser duck-types Browser
            allow_dead_assets=case.allow_dead_assets,
        )
        retry_policy = RetryPolicy(
            sleeper=_RecordingSleeper(clock, script), jitter=_ZeroJitter(), breaker_threshold=99
        )
        service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())

        result = asyncio.run(
            service.process(
                scout=ScoutInput(name=case.scout_name, url=case.qr_url),
                config=AcquisitionConfig(
                    timeout_seconds=case.timeout_seconds,
                    request_delay_ms=case.request_delay_ms,
                ),
                raw_dir=root / "raw",
                run_identity=RunIdentity(),
            )
        )
        script.assert_consumed()

        if self.context_id == "raw":
            return AcquisitionObservation(
                result=_project(result),
                relative_files=_normalize_raw_names(root),
                closed=browser.contexts[0].closed,
            )
        return AcquisitionObservation(
            result=_project(result),
            calls=tuple(script.calls),
            waits_ms=clock.waits_ms,
            closed=browser.contexts[0].closed,
        )

    def _run_raw_distinct(self, case: AcquisitionCase, root: Path) -> AcquisitionObservation:
        """Mirror of LegacyAcquisitionRunner._ctx_raw_distinct (test_acquisition_matrix.py):
        two attendees sharing the same printed name must still get two distinct raw filenames,
        because the UUID segment is keyed on attendee_id, not name. Each half of case.script is
        a full schedule-only exchange for one attendee -- run through AcquisitionService.process
        as two SEPARATE calls sharing one RunIdentity, exactly like the legacy dispatch does."""
        run_identity = RunIdentity()
        raw_dir = root / "raw"
        for expected, response in case.script:
            script = StrictScript(((expected, response),))
            clock = FakeClock()
            browser = StrictFakeBrowser(script, clock)
            gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
            retry_policy = RetryPolicy(
                sleeper=_RecordingSleeper(clock, script), jitter=_ZeroJitter(), breaker_threshold=99
            )
            service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
            asyncio.run(
                service.process(
                    scout=ScoutInput(name=case.scout_name, url=case.qr_url),
                    config=AcquisitionConfig(timeout_seconds=case.timeout_seconds, request_delay_ms=0),
                    raw_dir=raw_dir,
                    run_identity=run_identity,
                )
            )
            script.assert_consumed()
        files = sorted(p.name for p in raw_dir.glob("*-schedule.json"))
        assert len(files) == 2, files
        assert files[0] != files[1]
        for name in files:
            assert re.match(r"^avery-example-[0-9a-f]{32}-schedule\.json$", name), name
        return AcquisitionObservation(result=(("distinct", True),))


@pytest.mark.parametrize(("case", "context_id"), execution_params(ACQUISITION_CASES))
def test_package_runner_matches_expected_legacy(
    case: AcquisitionCase, context_id: str, tmp_path: Path
) -> None:
    if context_id not in {"process", "raw"}:
        pytest.skip(f"{context_id} has no package-side equivalent yet")
    if case.meta.classification is Classification.INTENTIONAL_CHANGE:
        pytest.skip(
            f"{case.meta.case_id} is intentional-change: AcquisitionService is built to diverge "
            "from expected_legacy here by design (see module docstring)"
        )

    runner = PackageAcquisitionRunner(context_id)
    observed = runner.run(case, root=tmp_path)

    expected = case.expected_legacy
    assert expected is not None
    if context_id == "process":
        expected = dataclasses.replace(expected, calls=tuple(req for req, _ in case.script))
    assert observed == expected


async def test_has_req_zero_skips_the_requirement_fetch(tmp_path: Path) -> None:
    """ACQ-HASREQ-002's landed behavior: AcquisitionService skips the requirement fetch
    entirely when HAS_REQ='0', rather than issuing it and relying on the response being empty
    (the legacy behavior that ACQ-HASREQ-002 still pins for scout_schedule_cli.process_scout).
    No requirement request is scripted below -- if AcquisitionService issued one anyway, the
    strict fake would raise for an unscripted call."""
    from tests.matrix.cases.acquisition_cases import ATTENDEE_A, CLASS_A, NAME_A, URL_A, _class_row

    def _schedule_payload(rows: tuple[dict, ...]) -> dict:
        return {"status": {"status": 1}, "data": list(rows)}

    from tests.matrix.cases.acquisition_cases import ExpectedRequest, ScriptedResponse

    script = StrictScript(
        (
            (
                ExpectedRequest("schedule", ATTENDEE_A),
                ScriptedResponse(value=_schedule_payload((_class_row(CLASS_A, has_req="0"),))),
            ),
        )
    )
    clock = FakeClock()
    browser = StrictFakeBrowser(script, clock)
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(clock, script), jitter=_ZeroJitter(), breaker_threshold=99)
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())

    result = await service.process(
        scout=ScoutInput(name=NAME_A, url=URL_A),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
        run_identity=RunIdentity(),
    )
    script.assert_consumed()  # no requirement request was ever scripted or issued
    assert result.classes[0].has_requirements is False
    assert result.requirements == ()
    assert result.errors == ()


async def test_schema_drift_row_produces_bounded_error_not_a_blank_record(tmp_path: Path) -> None:
    """ACQ-REQ-004's landed behavior: a requirement row missing its identity fields produces one
    bounded error string in ScoutResult.errors -- not a crash, and not a silently-coerced blank
    RequirementRecord (the legacy behavior that ACQ-REQ-004 still pins for process_scout)."""
    from tests.matrix.cases.acquisition_cases import ATTENDEE_A, CLASS_A, NAME_A, URL_A, _class_row

    def _schedule_payload(rows: tuple[dict, ...]) -> dict:
        return {"status": {"status": 1}, "data": list(rows)}

    from tests.matrix.cases.acquisition_cases import ExpectedRequest, ScriptedResponse

    script = StrictScript(
        (
            (
                ExpectedRequest("schedule", ATTENDEE_A),
                ScriptedResponse(value=_schedule_payload((_class_row(CLASS_A),))),
            ),
            (
                ExpectedRequest("requirement", ATTENDEE_A, CLASS_A),
                ScriptedResponse(
                    value={"status": {"status": 1}, "data": [{"MERIT_BADGE_NAME": "Chess"}]}
                ),
            ),
        )
    )
    clock = FakeClock()
    browser = StrictFakeBrowser(script, clock)
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(clock, script), jitter=_ZeroJitter(), breaker_threshold=99)
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())

    result = await service.process(
        scout=ScoutInput(name=NAME_A, url=URL_A),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
        run_identity=RunIdentity(),
    )
    script.assert_consumed()
    assert result.requirements == ()  # no blank-coerced record was built
    assert len(result.errors) == 1
    assert "requirement_id" in result.errors[0] and "requirement_number" in result.errors[0]
