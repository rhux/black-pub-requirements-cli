#!/usr/bin/env python3
"""Launch the Troop 349 Summer Camp Command Program UI.

By default this opens a chromeless native window (pywebview, using Windows'
built-in WebView2 control) around a local FastAPI server. Pass --browser to
open the same server in the system's default browser tab instead, which is
easier to use with normal browser devtools during development.
"""

from __future__ import annotations

import argparse
import asyncio
import threading
import time
import urllib.error
import urllib.request

import uvicorn

from scoutmb.interfaces.web.rendezvous import bind_loopback_socket
from ui import server


def start_server_on_free_port() -> tuple[threading.Thread, int]:
    sock = bind_loopback_socket()
    port = sock.getsockname()[1]
    config = uvicorn.Config(app=server.app, host="127.0.0.1", port=port, log_level="warning")
    uvicorn_server = uvicorn.Server(config)

    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # uvicorn.Server.serve(sockets=[...]) binds no NEW socket of its own -- it accepts
        # connections on the one already bound above, closing the probe-bind-close-then-rebind
        # gap the old free_port()/start_server(port) two-step dance had.
        loop.run_until_complete(uvicorn_server.serve(sockets=[sock]))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, port


def wait_until_ready(url: str, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.1)
    raise RuntimeError(f"Server did not become ready at {url}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open in the system's default browser instead of a native window.",
    )
    args = parser.parse_args()

    _thread, port = start_server_on_free_port()
    base_url = f"http://127.0.0.1:{port}/"
    wait_until_ready(base_url + "api/health")

    if args.browser:
        import webbrowser

        webbrowser.open(base_url)
        print(f"Serving at {base_url} (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0
    else:
        import webview

        webview.create_window("Troop 349 Summer Camp Command Program", base_url, width=1150, height=820, min_size=(760, 560))
        webview.start()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
