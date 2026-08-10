"""Acquisition/interface characterization tests drive strict FAKES against synthetic
scoutingevent.com URLs -- never a real socket (tests/conftest.py's pytest-socket
host-restriction mode still blocks any actual non-loopback connection regardless). Once the
gateway wires assert_egress_allowed into the schedule/requirement fetch path, these fake-driven
tests need the policy opt-in or every one of them raises ExternalNetworkBlocked immediately."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _allow_synthetic_scoutingevent_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOUTMB_ALLOW_LIVE_SERVICE", "1")
