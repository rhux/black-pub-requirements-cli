"""Desktop launcher characterization catalog (Task 21): ``run_app.py``'s ``free_port``,
``wait_until_ready``, and ``main`` dispatch logic.

Domain choice (documented, not left implicit): ``run_app.py`` has no dedicated ``Domain``
member of its own -- ``Domain`` is a Task-16 locked contract other tasks depend on, so this
catalog reuses ``Domain.PLATFORM`` (the same domain ``PLAT-WIN``/``PLAT-MAC`` already use for
"this codebase's own platform-facing entrypoint code", as opposed to ``Domain.INTERFACE``, which
is reserved for ``ui/server.py``'s FastAPI app surface). ``run_app.py`` is the platform-specific
desktop bootstrap wrapper *around* that FastAPI app, not the app itself, so ``PLATFORM`` is the
closer fit.

This module holds only frozen data -- it never imports ``run_app`` at module level. The runner
in ``tests/characterization/test_desktop_matrix.py`` performs the real import and drives the
real ``free_port``/``wait_until_ready``/``main`` functions, injecting at their real current
seams (patching the module-level ``time.monotonic``/``time.sleep``/``urllib.request.urlopen``/
``webbrowser.open``/``webview.create_window``/``webview.start`` names ``run_app`` itself binds
via its ``import time`` / ``import urllib.request`` / (deferred) ``import webbrowser`` /
(deferred) ``import webview`` statements -- these are the actual, only injectable seams in the
real code today; nothing here invents a parameter or refactor that doesn't already exist).

``DESK-PORT-001``/``002`` exercise a REAL loopback socket bind/close (fast, safe, and exactly
what free_port's contract is about) -- every other case in this catalog performs no real
socket/HTTP I/O, no real sleep, and opens no real browser/webview window.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.matrix.model import CaseMetadata, Classification, Domain, EvidenceKind

_EVIDENCE_PORT = "run_app.py:25-28 free_port"
_EVIDENCE_READY = "run_app.py:44-52 wait_until_ready"
_EVIDENCE_MODE = "run_app.py:55-85 main"


@dataclass(frozen=True, slots=True)
class DesktopPortCase:
    meta: CaseMetadata
    scenario: str  # "free-port" | "bind-conflict"


@dataclass(frozen=True, slots=True)
class DesktopReadyCase:
    meta: CaseMetadata
    failures_before_success: int  # number of urlopen calls that raise before one succeeds
    timeout_seconds: float
    expect_ready: bool  # False => wait_until_ready must raise RuntimeError
    expect_urlopen_calls: int
    expect_sleep_calls: int


@dataclass(frozen=True, slots=True)
class DesktopModeCase:
    meta: CaseMetadata
    browser_flag: bool
    server_becomes_ready: bool
    raise_keyboard_interrupt_in_wait_loop: bool
    expect_webbrowser_opened: bool
    expect_webview_used: bool
    expect_return_code: int | None  # None => main() must let an exception propagate uncaught
    expect_propagated_exception: type[BaseException] | None


def _meta(case_id: str, axis_id: str, member: str, rationale: str, evidence: str) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id=axis_id,
        member=member,
        domain=Domain.PLATFORM,
        classification=Classification.PRESERVE,
        evidence=EvidenceKind.CURRENT_BRANCH,
        rationale=rationale,
        contexts=(axis_id.lower(),),
        evidence_reference=evidence,
    )


# ==================================================================================================
# DESK-PORT-001..002 -- free_port's real socket bind/close contract (REAL loopback socket).
# ==================================================================================================
DESKTOP_PORT_CASES: tuple[DesktopPortCase, ...] = (
    DesktopPortCase(
        meta=_meta(
            "DESK-PORT-001",
            "DESK-PORT",
            "free-port-closed-cleanly",
            "free_port binds an ephemeral port with the `with socket.socket(...) as probe:` "
            "context manager, so the probe socket is guaranteed closed (via __exit__) the "
            "instant getsockname()[1] is read and returned -- no descriptor is held open past "
            "the function's own body, and the returned port number must be immediately "
            "re-bindable by a second, independent socket.",
            _EVIDENCE_PORT,
        ),
        scenario="free-port",
    ),
    DesktopPortCase(
        meta=_meta(
            "DESK-PORT-002",
            "DESK-PORT",
            "bind-conflict-surfaces",
            "free_port itself never collides (the OS assigns an ephemeral port via bind to "
            "port 0), but the SAME `probe.bind(...)` call, when aimed at a port already held "
            "open by another live socket instead of port 0, raises a real, catchable OSError "
            "(EADDRINUSE) -- pinning that a bind conflict on this exact code shape is never "
            "silently swallowed.",
            _EVIDENCE_PORT,
        ),
        scenario="bind-conflict",
    ),
)


# ==================================================================================================
# DESK-READY-001..003 -- wait_until_ready's retry loop. ALL THREE use a fake time.monotonic
# (an incrementing counter) and a fake time.sleep (records calls, advances nothing real) plus a
# patched urllib.request.urlopen -- NO real time passes and NO real socket/HTTP call happens.
# ==================================================================================================
DESKTOP_READY_CASES: tuple[DesktopReadyCase, ...] = (
    DesktopReadyCase(
        meta=_meta(
            "DESK-READY-001",
            "DESK-READY",
            "immediate-success",
            "When the very first urlopen call succeeds (the server was already listening), "
            "wait_until_ready returns immediately without ever calling time.sleep -- the retry "
            "branch is never entered.",
            _EVIDENCE_READY,
        ),
        failures_before_success=0,
        timeout_seconds=5.0,
        expect_ready=True,
        expect_urlopen_calls=1,
        expect_sleep_calls=0,
    ),
    DesktopReadyCase(
        meta=_meta(
            "DESK-READY-002",
            "DESK-READY",
            "retries-then-success",
            "Two consecutive connection failures (each caught by the except clause, which "
            "sleeps 0.1s and loops) followed by a third urlopen call that succeeds: "
            "wait_until_ready returns normally having called time.sleep exactly twice, one per "
            "failed attempt, proving the retry loop genuinely retries rather than giving up "
            "after the first failure.",
            _EVIDENCE_READY,
        ),
        failures_before_success=2,
        timeout_seconds=5.0,
        expect_ready=True,
        expect_urlopen_calls=3,
        expect_sleep_calls=2,
    ),
    DesktopReadyCase(
        meta=_meta(
            "DESK-READY-003",
            "DESK-READY",
            "timeout-gives-up",
            "When urlopen never succeeds before the deadline (time.monotonic's fake clock is "
            "driven past deadline by the loop's own repeated time.sleep-adjacent advance), the "
            "while loop condition (`time.monotonic() < deadline`) goes false and the function "
            "falls through to `raise RuntimeError(...)` -- it gives up after a time budget "
            "rather than retrying forever.",
            _EVIDENCE_READY,
        ),
        failures_before_success=10_000,  # never succeeds within the fake deadline
        timeout_seconds=0.3,
        expect_ready=False,
        expect_urlopen_calls=3,  # exactly as many attempts as fit before the fake clock crosses 0.3s
        expect_sleep_calls=3,
    ),
)


# ==================================================================================================
# DESK-MODE-001..004 -- main()'s post-readiness dispatch: --browser vs. native webview, a
# server-start failure propagating out of main(), and Ctrl+C handling. free_port/start_server/
# wait_until_ready are all patched so no real server, socket, or sleep is ever touched; webbrowser
# and webview are patched so no real browser tab or native window is ever opened.
# ==================================================================================================
DESKTOP_MODE_CASES: tuple[DesktopModeCase, ...] = (
    DesktopModeCase(
        meta=_meta(
            "DESK-MODE-001",
            "DESK-MODE",
            "browser-mode",
            "With --browser passed, main() imports webbrowser and calls webbrowser.open(base_url) "
            "-- it never imports or touches the webview module at all (the `else` branch, and "
            "its `import webview`, is simply never reached).",
            _EVIDENCE_MODE,
        ),
        browser_flag=True,
        server_becomes_ready=True,
        raise_keyboard_interrupt_in_wait_loop=True,
        expect_webbrowser_opened=True,
        expect_webview_used=False,
        expect_return_code=0,
        expect_propagated_exception=None,
    ),
    DesktopModeCase(
        meta=_meta(
            "DESK-MODE-002",
            "DESK-MODE",
            "native-mode",
            "Without --browser, main() takes the `else` branch: it imports webview, calls "
            "webview.create_window(...) then webview.start(), and never imports or calls "
            "webbrowser.open at all. When webview.start() returns normally (the real call "
            "blocks until the window closes; here it's patched to return immediately), main() "
            "falls through to `return 0`.",
            _EVIDENCE_MODE,
        ),
        browser_flag=False,
        server_becomes_ready=True,
        raise_keyboard_interrupt_in_wait_loop=False,
        expect_webbrowser_opened=False,
        expect_webview_used=True,
        expect_return_code=0,
        expect_propagated_exception=None,
    ),
    DesktopModeCase(
        meta=_meta(
            "DESK-MODE-003",
            "DESK-MODE",
            "server-start-failure-propagates",
            "start_server itself never raises synchronously (uvicorn.Server.serve() runs "
            "inside a background daemon thread, so a bind/startup failure there never reaches "
            "the caller); the ONLY way a server-start failure becomes visible to main() is "
            "wait_until_ready's own `raise RuntimeError(...)` once its deadline passes. main() "
            "wraps none of free_port/start_server/wait_until_ready in a try/except, so this "
            "RuntimeError propagates straight out of main() uncaught -- there is no graceful "
            "error report for this failure in the current code.",
            _EVIDENCE_MODE,
        ),
        browser_flag=False,
        server_becomes_ready=False,
        raise_keyboard_interrupt_in_wait_loop=False,
        expect_webbrowser_opened=False,
        expect_webview_used=False,
        expect_return_code=None,
        expect_propagated_exception=RuntimeError,
    ),
    DesktopModeCase(
        meta=_meta(
            "DESK-MODE-004",
            "DESK-MODE",
            "keyboard-interrupt-during-browser-wait",
            "KeyboardInterrupt handling is asymmetric across the two modes in the CURRENT code: "
            "browser mode wraps its `while True: time.sleep(1)` loop in "
            "`try/except KeyboardInterrupt: return 0`, so Ctrl+C there is turned into a clean "
            "exit code 0. Native/webview mode has NO such try/except around webview.start() -- "
            "this case pins the browser-mode contract specifically (a KeyboardInterrupt raised "
            "from inside the wait loop's time.sleep is caught and converted to return 0), "
            "without asserting anything about the unguarded native-mode path.",
            _EVIDENCE_MODE,
        ),
        browser_flag=True,
        server_becomes_ready=True,
        raise_keyboard_interrupt_in_wait_loop=True,
        expect_webbrowser_opened=True,
        expect_webview_used=False,
        expect_return_code=0,
        expect_propagated_exception=None,
    ),
)


ALL_DESKTOP_METADATA: tuple[CaseMetadata, ...] = (
    tuple(case.meta for case in DESKTOP_PORT_CASES)
    + tuple(case.meta for case in DESKTOP_READY_CASES)
    + tuple(case.meta for case in DESKTOP_MODE_CASES)
)
