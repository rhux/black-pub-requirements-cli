"""troop349 console script: native pywebview window around the package's create_app(settings),
using the same race-free port-zero bind as run_app.py."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import uvicorn
import webview

from scoutmb.config import UiSettings
from scoutmb.interfaces.web.app import create_app
from scoutmb.interfaces.web.rendezvous import bind_loopback_socket
from scoutmb.logging_setup import configure_logging


def _wait_until_ready(url: str, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.1)
    raise RuntimeError(f"Server did not become ready at {url}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch the Troop 349 Summer Camp Command Program UI."
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open in the system's default browser instead of a native window.",
    )
    args = parser.parse_args()

    settings = UiSettings.resolve()
    configure_logging(settings.data_root)

    app = create_app(settings)
    sock = bind_loopback_socket()
    port = sock.getsockname()[1]
    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    uvicorn_server = uvicorn.Server(config)

    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(uvicorn_server.serve(sockets=[sock]))

    threading.Thread(target=run, daemon=True).start()
    base_url = f"http://127.0.0.1:{port}/"
    _wait_until_ready(base_url + "api/health")

    readiness_file = os.environ.get("SCOUTMB_READINESS_FILE")
    if readiness_file:
        Path(readiness_file).write_text(
            json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8"
        )

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
        webview.create_window(
            "Troop 349 Summer Camp Command Program",
            base_url,
            width=1150,
            height=820,
            min_size=(760, 560),
        )
        webview.start()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
