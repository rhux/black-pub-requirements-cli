from __future__ import annotations

import http.server
import threading

import pytest


@pytest.fixture
def loopback_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    thread.join(timeout=5)


@pytest.mark.playwright
async def test_selected_engine_completes_local_fake_flow(loopback_server):
    from bootstrap.browser_setup import verify_readiness

    port = loopback_server.server_address[1]
    assert await verify_readiness(channel=None, url=f"http://127.0.0.1:{port}/")


@pytest.mark.playwright
async def test_readiness_failure_does_not_switch_engines(monkeypatch):
    from bootstrap import browser_setup

    calls: list[str] = []
    monkeypatch.setattr(
        browser_setup, "install_chromium_capability", lambda *a, **k: calls.append("switched")
    )

    # Port 1 is a privileged/unused port -- connecting there fails fast and reliably.
    ok = await browser_setup.verify_readiness(channel=None, url="http://127.0.0.1:1/")

    assert ok is False
    assert calls == []  # a readiness failure is reported, never silently worked around
