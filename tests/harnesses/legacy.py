"""Isolated legacy ``ui.server`` module reload harness (Task 21).

``ui/server.py`` reads ``SCOUTMB_DATA_DIR`` (via ``UiSettings.resolve``) and computes
``SCOUTS_CSV`` / ``PDF_UPLOADS_DIR`` / ``RUNS_DIR`` / the module-level ``operations`` /
``busy`` / ``current_download`` state ALL AT IMPORT TIME (see ``ui/server.py:86-99``). That
means a single shared import (as ``tests/conftest.py`` already sandboxes for the whole
session) cannot give each interface-matrix test its own isolated data root -- the module has
to be re-imported fresh, under a freshly-set env var, for every test that needs a distinct
``tmp_path``-scoped root.

This harness does exactly that: point ``SCOUTMB_DATA_DIR`` at the caller's ``data_root``,
drop any cached ``ui.server`` module so the next import re-reads the env var and re-runs
``SETTINGS.ensure_dirs()`` against the new root, then restore the PREVIOUS module identity and
env var on exit so later tests (and the session-wide sandbox conftest.py installs) are
unaffected.

``load_legacy_ui`` is an ASYNC context manager (not a plain ``@contextmanager``) specifically
so it can genuinely ``await`` the drain of any asyncio tasks a caller's requests started
(``asyncio.create_task(worker())`` in the ``/api/pdf-extract`` and ``/api/schedule-download``
handlers) before asserting the module's shared dicts are empty on exit -- a synchronous
``finally`` cannot await a cancelled task's actual completion.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType

DATA_DIR_ENV = "SCOUTMB_DATA_DIR"


@asynccontextmanager
async def load_legacy_ui(data_root: Path) -> AsyncIterator[ModuleType]:
    old = os.environ.get(DATA_DIR_ENV)
    os.environ[DATA_DIR_ENV] = str(data_root)
    sys.modules.pop("ui.server", None)
    before_tasks = {task for task in asyncio.all_tasks() if not task.done()}
    module: ModuleType | None = None
    try:
        module = __import__("ui.server", fromlist=["server"])
        module.operations.clear()
        module.busy.update({"pdf-extract": False, "schedule-download": False})
        module.current_download.clear()
        yield module
    finally:
        try:
            if module is not None:
                # Cancel and await any worker() tasks this test's requests scheduled via
                # asyncio.create_task, so nothing leaks into a later test/event loop.
                after_tasks = {task for task in asyncio.all_tasks() if not task.done()}
                spawned = after_tasks - before_tasks
                for task in spawned:
                    task.cancel()
                for task in spawned:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task

                assert module.operations == {}, "operations leaked across load_legacy_ui"
                assert module.current_download == {}, (
                    "current_download leaked across load_legacy_ui"
                )
                assert module.busy == {"pdf-extract": False, "schedule-download": False}, (
                    "busy flags leaked across load_legacy_ui"
                )
        finally:
            # This cleanup MUST run even if the leak-detection asserts above fired -- an
            # AssertionError here means a real leak was caught (exactly what this harness
            # exists to detect), and letting it skip the module-cache eviction / env-var
            # restore would leak stale module/env state into every later test in the session,
            # on top of the original failure.
            sys.modules.pop("ui.server", None)
            if old is None:
                os.environ.pop(DATA_DIR_ENV, None)
            else:
                os.environ[DATA_DIR_ENV] = old
