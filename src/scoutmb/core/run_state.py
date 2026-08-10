"""A versioned, total run-state machine (D33). Models ONE run's lifecycle from IDLE to a
terminal state; a new run gets a new RunStateMachine instance rather than reusing a terminal one.
Every (state, event) pair not explicitly listed in _TRANSITIONS raises IllegalTransition -- proven
total by tests/unit/jobs/test_run_state.py's Hypothesis property, not merely asserted here."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from scoutmb.errors import ScoutmbError

RUN_STATE_VERSION = 1


class RunState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunEvent(StrEnum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    CANCELLED = "cancelled"
    COMPLETE = "complete"
    FAIL = "fail"


class IllegalTransition(ScoutmbError):
    """The event is not legal from the current state. Fails closed: the state machine's
    .state is never mutated by a rejected attempt."""

    def __init__(self, state: RunState, event: RunEvent) -> None:
        self.state = state
        self.event = event
        super().__init__(f"cannot apply {event.value!r} while in state {state.value!r}")


_TRANSITIONS: dict[tuple[RunState, RunEvent], RunState] = {
    (RunState.IDLE, RunEvent.START): RunState.RUNNING,
    (RunState.RUNNING, RunEvent.PAUSE): RunState.PAUSED,
    (RunState.PAUSED, RunEvent.RESUME): RunState.RUNNING,
    (RunState.RUNNING, RunEvent.CANCEL): RunState.CANCELLING,
    (RunState.PAUSED, RunEvent.CANCEL): RunState.CANCELLING,
    (RunState.CANCELLING, RunEvent.CANCELLED): RunState.CANCELLED,
    (RunState.RUNNING, RunEvent.COMPLETE): RunState.COMPLETED,
    (RunState.RUNNING, RunEvent.FAIL): RunState.FAILED,
    (RunState.PAUSED, RunEvent.FAIL): RunState.FAILED,
    (RunState.CANCELLING, RunEvent.FAIL): RunState.FAILED,
}


@dataclass(slots=True)
class RunStateMachine:
    state: RunState = RunState.IDLE
    version: int = RUN_STATE_VERSION

    def apply(self, event: RunEvent) -> RunState:
        key = (self.state, event)
        next_state = _TRANSITIONS.get(key)
        if next_state is None:
            raise IllegalTransition(self.state, event)
        self.state = next_state
        return next_state
