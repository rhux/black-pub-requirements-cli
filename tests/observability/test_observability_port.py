from __future__ import annotations

import socket

import pytest

from scoutmb.adapters.observability.noop import NoopObservability
from scoutmb.ports.observability import InvalidObservabilityEvent


def test_noop_observability_never_persists_or_uses_network(tmp_path, monkeypatch):
    def fail_if_socket_opened(*_a, **_k):
        raise AssertionError("NoopObservability must never touch the network")

    monkeypatch.setattr(socket, "socket", fail_if_socket_opened)

    obs = NoopObservability()
    obs.record("scout_processed", count="3")

    assert list(tmp_path.iterdir()) == []  # nothing written anywhere


def test_forbidden_attribute_keys_are_rejected():
    obs = NoopObservability()
    with pytest.raises(InvalidObservabilityEvent):
        obs.record("scout_processed", qr_url="https://scoutingevent.com/mobile/abc123")


def test_forbidden_attribute_values_shaped_like_a_path_are_rejected():
    obs = NoopObservability()
    with pytest.raises(InvalidObservabilityEvent):
        obs.record("file_written", detail="/Users/someone/scouts.csv")


def test_forbidden_attribute_values_shaped_like_a_url_are_rejected():
    obs = NoopObservability()
    with pytest.raises(InvalidObservabilityEvent):
        obs.record("network_call", detail="https://scoutingevent.com/mobile/abc123")


def test_ordinary_event_with_safe_attributes_is_accepted():
    obs = NoopObservability()
    obs.record("scout_processed", count="3", status="complete")  # must not raise
