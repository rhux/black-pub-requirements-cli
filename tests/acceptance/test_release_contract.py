from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_gate_1_and_2_evidence_is_present():
    assert (REPO_ROOT / "tests/baselines/phase_a.json").exists()
    assert (REPO_ROOT / "tests/matrix/test_registry.py").exists()


def test_gate_3_deferred_status_is_explicitly_recorded():
    slice3_followup = REPO_ROOT / "docs/superpowers/plans/2026-08-26-slice-3-followup-launch-release-dir.md"
    text = slice3_followup.read_text()
    assert "still outstanding" in text.lower() or "deferred" in text.lower()


def test_no_stale_shim_comment_references_a_deleted_file():
    deleted = {"pdf_to_scouts.py", "scout_schedule_cli.py"}
    for path in (REPO_ROOT / "src/scoutmb/interfaces/cli").glob("*.py"):
        text = path.read_text()
        for name in deleted:
            assert name not in text, f"{path} still references deleted file {name}"
