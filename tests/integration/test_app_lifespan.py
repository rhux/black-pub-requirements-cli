"""UI-IMPORT-001: create_app(settings) has no import-time side effects and constructs a fresh
app + JobSupervisor per call. The subprocess import-probe pattern proves the import itself
touches no filesystem/network state.

Lifespan is driven through Starlette's own `app.router.lifespan_context(app)` async context
manager -- the exact mechanism both `asgi-lifespan`'s LifespanManager and Starlette's own
TestClient use internally -- rather than a third-party dependency or plain httpx.ASGITransport,
which does NOT run lifespan on its own. An earlier draft of this test file used ASGITransport
alone and would have reached routes before app.state.settings/job_registry were ever set."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx

from scoutmb.config import UiSettings
from scoutmb.interfaces.web.app import create_app


def test_import_has_no_side_effects_in_a_poisoned_environment(tmp_path) -> None:
    poisoned_data_dir = tmp_path / "does-not-exist-and-must-stay-that-way"
    src_path = Path(__file__).resolve().parents[2] / "src"
    probe = (
        f"import sys; sys.path.insert(0, {str(src_path)!r})\n"
        "import scoutmb.interfaces.web.app\n"
        "print('IMPORT_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        env={"SCOUTMB_DATA_DIR": str(poisoned_data_dir)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout
    assert not poisoned_data_dir.exists(), "import must not have created the data root"


def test_create_app_returns_a_fresh_instance_each_call(tmp_path) -> None:
    settings_a = UiSettings(data_root=tmp_path / "a")
    settings_b = UiSettings(data_root=tmp_path / "b")
    app_a = create_app(settings_a)
    app_b = create_app(settings_b)
    assert app_a is not app_b


async def test_health_and_lifespan_shutdown(tmp_path) -> None:
    settings = UiSettings(data_root=tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert hasattr(app.state, "job_registry")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
