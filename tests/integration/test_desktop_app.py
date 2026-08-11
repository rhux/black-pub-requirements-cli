"""Package-side equivalent of the legacy DESK-READY-*/DESK-MODE-* characterization catalog
(tests/characterization/test_desktop_matrix.py, deleted alongside run_app.py in this same
sub-plan's B10.3), driving scoutmb.interfaces.desktop.app instead of run_app.py.

DESK-READY-* cases drive _wait_until_ready's retry loop with a fake clock/sleeper and a patched
urlopen -- no real time passes and no real socket/HTTP request happens, exactly like the legacy
tests. DESK-MODE-* cases drive main()'s post-readiness dispatch (--browser vs. native webview,
a server-start failure propagating out of main(), and Ctrl+C handling) with bind_loopback_socket,
uvicorn.Server, threading.Thread, and _wait_until_ready all patched so no real server, socket,
thread, or sleep is ever touched; webbrowser and webview are patched so no real browser tab or
native window is ever opened."""

from __future__ import annotations

import socket
import sys
import urllib.error

import pytest

import scoutmb.interfaces.desktop.app as desktop_app


# ==================================================================================================
# DESK-READY equivalent -- _wait_until_ready's retry loop, driven entirely by a fake clock/sleeper
# and a patched urlopen. NO real time passes and NO real socket/HTTP request happens.
# ==================================================================================================
class _FakeUrlopenResult:
    def __enter__(self) -> _FakeUrlopenResult:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


@pytest.mark.parametrize(
    ("failures_before_success", "timeout_seconds", "expect_ready", "expect_urlopen_calls", "expect_sleep_calls"),
    [
        (0, 5.0, True, 1, 0),  # DESK-READY-001: immediate-success
        (2, 5.0, True, 3, 2),  # DESK-READY-002: retries-then-success
        (10_000, 0.3, False, 3, 3),  # DESK-READY-003: timeout-gives-up
    ],
)
def test_wait_until_ready(
    failures_before_success: int,
    timeout_seconds: float,
    expect_ready: bool,
    expect_urlopen_calls: int,
    expect_sleep_calls: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 0.0}
    calls = {"urlopen": 0, "sleep": 0}

    def fake_monotonic() -> float:
        return clock["now"]

    def fake_sleep(seconds: float) -> None:
        calls["sleep"] += 1
        clock["now"] += seconds

    def fake_urlopen(url: str, timeout: float | None = None) -> _FakeUrlopenResult:
        calls["urlopen"] += 1
        if calls["urlopen"] <= failures_before_success:
            raise urllib.error.URLError("connection refused")
        return _FakeUrlopenResult()

    monkeypatch.setattr(desktop_app.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(desktop_app.time, "sleep", fake_sleep)
    monkeypatch.setattr(desktop_app.urllib.request, "urlopen", fake_urlopen)

    if expect_ready:
        desktop_app._wait_until_ready("http://127.0.0.1:0/api/health", timeout_seconds=timeout_seconds)
    else:
        with pytest.raises(RuntimeError):
            desktop_app._wait_until_ready("http://127.0.0.1:0/api/health", timeout_seconds=timeout_seconds)

    assert calls["urlopen"] == expect_urlopen_calls
    assert calls["sleep"] == expect_sleep_calls


# ==================================================================================================
# DESK-MODE equivalent -- main()'s post-readiness dispatch. bind_loopback_socket/uvicorn.Server/
# threading.Thread/_wait_until_ready are all patched so no real server, socket, thread, or sleep
# is ever touched; webbrowser and webview are patched so no real browser tab or native window is
# ever opened.
# ==================================================================================================
@pytest.mark.parametrize(
    (
        "browser_flag",
        "server_becomes_ready",
        "raise_keyboard_interrupt_in_wait_loop",
        "expect_webbrowser_opened",
        "expect_webview_used",
        "expect_return_code",
        "expect_propagated_exception",
    ),
    [
        (True, True, True, True, False, 0, None),  # DESK-MODE-001: browser-mode
        (False, True, False, False, True, 0, None),  # DESK-MODE-002: native-mode
        (False, False, False, False, False, None, RuntimeError),  # DESK-MODE-003: server-start-failure
        (True, True, True, True, False, 0, None),  # DESK-MODE-004: keyboard-interrupt-during-browser-wait
    ],
)
def test_main_dispatch(
    browser_flag: bool,
    server_becomes_ready: bool,
    raise_keyboard_interrupt_in_wait_loop: bool,
    expect_webbrowser_opened: bool,
    expect_webview_used: bool,
    expect_return_code: int | None,
    expect_propagated_exception: type[BaseException] | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    real_sock.bind(("127.0.0.1", 0))
    real_sock.listen()
    monkeypatch.setattr(desktop_app, "bind_loopback_socket", lambda: real_sock)
    monkeypatch.setattr(desktop_app, "create_app", lambda settings: object())

    class _FakeUvicornServer:
        def __init__(self, config: object) -> None:
            pass

        async def serve(self, sockets: object) -> None:
            pass

    monkeypatch.setattr(desktop_app.uvicorn, "Config", lambda **kwargs: object())
    monkeypatch.setattr(desktop_app.uvicorn, "Server", _FakeUvicornServer)

    class _FakeThread:
        def __init__(self, *, target: object, daemon: bool) -> None:
            pass

        def start(self) -> None:
            pass

    monkeypatch.setattr(desktop_app.threading, "Thread", _FakeThread)

    if server_becomes_ready:
        monkeypatch.setattr(desktop_app, "_wait_until_ready", lambda url: None)
    else:

        def _raise_not_ready(url: str) -> None:
            raise RuntimeError(f"Server did not become ready at {url}")

        monkeypatch.setattr(desktop_app, "_wait_until_ready", _raise_not_ready)

    argv = ["troop349"]
    if browser_flag:
        argv.append("--browser")
    monkeypatch.setattr(sys, "argv", argv)

    browser_open_calls: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: browser_open_calls.append(url))

    webview_calls = {"create_window": 0, "start": 0}
    monkeypatch.setattr(
        desktop_app.webview,
        "create_window",
        lambda *args, **kwargs: webview_calls.__setitem__(
            "create_window", webview_calls["create_window"] + 1
        ),
    )

    def fake_webview_start() -> None:
        webview_calls["start"] += 1

    monkeypatch.setattr(desktop_app.webview, "start", fake_webview_start)

    def fake_sleep(seconds: float) -> None:
        if raise_keyboard_interrupt_in_wait_loop:
            raise KeyboardInterrupt
        raise RuntimeError("test double: unexpected time.sleep call in browser-mode wait loop")

    monkeypatch.setattr(desktop_app.time, "sleep", fake_sleep)

    try:
        if expect_propagated_exception is not None:
            with pytest.raises(expect_propagated_exception):
                desktop_app.main()
        else:
            return_code = desktop_app.main()
            assert return_code == expect_return_code

        assert bool(browser_open_calls) == expect_webbrowser_opened
        assert (webview_calls["create_window"] > 0 or webview_calls["start"] > 0) == (
            expect_webview_used
        )
    finally:
        real_sock.close()
