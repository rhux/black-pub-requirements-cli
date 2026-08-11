"""Typed matrix execution of the desktop-launcher characterization catalog (Task 21, final
slice): ``run_app.py``'s port-bind seam, ``wait_until_ready``, and ``main`` dispatch.

``DESK-PORT-*`` drive a REAL loopback socket bind -- fast, safe, and exactly what the port-zero
rendezvous contract is about. As of B9.1, DESK-PORT-001 exercises
``scoutmb.interfaces.web.rendezvous.bind_loopback_socket`` (the race-free replacement for
``run_app.py``'s old, now-removed ``free_port``) rather than ``run_app`` directly -- see
``tests/matrix/cases/desktop_cases.py``'s DESK-PORT-001 for why this is an intentional-change
row, not a preserved one. Every other case here injects at ``run_app``'s real current seams (the
plain module-level ``time.monotonic``/``time.sleep``/``urllib.request.urlopen`` names it binds
via its own ``import time`` / ``import urllib.request`` statements, plus
``webbrowser.open``/``webview.create_window``/``webview.start`` for the two deferred imports
inside ``main()``, and ``start_server_on_free_port`` for the merged port-bind-and-serve seam)
via ``pytest.MonkeyPatch`` -- never a real sleep, never a real HTTP request, never a real
browser tab or native window.
"""

from __future__ import annotations

import socket
import sys
import urllib.error

import pytest
from tests.matrix.cases.desktop_cases import (
    DESKTOP_MODE_CASES,
    DESKTOP_PORT_CASES,
    DESKTOP_READY_CASES,
    DesktopModeCase,
    DesktopPortCase,
    DesktopReadyCase,
)
from tests.matrix.pytest_support import assert_platform_domain_registry_valid, execution_params


# ==================================================================================================
# DESK-PORT -- real loopback socket bind/close.
# ==================================================================================================
@pytest.mark.parametrize(("case", "context_id"), execution_params(DESKTOP_PORT_CASES))
def test_desktop_port_execution(case: DesktopPortCase, context_id: str) -> None:
    del context_id
    if case.scenario == "free-port":
        from scoutmb.interfaces.web.rendezvous import bind_loopback_socket

        sock = bind_loopback_socket()
        try:
            port = sock.getsockname()[1]
            # DESK-PORT-001 (INTENTIONAL_CHANGE, B9.1): unlike the old free_port(), which closed
            # its probe socket before returning (making the port immediately re-bindable),
            # bind_loopback_socket() keeps the socket open -- a second, independent socket
            # attempting to bind to the SAME port while the first is still held must fail.
            with pytest.raises(OSError), socket.socket(socket.AF_INET, socket.SOCK_STREAM) as rebinder:
                rebinder.bind(("127.0.0.1", port))
        finally:
            sock.close()
    else:
        assert case.scenario == "bind-conflict"
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            holder.bind(("127.0.0.1", 0))
            holder.listen(1)
            held_port = holder.getsockname()[1]
            with pytest.raises(OSError), socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("127.0.0.1", held_port))
        finally:
            holder.close()


# ==================================================================================================
# DESK-READY -- wait_until_ready's retry loop, driven entirely by a fake clock/sleeper and a
# patched urlopen. NO real time passes and NO real socket/HTTP request happens.
# ==================================================================================================
class _FakeUrlopenResult:
    def __enter__(self) -> _FakeUrlopenResult:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


