"""UI-IMPORT-001: create_app(settings) has no import-time side effects and constructs a fresh
app + JobSupervisor per call. The subprocess import-probe pattern proves the import itself
touches no filesystem/network state.

Lifespan is driven through Starlette's own `app.router.lifespan_context(app)` async context
manager -- the exact mechanism both `asgi-lifespan`'s LifespanManager and Starlette's own
TestClient use internally -- rather than a third-party dependency or plain httpx.ASGITransport,
which does NOT run lifespan on its own. An earlier draft of this test file used ASGITransport
alone and would have reached routes before app.state.settings/job_registry were ever set."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from scoutmb.config import UiSettings
from scoutmb.interfaces.web.app import create_app

_PROBE_SOURCE = (
    "import sys; sys.path.insert(0, {src_path!r})\n"
    "import scoutmb.interfaces.web.app\n"
    "print('IMPORT_OK')\n"
)


@pytest.mark.matrix_case(case_id="UI-IMPORT-001", context_id="import", lane="default")
def test_import_has_no_side_effects_in_a_poisoned_environment(tmp_path) -> None:
    poisoned_data_dir = tmp_path / "does-not-exist-and-must-stay-that-way"
    src_path = Path(__file__).resolve().parents[2] / "src"
    probe = _PROBE_SOURCE.format(src_path=str(src_path))
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


@pytest.mark.matrix_case(case_id="UI-IMPORT-002", context_id="import", lane="default")
def test_import_never_touches_the_real_platform_data_root(tmp_path) -> None:
    """UI-IMPORT-002: a plain import must never create or write anything under the REAL
    platform-specific data root -- not even when SCOUTMB_DATA_DIR is entirely UNSET (the
    scenario where UiSettings.resolve() would otherwise fall back to _platform_data_root()).
    A fake HOME stands in for the real one so this test can assert on a real, deterministic
    path without ever touching the actual user's home directory."""
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    src_path = Path(__file__).resolve().parents[2] / "src"
    probe = _PROBE_SOURCE.format(src_path=str(src_path))
    env = {"HOME": str(fake_home), "PATH": os.environ.get("PATH", "")}
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout

    if sys.platform == "win32":
        real_root = fake_home  # LOCALAPPDATA-based; not exercised on this host either way
    elif sys.platform == "darwin":
        real_root = fake_home / "Library" / "Application Support" / "ScoutingMeritBadges"
    else:
        real_root = fake_home / ".local" / "share" / "ScoutingMeritBadges"
    assert not real_root.exists(), "import must not have created the real platform data root"


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
