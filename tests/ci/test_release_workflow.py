from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_release_workflow() -> dict:
    return yaml.safe_load((REPO_ROOT / ".github/workflows/release.yml").read_text())


def test_release_workflow_defines_one_native_job_per_platform():
    workflow = _load_release_workflow()
    assert set(workflow["jobs"]) == {"launcher-windows", "launcher-macos"}


def test_each_release_job_runs_only_on_its_own_native_runner():
    workflow = _load_release_workflow()
    assert workflow["jobs"]["launcher-windows"]["runs-on"] == "windows-latest"
    assert workflow["jobs"]["launcher-macos"]["runs-on"] == "macos-latest"


def test_release_workflow_is_manually_triggered_not_on_every_push():
    workflow = _load_release_workflow()
    # PyYAML parses the bare `on:` key as the boolean True, not the string "on"
    triggers = workflow.get(True, workflow.get("on"))
    assert set(triggers) == {"workflow_dispatch"}


def test_each_release_job_actually_runs_the_release_marked_tests():
    workflow = _load_release_workflow()
    for job in workflow["jobs"].values():
        steps_text = " ".join(step.get("run", "") for step in job["steps"])
        assert "tests/release" in steps_text
        assert "-m release" in steps_text
