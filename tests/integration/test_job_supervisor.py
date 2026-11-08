"""B7: JobSupervisor retains every task it starts and shutdown() cancels+awaits all of them,
including asyncio.to_thread work -- to the precise extent asyncio's own cancellation model
allows (see the sub-plan's Design Decision 3: cancelling a Task awaiting to_thread stops
AWAITING it, it cannot forcibly stop the underlying OS thread)."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from scoutmb.runtime.jobs import JobSupervisor


async def test_completed_task_is_retained_then_auto_removed() -> None:
    supervisor = JobSupervisor()

    async def quick() -> str:
        return "done"

    task = supervisor.start("job-1", quick())
    assert supervisor.get("job-1") is task
    result = await task
    assert result == "done"
    # add_done_callback fires on the same loop iteration the awaited task completes in, but
    # callbacks run via call_soon -- yield once so it has actually run before asserting.
    await asyncio.sleep(0)
    assert supervisor.get("job-1") is None


async def test_shutdown_cancels_and_awaits_all_running_tasks() -> None:
    supervisor = JobSupervisor()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def long_running() -> None:
        started.set()
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    supervisor.start("job-1", long_running())
    await started.wait()

    await supervisor.shutdown()

    assert cancelled.is_set()
    assert supervisor.get("job-1") is None
    assert supervisor.pending_count == 0


async def test_shutdown_is_idempotent() -> None:
    supervisor = JobSupervisor()
    await supervisor.shutdown()
    await supervisor.shutdown()  # must not raise


async def test_cancellation_during_a_blocking_adapter_call_leaves_no_pending_task() -> None:
    """Precise claim: after shutdown(), no asyncio.Task is pending. NOT claimed: the underlying
    thread has stopped -- asyncio.Task.cancel() cannot interrupt a thread already running inside
    run_in_executor, so this test uses a short, self-terminating blocking call rather than
    asserting on the thread's own lifetime."""
    supervisor = JobSupervisor()
    thread_finished = threading.Event()

    def blocking_work() -> None:
        time.sleep(0.05)
        thread_finished.set()

    async def wraps_thread() -> None:
        await asyncio.to_thread(blocking_work)

    task = supervisor.start("job-1", wraps_thread())
    await asyncio.sleep(0)  # let the task start and enter asyncio.to_thread

    await supervisor.shutdown()

    assert supervisor.pending_count == 0
    assert task.done()
    # The thread itself is short-lived and self-terminating by design (0.05s sleep) -- this
    # proves the supervisor's bookkeeping is clean, not that cancellation stopped the thread.
    thread_finished.wait(timeout=1.0)
    assert thread_finished.is_set()


async def test_reusing_a_job_id_cancels_the_superseded_task() -> None:
    """A naive `self._tasks[job_id] = task` overwrite, with no cancellation, has a real bug: if
    job A (id="x") is still running when job B (also id="x") starts, A's task reference is
    simply dropped from the registry while STILL RUNNING -- shutdown() can never reach it again
    to cancel or await it, since nothing tracks it anymore. Starting a new task under a reused
    job_id must actively cancel the old one, not merely stop tracking it."""
    supervisor = JobSupervisor()
    first_cancelled = asyncio.Event()

    async def first() -> str:
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            first_cancelled.set()
            raise

    async def second() -> str:
        await asyncio.sleep(0.05)
        return "second"

    first_task = supervisor.start("x", first())
    await asyncio.sleep(0)  # let first_task actually start awaiting sleep(100)

    second_task = supervisor.start("x", second())  # reuses "x" while first_task is still running
    assert supervisor.get("x") is second_task  # the registry now tracks the newer task

    await asyncio.sleep(0)  # let first_task's cancellation actually propagate
    assert first_cancelled.is_set(), (
        "starting a new task under a reused job_id did not cancel the superseded task"
    )
    with pytest.raises(asyncio.CancelledError):
        await first_task

    # first_task's own done-callback fires here -- it must NOT evict second_task's still-live
    # registry entry, since by the time it runs, "x" no longer belongs to first_task at all.
    assert supervisor.get("x") is second_task, (
        "the superseded task's cancellation evicted second's entry"
    )
    await second_task
