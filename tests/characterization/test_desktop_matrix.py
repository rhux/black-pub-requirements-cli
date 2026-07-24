"""Typed matrix execution of the desktop-launcher characterization catalog (Task 21, final
slice): ``run_app.py``'s ``free_port``, ``wait_until_ready``, and ``main`` dispatch.

``DESK-PORT-*`` drive a REAL loopback socket bind/close -- fast, safe, and exactly what
``free_port``'s contract is about. Every other case here injects at ``run_app``'s real current
seams (the plain module-level ``time.monotonic``/``time.sleep``/``urllib.request.urlopen``
names it binds via its own ``import time`` / ``import urllib.request`` statements, plus
``webbrowser.open``/``webview.create_window``/``webview.start`` for the two deferred imports
inside ``main()``) via ``pytest.MonkeyPatch`` -- never a real sleep, never a real HTTP request,
never a real browser tab or native window.
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
from tests.matrix.pytest_support import execution_params


# ==================================================================================================
# DESK-PORT -- real loopback socket bind/close.
# ==================================================================================================
@pytest.mark.parametrize(("case", "context_id"), execution_params(DESKTOP_PORT_CASES))
def test_desktop_port_execution(case: DesktopPortCase, context_id: str) -> None:
    del context_id
    if case.scenario == "free-port":
        import run_app

        port = run_app.free_port()
        # If free_port's `with socket.socket(...) as probe:` had leaked the probe's file
        # descriptor (or left it bound), a second, independent socket binding to the exact
        # same port would raise OSError (EADDRINUSE) here.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as rebinder:
            rebinder.bind(("127.0.0.1", port))
            rebinder.listen(1)
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
        run_app.wait_until_ready("http://127.0.0.1:0/api/health", timeout_seconds=case.timeout_seconds)
    else:
        with pytest.raises(RuntimeError):
            run_app.wait_until_ready(
                "http://127.0.0.1:0/api/health", timeout_seconds=case.timeout_seconds
            )

    assert calls["urlopen"] == case.expect_urlopen_calls
    assert calls["sleep"] == case.expect_sleep_calls


# ==================================================================================================
# DESK-MODE -- main()'s post-readiness dispatch. free_port/start_server/wait_until_ready are all
# patched so no real server, socket, or sleep is ever touched; webbrowser and webview are
# patched so no real browser tab or native window is ever opened.
# ==================================================================================================
@pytest.mark.parametrize(("case", "context_id"), execution_params(DESKTOP_MODE_CASES))
def test_desktop_mode_execution(
    case: DesktopModeCase, context_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    del context_id
    import run_app

    monkeypatch.setattr(run_app, "free_port", lambda: 55555)
    monkeypatch.setattr(run_app, "start_server", lambda port: None)

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
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.bootstrap_cases import ALL_BOOTSTRAP_METADATA
    from tests.matrix.cases.desktop_cases import ALL_DESKTOP_METADATA
    from tests.matrix.cases.platform_cases import ALL_PLATFORM_METADATA
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    platform_axes = [axis for axis in AXES if axis.domain is Domain.PLATFORM]
    platform_boundaries = [b for b in BOUNDARIES if b.domain is Domain.PLATFORM]

    errors = validate_registry(
        ALL_PLATFORM_METADATA + ALL_DESKTOP_METADATA + ALL_BOOTSTRAP_METADATA,
        platform_axes,
        platform_boundaries,
        [],
        list(POLICIES),
    )
    assert errors == ()
