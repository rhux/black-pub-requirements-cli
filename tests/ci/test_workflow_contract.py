from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_supply_chain_job_is_required_in_ci():
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    assert "supply-chain" in workflow["jobs"]
    job = workflow["jobs"]["supply-chain"]
    steps_text = " ".join(step.get("run", "") for step in job["steps"])
    assert "uv audit" in steps_text
    assert "check_licenses.py" in steps_text
