"""PyInstaller entry point. Kept separate from main.py for testability."""

from __future__ import annotations

import sys
import traceback


def _run() -> int:
    from bootstrap.main import main

    return main()


if __name__ == "__main__":
    try:
        raise SystemExit(_run())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - last-resort net for failures before main()'s own handling
        try:
            import tkinter.messagebox as messagebox

            messagebox.showerror(
                "Setup failed",
                "Something went wrong before setup could start:\n\n" + traceback.format_exc(),
            )
        except Exception:
            print(traceback.format_exc(), file=sys.stderr)
        raise SystemExit(1)
