"""Typed matrix execution of the acquisition characterization catalog (Task 19).

Each executable ``ACQ-*`` case declares one execution context; ``execution_params`` expands
them. The ``process``/``raw``/``asset`` contexts drive the REAL ``scout_schedule_cli.process_scout``
(never mocked) through the strict fake Browser/Context/Page in ``tests/fakes/browser.py`` and the
``FakeClock`` in ``tests/fakes/clock.py`` -- nothing here patches ``process_scout``,
``post_requirement``, the dedup logic, or record construction. The ``form``/``identity`` contexts
call ``form_values`` / ``is_schedule_response`` / ``RunIdentity.output_id`` directly with no
browser at all. ``NET-POLICY-*`` cases exercise the real, EXISTING
``scoutmb.network_policy.assert_egress_allowed`` boundary.

No test writes outside ``tmp_path`` and no test performs real network I/O: the strict fakes never
open a socket, and the offline pytest-socket policy in ``tests/conftest.py`` would block one
regardless.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import re
from pathlib import Path

import pytest
from tests.fakes.acquisition import FormResponseStub, StrictScript
from tests.fakes.browser import StrictFakeBrowser, StrictFakeRoute
from tests.fakes.clock import FakeClock
from tests.matrix.cases.acquisition_cases import (
    ACQUISITION_CASES,
    ATTENDEE_A,
    AcquisitionCase,
    AcquisitionObservation,
)
from tests.matrix.pytest_support import execution_params

_UUID_HEX_RE = re.compile(r"(?<=-)[0-9a-f]{32}(?=[-.])")
_UUIDV4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _args(**overrides: object) -> argparse.Namespace:
    return argparse.Namespace(
        **{
            "timeout": 5,
            "request_delay_ms": 0,
            "allow_dead_assets": False,
            "headed": False,
            "channel": None,
            **overrides,
        }
    )


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


class LegacyAcquisitionRunner:
    """Runner[AcquisitionCase, AcquisitionObservation] over the real acquisition pipeline."""

    def __init__(self, context_id: str) -> None:
        self.context_id = context_id

    def run(self, case: AcquisitionCase, *, root: Path) -> AcquisitionObservation:
        handler = getattr(self, f"_ctx_{self.context_id.replace('-', '_')}")
        return handler(case, root)

    # -- direct function-level contexts (no browser) ----------------------------------------

    def _ctx_form(self, case: AcquisitionCase, root: Path) -> AcquisitionObservation:
        import scout_schedule_cli as legacy

        _, response = case.script[0]
        post_data = response.value
        values = legacy.form_values(post_data)
        fake_response = FormResponseStub(case.qr_url, post_data)
        is_schedule = legacy.is_schedule_response(fake_response)
        return AcquisitionObservation(
            result=(
                ("form", tuple(sorted(values.items()))),
                ("is_schedule_response", is_schedule),
            )
        )

    def _ctx_identity(self, case: AcquisitionCase, root: Path) -> AcquisitionObservation:
        import scout_schedule_cli as legacy

        if case.meta.member == "uuidv4-stable":
            run_identity = legacy.RunIdentity()
            attendee = legacy.AttendeeId.parse(ATTENDEE_A)
            first = run_identity.output_id(attendee)
            second = run_identity.output_id(attendee)
            return AcquisitionObservation(
                result=(("stable", first == second), ("uuidv4", bool(_UUIDV4_RE.match(first))))
            )
        if case.meta.member == "runs-unlinkable":
            attendee = legacy.AttendeeId.parse(ATTENDEE_A)
            first = legacy.RunIdentity().output_id(attendee)
            second = legacy.RunIdentity().output_id(attendee)
            return AcquisitionObservation(result=(("unlinkable", first != second),))
        raise AssertionError(f"unknown identity member: {case.meta.member}")

    # -- browser-driven contexts -------------------------------------------------------------

    async def _run_process(self, case: AcquisitionCase, root: Path):
        import scout_schedule_cli as legacy

        script = StrictScript(case.script)
        clock = FakeClock()
        browser = StrictFakeBrowser(script, clock)
        raw_dir = root / "raw"
        run_identity = legacy.RunIdentity()
        scout = legacy.ScoutInput(name=case.scout_name, url=case.qr_url)
        args = _args(
            request_delay_ms=case.request_delay_ms,
            allow_dead_assets=case.allow_dead_assets,
            timeout=case.timeout_seconds,
        )
        result = await legacy.process_scout(browser, scout, args, raw_dir, run_identity)
        return result, browser.contexts[0], script, clock

    def _ctx_process(self, case: AcquisitionCase, root: Path) -> AcquisitionObservation:
        result, context, script, clock = asyncio.run(self._run_process(case, root))
        script.assert_consumed()
        return AcquisitionObservation(
            result=_project(result),
            calls=tuple(script.calls),
            waits_ms=clock.waits_ms,
            closed=context.closed,
        )

    def _ctx_raw(self, case: AcquisitionCase, root: Path) -> AcquisitionObservation:
        if case.meta.member == "distinct-uuid-filenames":
            return self._ctx_raw_distinct(case, root)
        result, context, script, clock = asyncio.run(self._run_process(case, root))
        script.assert_consumed()
        return AcquisitionObservation(
            result=_project(result),
            relative_files=_normalize_raw_names(root),
            closed=context.closed,
        )

    def _ctx_raw_distinct(self, case: AcquisitionCase, root: Path) -> AcquisitionObservation:
        import scout_schedule_cli as legacy

        run_identity = legacy.RunIdentity()
        raw_dir = root / "raw"
        for expected, response in case.script:
            script = StrictScript(((expected, response),))
            clock = FakeClock()
            browser = StrictFakeBrowser(script, clock)
            scout = legacy.ScoutInput(name=case.scout_name, url=case.qr_url)
            asyncio.run(
                legacy.process_scout(browser, scout, _args(), raw_dir, run_identity)
            )
            script.assert_consumed()
        files = sorted(p.name for p in raw_dir.glob("*-schedule.json"))
        assert len(files) == 2, files
        assert files[0] != files[1]
        for name in files:
            assert re.match(r"^avery-example-[0-9a-f]{32}-schedule\.json$", name), name
        return AcquisitionObservation(result=(("distinct", True),))

    def _ctx_asset(self, case: AcquisitionCase, root: Path) -> AcquisitionObservation:
        result, context, script, clock = asyncio.run(self._run_process(case, root))
        script.assert_consumed()
        registered = context.route_handler is not None
        dead_aborted: bool | None = None
        normal_continued: bool | None = None
        if registered:
            dead_route = StrictFakeRoute("https://mike.dev.admin.247scouting.com/x.js")
            normal_route = StrictFakeRoute("https://scoutingevent.com/mobile/asset.js")
            asyncio.run(context.route_handler(dead_route))  # type: ignore[misc]
            asyncio.run(context.route_handler(normal_route))  # type: ignore[misc]
            dead_aborted = dead_route.aborted
            normal_continued = normal_route.continued
        return AcquisitionObservation(
            result=(
                ("route_registered", registered),
                ("dead_aborted", dead_aborted),
                ("normal_continued", normal_continued),
            )
        )


def _observe(case: AcquisitionCase, context_id: str, root: Path) -> AcquisitionObservation:
    return LegacyAcquisitionRunner(context_id).run(case, root=root)


@pytest.mark.parametrize(("case", "context_id"), execution_params(ACQUISITION_CASES))
def test_acquisition_case(case: AcquisitionCase, context_id: str, tmp_path: Path) -> None:
    observed = _observe(case, context_id, tmp_path)
    expected = case.expected_legacy
    assert expected is not None
    if context_id == "process":
        # The ordered-call assertion is the full scripted sequence itself: a full script
        # consumption (already enforced by assert_consumed() inside the runner) IS the ordered
        # request list. Deriving it here keeps the catalog free of hand-duplicated call lists
        # that would drift out of sync with the script.
        expected = dataclasses.replace(
            expected, calls=tuple(req for req, _ in case.script)
        )
    assert observed == expected


# --------------------------------------------------------------------------------------------
# NET-POLICY: the EXISTING scoutmb.network_policy.assert_egress_allowed boundary (Slice 1a).
# --------------------------------------------------------------------------------------------
@pytest.mark.matrix_case(case_id="NET-POLICY-001", context_id="net-policy", lane="default")
def test_net_policy_loopback_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    from scoutmb.network_policy import assert_egress_allowed

    monkeypatch.delenv("SCOUTMB_ALLOW_LIVE_SERVICE", raising=False)
    for host in ("127.0.0.1", "::1", "localhost"):
        assert assert_egress_allowed(host) is None


@pytest.mark.matrix_case(case_id="NET-POLICY-002", context_id="net-policy", lane="default")
def test_net_policy_non_loopback_denied_without_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    from scoutmb.errors import ExternalNetworkBlocked
    from scoutmb.network_policy import assert_egress_allowed

    monkeypatch.delenv("SCOUTMB_ALLOW_LIVE_SERVICE", raising=False)
    with pytest.raises(ExternalNetworkBlocked):
        assert_egress_allowed("scoutingevent.com")


@pytest.mark.matrix_case(case_id="NET-POLICY-003", context_id="net-policy", lane="default")
def test_net_policy_opt_in_allows_service_host(monkeypatch: pytest.MonkeyPatch) -> None:
    from scoutmb.network_policy import assert_egress_allowed

    monkeypatch.setenv("SCOUTMB_ALLOW_LIVE_SERVICE", "1")
    assert assert_egress_allowed("scoutingevent.com") is None
    # The environment opt-in is only HALF of the real live-service contract: pytest-socket
    # (tests/conftest.py pytest_runtest_setup) additionally requires the 'live_service' marker
    # before it will let a real connection through even with this variable set. This test does
    # not carry that marker and performs no real connection -- it only proves the *policy*
    # function's half of the two-part gate.


# --------------------------------------------------------------------------------------------
# Registry self-check, mirroring tests/characterization/test_pdf_matrix.py.
# --------------------------------------------------------------------------------------------
def test_acquisition_registry_is_structurally_valid() -> None:
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.acquisition_cases import ALL_ACQUISITION_METADATA
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    acq_axes = [axis for axis in AXES if axis.domain is Domain.ACQUISITION]
    acq_boundaries = [b for b in BOUNDARIES if b.domain is Domain.ACQUISITION]

    errors = validate_registry(
        ALL_ACQUISITION_METADATA, acq_axes, acq_boundaries, [], list(POLICIES)
    )
    assert errors == ()
