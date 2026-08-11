"""Gate 2's release-root acceptance sequence: copy the root outside the repo, remove the repo
from the environment, launch, confirm health + one report renders. This is the SEQUENCE the
Phase B spec names as the acceptance condition -- not a claim, a specific reproducible check."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_copied_release_root_starts_and_renders_a_report(tmp_path: Path) -> None:
    release_root = tmp_path / "release"
    release_root.mkdir()
    shutil.copytree(REPO_ROOT / "src" / "scoutmb", release_root / "scoutmb")
    shutil.copy2(REPO_ROOT / "requirements.txt", release_root / "requirements.txt")
    output_dir = tmp_path / "output"

    # Both halves of Gate 2's acceptance sequence in one probe: the health endpoint answers,
    # AND a real report.html renders through the composition root's own ReportingService --
    # not just a health check, which would only prove the app boots, not that reporting works
    # from a copied root with no repository present.
    probe = (
        "import sys; sys.path.insert(0, %r)\n"
        "from scoutmb.interfaces.web.app import create_app\n"
        "from scoutmb.config import UiSettings\n"
        "from scoutmb.interfaces.cli.composition import build_reporting_service\n"
        "from scoutmb.core.identity import RunIdentity\n"
        "from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutResult\n"
        "from fastapi.testclient import TestClient\n"
        "import tempfile, pathlib\n"
        "\n"
        "with tempfile.TemporaryDirectory() as data_dir:\n"
        "    app = create_app(UiSettings(data_root=pathlib.Path(data_dir)))\n"
        "    with TestClient(app) as client:\n"
        "        response = client.get('/api/health')\n"
        "        assert response.status_code == 200, response.text\n"
        "        assert response.json() == {'status': 'ok'}\n"
        "\n"
        "result = ScoutResult(\n"
        "    name='Avery Example', qr_url='https://scoutingevent.com/mobile/x', attendee_id='A1',\n"
        "    classes=(ClassRecord(scout_name='Avery Example', attendee_id='A1', class_number='1',\n"
        "        class_p4_id='C1', class_name='Chess', days='', period_name='', start_time='',\n"
        "        start_time_24h='', location='', has_requirements=True, class_completed=False,\n"
        "        raw_class_name=''),),\n"
        "    requirements=(RequirementRecord(scout_name='Avery Example', attendee_id='A1',\n"
        "        class_number='1', class_p4_id='C1', merit_badge_name='Chess', requirement_id='R1',\n"
        "        requirement_type_id='1', requirement_number='#1', description='Show up.',\n"
        "        completed_requirement=False, completed_class=False, requirement_on_event=True,\n"
        "        present_days=''),),\n"
        "    errors=(),\n"
        ")\n"
        "output_dir = pathlib.Path(%r)\n"
        "build_reporting_service().publish(\n"
        "    output_dir, [result], generated_at_local='2026-08-05 09:00:00 UTC',\n"
        "    generated_at_iso='2026-08-05T09:00:00+00:00', run_identity=RunIdentity(),\n"
        ")\n"
        "report_html = output_dir / 'report.html'\n"
        "assert report_html.is_file() and report_html.stat().st_size > 0, 'report.html did not render'\n"
        "print('RELEASE_ROOT_ACCEPTANCE_OK')\n"
    ) % (str(release_root), str(output_dir))

    # Run from release_root itself, with REPO_ROOT absent from sys.path/PYTHONPATH/cwd --
    # the "remove the repository from the environment" half of the acceptance sequence.
    env = {"PATH": "/usr/bin:/bin"}  # deliberately minimal; no PYTHONPATH, no repo-derived vars
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=release_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "RELEASE_ROOT_ACCEPTANCE_OK" in result.stdout
