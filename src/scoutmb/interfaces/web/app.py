"""create_app(settings) -- UI-IMPORT-001: importing this module performs no filesystem,
network, or job side effects. Every side-effecting call (ensure_dirs, JobSupervisor
construction, route registration) happens INSIDE create_app or the lifespan, never at module
scope. Contrast with ui/server.py, which still does all of this at import time -- that stays
true intentionally until Slice 2b retires it (sub-plan 4), since UI-ROUTE-024..029 read its
module globals directly.

settings.ensure_dirs() is called HERE, synchronously, not only inside the lifespan -- a later
StaticFiles(directory=settings.runs_dir) mount inside this same function needs the directory to
already exist, since Starlette's StaticFiles constructor checks directory existence immediately,
before the lifespan (which runs later, only once something actually starts serving/tests the
app) ever gets a chance to create it. Calling ensure_dirs() here as well closes that ordering
gap; it is cheap and idempotent, so calling it twice (here and in the lifespan) costs nothing."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.resources import as_file, files

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from scoutmb.config import UiSettings
from scoutmb.runtime.jobs import JobSupervisor


def create_app(settings: UiSettings) -> FastAPI:
    settings.ensure_dirs()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.job_registry = JobSupervisor()
        app.state.operations = {}
        app.state.current_download = {}
        try:
            yield
        finally:
            await app.state.job_registry.shutdown()

    app = FastAPI(title="Troop 349 Summer Camp Command Program UI", lifespan=lifespan)

    @app.get("/api/health")
    async def health(nonce: str | None = None) -> dict[str, str]:
        configured_nonce = os.environ.get("SCOUTMB_READINESS_NONCE")
        if configured_nonce is not None and nonce != configured_nonce:
            raise HTTPException(status_code=401, detail="readiness nonce mismatch")
        return {"status": "ok"}

    from scoutmb.interfaces.web.routes import router

    app.include_router(router)

    # `as_file`'s context manager materializes a real filesystem path even if the package were
    # ever read from a zip (untested/unused per the Phase B spec's own scope note) -- for the
    # copied-release-root and installed-wheel cases this targets, static_root is already a real
    # directory and as_file is a cheap no-op wrapper, not a temp-extraction cost. Exiting the
    # `with` block immediately here is safe: for a real (non-zip) package, as_file yields the
    # underlying path directly, with no extraction and therefore no cleanup-on-exit hazard.
    static_root = files("scoutmb.resources").joinpath("web_static")
    with as_file(static_root) as static_path:
        app.mount("/runs", StaticFiles(directory=settings.runs_dir), name="runs")
        app.mount("/", StaticFiles(directory=static_path, html=True), name="static")

    return app
