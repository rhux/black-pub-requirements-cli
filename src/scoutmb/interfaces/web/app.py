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

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    from scoutmb.interfaces.web.routes import router

    app.include_router(router)

    return app