@pytest.mark.parametrize(("case", "context_id"), execution_params(DESKTOP_READY_CASES))
def test_desktop_ready_execution(
    case: DesktopReadyCase, context_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    del context_id
    import run_app

    clock = {"now": 0.0}
    calls = {"urlopen": 0, "sleep": 0}

    def fake_monotonic() -> float:
        return clock["now"]

    def fake_sleep(seconds: float) -> None:
        calls["sleep"] += 1
        clock["now"] += seconds

    def fake_urlopen(url: str, timeout: float | None = None) -> _FakeUrlopenResult:
        calls["urlopen"] += 1
        if calls["urlopen"] <= case.failures_before_success:
            raise urllib.error.URLError("connection refused")
        return _FakeUrlopenResult()

    monkeypatch.setattr(run_app.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(run_app.time, "sleep", fake_sleep)
    monkeypatch.setattr(run_app.urllib.request, "urlopen", fake_urlopen)

    if case.expect_ready:
        run_app.wait_until_ready(
            "http://127.0.0.1:0/api/health", timeout_seconds=case.timeout_seconds
        )
    else:
        with pytest.raises(RuntimeError):
            run_app.wait_until_ready(
                "http://127.0.0.1:0/api/health", timeout_seconds=case.timeout_seconds
            )

    assert calls["urlopen"] == case.expect_urlopen_calls
    assert calls["sleep"] == case.expect_sleep_calls


# ==================================================================================================
# DESK-MODE -- main()'s post-readiness dispatch. start_server_on_free_port/wait_until_ready are
# both patched so no real server, socket, or sleep is ever touched; webbrowser and webview are
# patched so no real browser tab or native window is ever opened. (B9.1: free_port/start_server
# merged into one start_server_on_free_port() seam -- this case's OWN observed behavior --
# browser vs. native dispatch, return codes, exception propagation -- is unchanged, only the
# driving mechanics of what gets monkeypatched.)
# ==================================================================================================
@pytest.mark.parametrize(("case", "context_id"), execution_params(DESKTOP_MODE_CASES))
def test_desktop_mode_execution(
    case: DesktopModeCase, context_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    del context_id
    import run_app

    monkeypatch.setattr(run_app, "start_server_on_free_port", lambda: (None, 55555))

    if case.server_becomes_ready:
        monkeypatch.setattr(run_app, "wait_until_ready", lambda url: None)
    else:

        def _raise_not_ready(url: str) -> None:
            raise RuntimeError(f"Server did not become ready at {url}")

        monkeypatch.setattr(run_app, "wait_until_ready", _raise_not_ready)

    argv = ["run_app.py"]
    if case.browser_flag:
        argv.append("--browser")
    monkeypatch.setattr(sys, "argv", argv)

    browser_open_calls: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: browser_open_calls.append(url))

    webview_calls = {"create_window": 0, "start": 0}
    monkeypatch.setattr(
        "webview.create_window",
        lambda *args, **kwargs: webview_calls.__setitem__(
            "create_window", webview_calls["create_window"] + 1
        ),
    )

    def fake_webview_start() -> None:
        webview_calls["start"] += 1

    monkeypatch.setattr("webview.start", fake_webview_start)

    def fake_sleep(seconds: float) -> None:
        if case.raise_keyboard_interrupt_in_wait_loop:
            raise KeyboardInterrupt
        # If a case ever reached here without wanting an interrupt, avoid spinning forever --
        # the real production loop is `while True: time.sleep(1)`, so a test double must break
        # it after one iteration.
        raise RuntimeError("test double: unexpected time.sleep call in browser-mode wait loop")

    monkeypatch.setattr(run_app.time, "sleep", fake_sleep)

    if case.expect_propagated_exception is not None:
        with pytest.raises(case.expect_propagated_exception):
            run_app.main()
    else:
        return_code = run_app.main()
        assert return_code == case.expect_return_code

    assert bool(browser_open_calls) == case.expect_webbrowser_opened
    assert (webview_calls["create_window"] > 0 or webview_calls["start"] > 0) == (
        case.expect_webview_used
    )


def test_desktop_registry_is_structurally_valid() -> None:
    # See tests/matrix/pytest_support.py's assert_platform_domain_registry_valid docstring:
    # this shared body is byte-for-byte identical to the equivalent test in
    # test_platform_matrix.py/test_bootstrap_matrix.py, kept as a thin per-file wrapper here so
    # this catalog stays covered even if one of the other two files is ever deleted.
    assert_platform_domain_registry_valid()
