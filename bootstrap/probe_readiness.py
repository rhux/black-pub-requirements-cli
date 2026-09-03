"""Standalone check: can the given Playwright channel (or bundled Chromium if omitted) launch
and complete one real navigation?

Run with the app-local Python, never the frozen bootstrapper interpreter -- mirrors
bootstrap/probe_msedge.py's shape, parameterized via argv instead of a fixed channel. This is
the ONLY place a readiness check imports playwright; browser_setup.py itself never does, so the
frozen bootstrapper's own PyInstaller Analysis never pulls playwright into the installer.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--channel", default=None)
    args = parser.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            launch_kwargs: dict[str, object] = {"headless": True}
            if args.channel:
                launch_kwargs["channel"] = args.channel
            browser = playwright.chromium.launch(**launch_kwargs)
            try:
                page = browser.new_page()
                page.goto(args.url, timeout=5_000)
            finally:
                browser.close()
        return 0
    except Exception as exc:  # noqa: BLE001 - report and let the caller decide
        print(f"readiness probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
