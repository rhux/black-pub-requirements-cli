"""Standalone check: can Playwright drive the system's Microsoft Edge?

Run with the app-local Python (not the frozen bootstrapper interpreter) once
Playwright is installed. No third-party imports besides playwright itself.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            browser.close()
        return 0
    except Exception as exc:  # noqa: BLE001 - report and let the caller decide
        print(f"msedge probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
