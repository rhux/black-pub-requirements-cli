"""Offline enforcement. The fixture-safety tripwire is added in Task 5.

Uses pytest-socket in *host-restriction* mode, NOT full disable_socket: connections to
any host other than loopback raise, while socket creation and loopback bind stay allowed.
That keeps FastAPI TestClient (in-process ASGI) and local fake services working while
still blocking real egress. Full disable_socket would break the loopback-bind test and can
break asyncio loop internals on Windows.
"""

from __future__ import annotations

import pytest_socket


def pytest_runtest_setup(item):
    if item.get_closest_marker("live_service"):
        pytest_socket.enable_socket()  # opt-in tests may reach the real service
        return
    # connect() to anything but loopback raises SocketConnectBlockedError;
    # creation/bind are untouched, so loopback servers and TestClient still work.
    pytest_socket.socket_allow_hosts(["127.0.0.1", "::1"], allow_unix_socket=True)
