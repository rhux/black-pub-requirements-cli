"""troop349-schedule console script: argument-for-argument identical to scout_schedule_cli.py's
CLI. Interface layer -- argument parsing and orchestration only, mirroring interfaces/cli/pdf.py's
existing shape. Playwright/acquisition/reporting all live in scout_schedule_cli.py itself at this
point in the plan (retirement is sub-plan 4's Task B10), so this module delegates straight to
scout_schedule_cli.async_main -- there is no package-side async_main to call yet.

This is a genuine Form-2 adapting shim (parse -> delegate -> return) in the Phase B spec's
sense, permitted for a module that must exist before its full package-side equivalent does.
Importing scout_schedule_cli here relies on the repo root being on sys.path -- true under
pytest (tests/__init__.py triggers pytest's own rootdir insertion) and true for an installed
editable console script (pyproject.toml's dev-mode-dirs explicitly adds the repo root alongside
src for exactly this reason, per that setting's own comment)."""

from __future__ import annotations

import asyncio
import sys

import scout_schedule_cli as legacy


def main() -> int:
    config = legacy.parse_args()
    try:
        return asyncio.run(legacy.async_main(config))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
