import socket

import pytest

from scoutmb.network_policy import ExternalNetworkBlocked, assert_egress_allowed


def test_non_loopback_socket_is_blocked():
    with pytest.raises(Exception):
        socket.create_connection(("93.184.216.34", 80), timeout=1)  # example.com IP


def test_loopback_is_allowed():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))  # binding loopback must not be blocked
    s.close()


def test_live_gateway_requires_two_part_opt_in(monkeypatch):
    monkeypatch.delenv("SCOUTMB_ALLOW_LIVE_SERVICE", raising=False)
    with pytest.raises(ExternalNetworkBlocked):
        assert_egress_allowed("scoutingevent.com")


def test_opt_in_allows_the_real_host(monkeypatch):
    monkeypatch.setenv("SCOUTMB_ALLOW_LIVE_SERVICE", "1")
    assert_egress_allowed("scoutingevent.com") is None
