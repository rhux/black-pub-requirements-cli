"""Lifespan-owned job supervisor (D33). Retains a reference to every asyncio.Task it starts --
the bug this fixes is ui/server.py's bare `asyncio.create_task(worker())` with no retained
reference, which the event loop is free to garbage-collect mid-flight once the enclosing route
handler returns, silently abandoning in-flight work. shutdown() cancels and awaits every tracked
task so nothing outlives the app's lifespan.

Limitation, stated rather than glossed over: cancelling a Task awaiting asyncio.to_thread(...)
delivers CancelledError at the next await point in the ASYNC side; it cannot interrupt the
underlying OS thread already running inside the executor. "No pending task after shutdown" is
what this class guarantees -- "no thread still running" is not achievable through this
mechanism and is not claimed.

Duplicate job IDs are handled safely at BOTH ends of a task's life, which takes two separate
fixes:

1. `start()`: if `job_id` already names a still-running task, that task is CANCELLED before the
   new one takes its place in the registry. An earlier draft only overwrote
   `self._tasks[job_id]`, which silently dropped the older task's reference while it kept
   running -- shutdown() could then never reach it again to cancel or await it, since nothing
   tracked it anymore.
2. The done-callback (`_discard_if_current`) only removes ITS OWN task from the registry if
   that task is still the current occupant of that key, never unconditionally. Without that
   check, the OLDER task's (now-cancelled) completion could evict the NEWER task's still-live
   registry entry, since both callbacks close over the same `job_id` string."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class JobSupervisor:
    _tasks: dict[str, asyncio.Task[Any]] = field(default_factory=dict)

    def start(self, job_id: str, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        existing = self._tasks.get(job_id)
        if existing is not None and not existing.done():
            # Cancel, don't just overwrite -- an overwrite alone would drop the only reference
            # to a still-running task, leaving it untracked and un-cancellable by shutdown().
            existing.cancel()
        task = asyncio.create_task(coro)
        self._tasks[job_id] = task
        task.add_done_callback(functools.partial(self._discard_if_current, job_id))
        return task

    def _discard_if_current(self, job_id: str, finished_task: asyncio.Task[Any]) -> None:
        """Only remove job_id's registry entry if `finished_task` IS the task currently stored
        there -- a done-callback belonging to a SUPERSEDED task (job_id was reused before this
        one finished) must not evict whatever newer task now occupies that key."""
        if self._tasks.get(job_id) is finished_task:
            del self._tasks[job_id]

    def get(self, job_id: str) -> asyncio.Task[Any] | None:
        return self._tasks.get(job_id)

    @property
    def pending_count(self) -> int:
        return sum(1 for task in self._tasks.values() if not task.done())

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
