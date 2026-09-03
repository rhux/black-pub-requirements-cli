"""Standalone check: can Playwright drive the system's installed Google Chrome on macOS?

Run with the app-local Python (not the frozen bootstrapper interpreter) once
Playwright is installed. No third-party imports besides playwright itself.
Mirrors bootstrap/probe_msedge.py's shape exactly, substituting the "chrome" channel.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            browser.close()
        return 0
    except Exception as exc:  # noqa: BLE001 - report and let the caller decide
        print(f"chrome (macOS) probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
