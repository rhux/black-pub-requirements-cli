"""Run-scoped acquisition composition (D22, ACQ-BREAKER, ACQ-RESUME). Owns the ONE RetryPolicy
shared across every scout in the run (so its breaker sees cross-scout failures, matching
ACQ-BREAKER's own rationale), the checkpoint store (skip completed scouts, persist output-UUIDs
and completed scouts' results, so a resumed run's report stays complete), and RunIdentity
hydration. AcquisitionService.process() handles one scout in isolation and knows nothing about
any of this -- see that module's docstring for why.

A scout is marked completed (added to completed_urls/completed_results) ONLY when its
ScoutResult.errors is empty -- an earlier draft marked every attempted scout completed
unconditionally, which meant a scout that failed once was silently skipped on every future
resume instead of being retried. output_ids IS still saved after every scout regardless of
success, since a scout's output_id, once minted via RunIdentity, must stay stable across
retries.

The checkpoint file is created (empty) at the very start of a fresh run, before any scout is
processed -- ACQ-RESUME-001 promises a checkpoint file exists from the start of a run, not only
after the first scout happens to finish."""

from __future__ import annotations

import random
from collections.abc import Sequence
from pathlib import Path

from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ScoutInput, ScoutResult
from scoutmb.core.output_schemas import scout_result_from_row, scout_result_to_row
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
from scoutmb.ports.checkpoint_store import CHECKPOINT_VERSION, Checkpoint, CheckpointStore


async def run_batch(
    scouts: Sequence[ScoutInput],
    *,
    service: AcquisitionService,
    retry_policy: RetryPolicy,
    checkpoint_store: CheckpointStore,
    run_identity: RunIdentity,
    config: AcquisitionConfig,
    raw_dir: Path,
    scout_delay_ms: int | None = None,
) -> list[ScoutResult]:
    checkpoint = checkpoint_store.load()
    if checkpoint is None:
        # Create the checkpoint file NOW, before any scout is processed -- ACQ-RESUME-001's
        # "a fresh run creates a checkpoint file at the start of a run" behavior, not only once
        # the first scout happens to finish.
        checkpoint = Checkpoint(version=CHECKPOINT_VERSION, completed_urls=(), output_ids={})
        checkpoint_store.save(checkpoint)
    else:
        run_identity.hydrate(checkpoint.output_ids)

    completed_urls = set(checkpoint.completed_urls)
    completed_results = dict(checkpoint.completed_results)

    # Scouts finished on a prior process are reconstructed from the checkpoint, not re-fetched
    # -- a resumed run's report must include them alongside whatever this run newly processes.
    results: list[ScoutResult] = [
        scout_result_from_row(row) for row in completed_results.values()
    ]

    total = len(scouts)
    for index, scout in enumerate(scouts, start=1):
        # Requires BOTH: a checkpoint written by this exact code always adds a URL to
        # completed_urls and completed_results in the same atomic step (below), so for a
        # same-version checkpoint the two are always in lockstep and this extra check changes
        # nothing. It only matters for a checkpoint saved before completed_results existed
        # (backward-compat load, Task B5.3) -- completed_urls has the entry but completed_results
        # is {}, so scout_result_from_row has nothing to reconstruct. Skipping on completed_urls
        # ALONE in that case would silently drop the scout from this run's results entirely --
        # the exact bug completed_results was added to fix, just triggered by an old-format file
        # instead of a same-format one. Re-processing it once here is the safe fallback: no
        # scout is ever silently lost, at the cost of one extra fetch for that edge case only.
        if scout.url in completed_urls and scout.url in completed_results:
            continue

        label = scout.name or scout.url
        print(f"[{index}/{total}] {label}")

        retry_policy.check_closed()  # raises BreakerOpen before opening a session for this scout
        result = await service.process(
            scout=scout, config=config, raw_dir=raw_dir, run_identity=run_identity
        )
        results.append(result)
        print(
            f"    attendeeID={result.attendee_id or 'unknown'}, "
            f"classes={len(result.classes)}, requirements={len(result.requirements)}, "
            f"errors={len(result.errors)}"
        )

        if result.errors:
            retry_policy.record_failure()
        else:
            retry_policy.record_success()
            completed_urls.add(scout.url)
            completed_results[scout.url] = scout_result_to_row(result)

        checkpoint_store.save(
            Checkpoint(
                version=CHECKPOINT_VERSION,
                completed_urls=tuple(completed_urls),
                output_ids=run_identity.snapshot(),
                completed_results=completed_results,
            )
        )

        # Only sleep if a not-yet-completed scout remains after this one -- never a pointless
        # delay before a tail of already-checkpointed scouts that will just be skipped.
        if any(remaining.url not in completed_urls for remaining in scouts[index:]):
            delay_seconds = (
                random.uniform(0.5, 2.0) if scout_delay_ms is None else scout_delay_ms / 1000
            )
            if delay_seconds > 0:
                await retry_policy.sleeper.sleep(delay_seconds)

    return results
