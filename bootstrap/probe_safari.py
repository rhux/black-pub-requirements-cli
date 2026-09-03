"""Standalone check: can Playwright drive Safari (WebKit) on macOS?

Experimental only -- never invoked by the normal resolve_browser_channel path. Reachable solely
through browser_setup.resolve_experimental_safari()'s explicit, separately-gated opt-in. Run with
the app-local Python once Playwright is installed; mirrors bootstrap/probe_msedge.py's shape.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.webkit.launch(headless=True)
            browser.close()
        return 0
    except Exception as exc:  # noqa: BLE001 - report and let the caller decide
        print(f"safari (webkit) probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
