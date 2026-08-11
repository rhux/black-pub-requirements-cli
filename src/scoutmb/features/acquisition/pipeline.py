"""The full CLI batch pipeline orchestration (D22, D33): drive every scout through run_batch's
shared breaker/checkpoint/RunIdentity, publish the report, all bracketed by one RunStateMachine.
The single home for this ORCHESTRATION LOGIC -- both scout_schedule_cli.async_main (a Form-2
shim) and interfaces/cli/schedule.py's run() call run_schedule_pipeline directly, so neither
depends on the other existing.

Pure dependency injection: every adapter this CLI path touches -- the launched Playwright
browser, the ScoutingEventGateway, the CheckpointStore, the AtomicFileSink each collaborator
wraps, the ReportingService -- is constructed by the CALLER and handed in already-built. An
earlier draft imported four adapters directly from this features/ module (AtomicFileSink,
AtomicFileCheckpointStore, TabularAttendeeSource, PlaywrightScoutingEventGateway) plus imported
UPWARD from scoutmb.interfaces.cli.composition -- both violate the dependency-edge table
(`features -> features, core, ports, config, errors`; never `adapters`, never `interfaces`).
interfaces/cli/composition.py now owns all of that construction; interfaces/cli/schedule.py's
run() calls those builders and passes the results in here.

The RetryPolicy's breaker_threshold (how many consecutive scout failures open the breaker) is
NOT defined here as a module constant -- it is a field on ScheduleConfig
(config.breaker_threshold, default 5, overridable via --breaker-threshold), read by whichever
caller constructs the shared RetryPolicy. This module never constructs a RetryPolicy itself, so
it has no reason to know the threshold's value at all."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any

from scoutmb.config import ScheduleConfig
from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ScoutInput, ScoutResult
from scoutmb.core.run_state import RunEvent, RunStateMachine
from scoutmb.features.acquisition.batch import run_batch
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
from scoutmb.features.reporting.service import ReportingService
from scoutmb.ports.checkpoint_store import CheckpointStore


async def run_schedule_pipeline(
    config: ScheduleConfig,
    *,
    scouts: Sequence[ScoutInput],
    service: AcquisitionService,
    retry_policy: RetryPolicy,
    checkpoint_store: CheckpointStore,
    reporting_service: ReportingService,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_event: asyncio.Event | None = None,
    run_state: RunStateMachine | None = None,
) -> int:
    """`retry_policy` MUST be the same instance embedded in `service` -- the caller (composition
    + interfaces/cli/schedule.run()) constructs ONE RetryPolicy and passes it to both, so the
    breaker's cross-scout failure count and the per-request backoff share one set of state. This
    module has no way to enforce that itself (it would require reaching into `service`'s
    internals); it is the caller's contract to uphold, exactly like `run_batch` already
    documents for its own `service`/`retry_policy` pair."""
    run_state = run_state if run_state is not None else RunStateMachine()
    run_state.apply(RunEvent.START)

    try:
        config.output.mkdir(parents=True, exist_ok=True)
        raw_dir = config.output / "raw"

        print(f"Loaded {len(scouts)} attendee QR link(s).")
        if progress_callback is not None:
            await progress_callback({"type": "batch_start", "total": len(scouts)})

        run_identity = RunIdentity()
        results: list[ScoutResult] = await run_batch(
            scouts,
            service=service,
            retry_policy=retry_policy,
            checkpoint_store=checkpoint_store,
            run_identity=run_identity,
            config=AcquisitionConfig(
                timeout_seconds=config.timeout, request_delay_ms=config.request_delay_ms
            ),
            raw_dir=raw_dir,
            scout_delay_ms=config.scout_delay_ms,
            progress_callback=progress_callback,
            resume_event=resume_event,
            run_state=run_state,
        )

        reporting_service.publish(
            config.output,
            results,
            generated_at_local=time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            generated_at_iso=datetime.now().astimezone().isoformat(timespec="seconds"),
            run_identity=run_identity,
            generate_html=not config.no_html,
            html_name=config.html_name,
            generate_email_report=config.email_report,
        )
        # Only recorded AFTER the report has actually been generated -- an earlier draft applied
        # COMPLETE right after the acquisition loop, so a reporting failure following a clean
        # acquisition would leave the state machine claiming a run that never actually finished.
        run_state.apply(RunEvent.COMPLETE)
    except asyncio.CancelledError:
        # What a real KeyboardInterrupt becomes inside this coroutine once asyncio.run cancels
        # it -- distinguished from an ordinary failure, never mapped to FAIL.
        run_state.apply(RunEvent.CANCEL)
        run_state.apply(RunEvent.CANCELLED)
        raise
    except Exception:
        run_state.apply(RunEvent.FAIL)
        raise

    print(f"Results written to: {config.output.resolve()}")
    return 1 if any(result.errors for result in results) else 0
