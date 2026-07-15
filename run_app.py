#!/usr/bin/env python3
"""Launch the Scouting Merit Badges UI.

By default this opens a chromeless native window (pywebview, using Windows'
built-in WebView2 control) around a local FastAPI server. Pass --browser to
open the same server in the system's default browser tab instead, which is
easier to use with normal browser devtools during development.
"""

from __future__ import annotations

import argparse
import asyncio
import socket
import threading
import time
import urllib.error
import urllib.request

import uvicorn

from ui import server


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start_server(port: int) -> None:
    config = uvicorn.Config(app=server.app, host="127.0.0.1", port=port, log_level="warning")
    uvicorn_server = uvicorn.Server(config)

    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(uvicorn_server.serve())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()


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

    port = free_port()
    start_server(port)
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

        webview.create_window("Scouting Merit Badges", base_url, width=1150, height=820, min_size=(760, 560))
        webview.start()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
