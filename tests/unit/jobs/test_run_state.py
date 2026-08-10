"""B7: the run-state transition table is TOTAL -- every (state, event) pair either transitions
or fails closed via IllegalTransition, with no pair falling through to anything else (a silent
no-op, an unrelated exception, or a state left in an inconsistent partial-write)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scoutmb.core.run_state import IllegalTransition, RunEvent, RunState, RunStateMachine

_TERMINAL = {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED}


def test_start_transitions_idle_to_running() -> None:
    machine = RunStateMachine()
    assert machine.state is RunState.IDLE
    assert machine.apply(RunEvent.START) is RunState.RUNNING
    assert machine.state is RunState.RUNNING


def test_pause_then_resume_round_trips() -> None:
    machine = RunStateMachine()
    machine.apply(RunEvent.START)
    assert machine.apply(RunEvent.PAUSE) is RunState.PAUSED
    assert machine.apply(RunEvent.RESUME) is RunState.RUNNING


def test_illegal_edge_raises_and_state_is_unchanged() -> None:
    machine = RunStateMachine()
    with pytest.raises(IllegalTransition) as exc_info:
        machine.apply(RunEvent.PAUSE)  # PAUSE is illegal from IDLE
    assert exc_info.value.state is RunState.IDLE
    assert exc_info.value.event is RunEvent.PAUSE
    assert machine.state is RunState.IDLE  # unchanged after the failed attempt


@pytest.mark.parametrize("terminal", sorted(_TERMINAL, key=lambda s: s.value))
def test_terminal_states_accept_no_further_event(terminal: RunState) -> None:
    machine = RunStateMachine(state=terminal)
    for event in RunEvent:
        with pytest.raises(IllegalTransition):
            machine.apply(event)
        assert machine.state is terminal  # every attempt fails closed, none mutate .state


@given(state=st.sampled_from(RunState), event=st.sampled_from(RunEvent))
def test_every_state_event_pair_transitions_or_fails_closed(
    state: RunState, event: RunEvent
) -> None:
    """Totality: NOTHING falls through. Either apply() returns a RunState (a legal edge) or it
    raises IllegalTransition -- there is no third outcome."""
    machine = RunStateMachine(state=state)
    try:
        result = machine.apply(event)
    except IllegalTransition as exc:
        assert exc.state is state
        assert exc.event is event
    else:
        assert isinstance(result, RunState)
        assert machine.state is result


# The Hypothesis property above proves TOTALITY (every pair transitions or raises -- no third
# outcome) but does NOT pin which SPECIFIC edges are legal: an implementation with a completely
# different (but still total) transition table would pass it too. This exhaustive parametrized
# test is the complement -- it enumerates every (state, event) pair against an INDEPENDENTLY
# spelled-out expected table and asserts each pair transitions to its declared next-state (or
# raises, if absent).
#
# _EXPECTED_TRANSITIONS is deliberately NOT imported from run_state.py's _TRANSITIONS -- an
# earlier draft of this test did import it directly, which made the test tautological: comparing
# a dict against itself always passes, so a WRONG _TRANSITIONS table (a missing edge, a typo'd
# target state) would pass this test too, since the test would just be re-stating whatever the
# implementation happens to say. Retyping the table here as a literal is what actually pins the
# intended shape -- this test fails if run_state.py's table drifts from the spec below, which is
# the whole point of an "exact table" test.
_ALL_PAIRS = [(state, event) for state in RunState for event in RunEvent]

_EXPECTED_TRANSITIONS: dict[tuple[RunState, RunEvent], RunState] = {
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


@pytest.mark.parametrize(("state", "event"), _ALL_PAIRS)
def test_transition_table_matches_exactly(state: RunState, event: RunEvent) -> None:
    machine = RunStateMachine(state=state)
    expected_next = _EXPECTED_TRANSITIONS.get((state, event))

    if expected_next is None:
        with pytest.raises(IllegalTransition):
            machine.apply(event)
        assert machine.state is state
    else:
        assert machine.apply(event) == expected_next
        assert machine.state == expected_next
