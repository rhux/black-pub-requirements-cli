"""Offline enforcement. The fixture-safety tripwire is added in Task 5.

Uses pytest-socket in *host-restriction* mode, NOT full disable_socket: connections to
any host other than loopback raise, while socket creation and loopback bind stay allowed.
That keeps FastAPI TestClient (in-process ASGI) and local fake services working while
still blocking real egress. Full disable_socket would break the loopback-bind test and can
break asyncio loop internals on Windows.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_socket
from tools.check_private_data import load_corpus_identifiers, scan_corpus, scan_patterns

_REPO_ROOT = Path(__file__).resolve().parents[1]


def pytest_runtest_setup(item):
    if item.get_closest_marker("live_service"):
        pytest_socket.enable_socket()  # opt-in tests may reach the real service
        return
    # connect() to anything but loopback raises SocketConnectBlockedError;
    # creation/bind are untouched, so loopback servers and TestClient still work.
    pytest_socket.socket_allow_hosts(["127.0.0.1", "::1"], allow_unix_socket=True)


@pytest.fixture(scope="session", autouse=True)
def fixtures_are_sanitized() -> None:
    roots = [Path(__file__).parent / "fixtures", Path(__file__).parent / "factories"]
    findings = scan_patterns(roots)
    corpus = _REPO_ROOT / "raw_data"
    if corpus.is_dir():  # local strictness; degrades to pattern-only in CI
        names, ids = load_corpus_identifiers(corpus)
        findings += scan_corpus(roots, names, ids)
    assert not findings, f"private-data findings under tests/: {len(findings)}"
