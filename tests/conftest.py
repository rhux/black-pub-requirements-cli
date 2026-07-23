"""Offline enforcement. The fixture-safety tripwire is added in Task 5.

Uses pytest-socket in *host-restriction* mode, NOT full disable_socket: connections to
any host other than loopback raise, while socket creation and loopback bind stay allowed.
That keeps FastAPI TestClient (in-process ASGI) and local fake services working while
still blocking real egress. Full disable_socket would break the loopback-bind test and can
break asyncio loop internals on Windows.
"""

from __future__ import annotations

import os
import tempfile

# Install a private data sandbox BEFORE importing anything that might reach ui.server, and
# before test modules are collected — some modules read SCOUTMB_DATA_DIR at import time, so a
# fixture (which runs post-import) would be too late. Do NOT set SCOUTMB_DEV.
_TEST_DATA_ROOT = tempfile.TemporaryDirectory(prefix="scoutmb-pytest-")
os.environ["SCOUTMB_DATA_DIR"] = _TEST_DATA_ROOT.name

pytest_plugins = ("tests.plugins.matrix_gate",)

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
import pytest_socket  # noqa: E402
from tools.check_private_data import (  # noqa: E402
    load_corpus_identifiers,
    scan_corpus,
    scan_patterns,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def pytest_unconfigure(config: pytest.Config) -> None:
    _TEST_DATA_ROOT.cleanup()


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
