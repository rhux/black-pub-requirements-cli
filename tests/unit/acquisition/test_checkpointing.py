"""ACQ-RESUME-001/002/003/004: checkpoint creation, skip-on-resume, UUID persistence, and
fail-closed on corruption -- INCLUDING type-confused shapes a hand-edited or partially-written
file could take, not just a wrong version number. No fake here -- these exercise the real
AtomicFileCheckpointStore against tmp_path, since the whole point is the on-disk round trip."""

from __future__ import annotations

import json
from types import MappingProxyType

import pytest

from scoutmb.adapters.files.checkpoint import AtomicFileCheckpointStore
from scoutmb.errors import ScoutmbError
from scoutmb.ports.checkpoint_store import Checkpoint, CorruptCheckpoint


def test_corrupt_checkpoint_is_a_scoutmb_error() -> None:
    assert issubclass(CorruptCheckpoint, ScoutmbError)


@pytest.mark.matrix_case(case_id="ACQ-RESUME-001", context_id="resume", lane="default")
def test_fresh_run_has_no_checkpoint(tmp_path) -> None:
    store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    assert store.load() is None


def test_save_then_load_round_trips(tmp_path) -> None:
    store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    checkpoint = Checkpoint(
        version=1,
        completed_urls=("https://x/a", "https://x/b"),
        output_ids={"attendee-1": "11111111-1111-4111-8111-111111111111"},
    )
    store.save(checkpoint)

    loaded = store.load()
    assert loaded == checkpoint


def test_output_ids_is_genuinely_immutable(tmp_path) -> None:
    """A dataclass's frozen=True freezes the FIELD REFERENCE, not a mutable dict sitting behind
    it -- Checkpoint.output_ids must be an actual read-only view, not merely typed Mapping."""
    store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    mutable_source = {"attendee-1": "uuid-1"}
    checkpoint = Checkpoint(version=1, completed_urls=(), output_ids=mutable_source)
    mutable_source["attendee-1"] = "mutated-after-construction"
    assert checkpoint.output_ids["attendee-1"] == "uuid-1"  # __post_init__ copied, not aliased

    assert isinstance(checkpoint.output_ids, MappingProxyType)
    with pytest.raises(TypeError):
        checkpoint.output_ids["attendee-1"] = "should-not-be-settable"  # type: ignore[index]


@pytest.mark.matrix_case(case_id="ACQ-RESUME-002", context_id="resume", lane="default")
def test_completed_url_is_recognized_on_resume(tmp_path) -> None:
    store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    store.save(Checkpoint(version=1, completed_urls=("https://x/a",), output_ids={}))

    loaded = store.load()
    assert loaded is not None
    assert "https://x/a" in loaded.completed_urls
    assert "https://x/b" not in loaded.completed_urls


@pytest.mark.matrix_case(case_id="ACQ-RESUME-003", context_id="resume", lane="default")
def test_output_id_map_survives_a_reload(tmp_path) -> None:
    store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    store.save(
        Checkpoint(version=1, completed_urls=(), output_ids={"attendee-1": "same-uuid"})
    )
    reloaded = AtomicFileCheckpointStore(tmp_path / "checkpoint.json").load()
    assert reloaded.output_ids["attendee-1"] == "same-uuid"


@pytest.mark.matrix_case(case_id="ACQ-RESUME-004", context_id="resume", lane="default")
def test_corrupt_json_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text("{not valid json", encoding="utf-8")
    store = AtomicFileCheckpointStore(path)
    with pytest.raises(CorruptCheckpoint):
        store.load()


def test_wrong_version_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps({"version": 999, "completed_urls": [], "output_ids": {}}), encoding="utf-8")
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_boolean_version_does_not_masquerade_as_one(tmp_path) -> None:
    """json.dumps(True) is the JSON literal `true`; json.loads('true') deserializes to Python's
    True, and `True == 1` since bool is an int subclass -- a naive `version != 1` check would
    silently accept this. core/output_schemas.py's check_schema_version already documents and
    guards against exactly this; the checkpoint loader must apply the same discipline."""
    path = tmp_path / "checkpoint.json"
    path.write_text('{"version": true, "completed_urls": [], "output_ids": {}}', encoding="utf-8")
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_missing_required_key_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps({"version": 1}), encoding="utf-8")
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_completed_urls_wrong_type_fails_closed(tmp_path) -> None:
    """A string is iterable, so a naive tuple(data["completed_urls"]) would silently produce a
    tuple of individual CHARACTERS instead of raising -- this must fail closed instead."""
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps({"version": 1, "completed_urls": "https://x/a", "output_ids": {}}),
        encoding="utf-8",
    )
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_output_ids_wrong_type_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps({"version": 1, "completed_urls": [], "output_ids": ["not", "a", "dict"]}),
        encoding="utf-8",
    )
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_output_ids_non_string_value_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps({"version": 1, "completed_urls": [], "output_ids": {"attendee-1": 12345}}),
        encoding="utf-8",
    )
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_completed_results_round_trips(tmp_path) -> None:
    """completed_results carries one scout_result_to_row-shaped mapping per completed scout's
    URL, so a resumed run can rebuild that scout's ScoutResult without re-fetching it -- see
    Task B5.5's run_batch, which is what actually reads this back via scout_result_from_row."""
    store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    row = {
        "name": "Avery",
        "qr_url": "https://x/a",
        "attendee_id": "A1",
        "classes": [],
        "requirements": [],
        "errors": [],
    }
    checkpoint = Checkpoint(
        version=1,
        completed_urls=("https://x/a",),
        output_ids={},
        completed_results={"https://x/a": row},
    )
    store.save(checkpoint)

    loaded = store.load()
    assert loaded == checkpoint
    assert loaded.completed_results["https://x/a"] == row


def test_completed_results_rows_are_genuinely_immutable_too(tmp_path) -> None:
    """Freezing only the OUTER completed_results mapping (an earlier draft's shape) leaves each
    ROW dict mutable through the exposed mapping's own values -- __post_init__ must wrap each
    row in its own MappingProxyType too, not just the top-level dict."""
    mutable_row = {"name": "Avery", "qr_url": "https://x/a", "attendee_id": "A1",
                    "classes": [], "requirements": [], "errors": []}
    checkpoint = Checkpoint(
        version=1, completed_urls=("https://x/a",), output_ids={},
        completed_results={"https://x/a": mutable_row},
    )
    mutable_row["name"] = "mutated-after-construction"
    assert checkpoint.completed_results["https://x/a"]["name"] == "Avery"  # copied, not aliased

    assert isinstance(checkpoint.completed_results["https://x/a"], MappingProxyType)
    with pytest.raises(TypeError):
        checkpoint.completed_results["https://x/a"]["name"] = "should-not-be-settable"


def test_checkpoint_without_completed_results_key_is_backward_compatible(tmp_path) -> None:
    """A checkpoint file saved before this field existed has no "completed_results" key at all
    -- it must still load, with the field defaulting to {}, not be treated as corrupt."""
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps({"version": 1, "completed_urls": ["https://x/a"], "output_ids": {}}),
        encoding="utf-8",
    )
    loaded = AtomicFileCheckpointStore(path).load()
    assert loaded is not None
    assert loaded.completed_results == {}


def test_completed_results_wrong_type_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "completed_urls": [],
                "output_ids": {},
                "completed_results": ["not", "a", "dict"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_completed_results_non_object_value_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "completed_urls": [],
                "output_ids": {},
                "completed_results": {"https://x/a": "not-an-object"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_completed_results_orphaned_url_fails_closed(tmp_path) -> None:
    """A completed_results entry for a URL absent from completed_urls is nonsensical -- if
    accepted, run_batch's `[scout_result_from_row(row) for row in completed_results.values()]`
    would inject a bogus reconstructed ScoutResult into the run's report even though that URL
    was never marked complete. Must fail closed, not silently accept the mismatch."""
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "completed_urls": [],  # empty -- the row below has no matching entry
                "output_ids": {},
                "completed_results": {
                    "https://x/orphan": {
                        "name": "Ghost", "qr_url": "https://x/orphan", "attendee_id": "G1",
                        "classes": [], "requirements": [], "errors": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_invalid_utf8_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_bytes(b"\xff\xfe\x00\x01not valid utf-8")
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_save_failure_preserves_prior_bytes(tmp_path, monkeypatch) -> None:
    """Reuses atomic_write_text's own contract: a failed os.replace leaves the previous file
    untouched. This test proves the CHECKPOINT save path actually benefits from that contract,
    not merely that atomic_write_text does (already proven elsewhere for report artifacts)."""
    path = tmp_path / "checkpoint.json"
    store = AtomicFileCheckpointStore(path)
    store.save(Checkpoint(version=1, completed_urls=("https://x/a",), output_ids={}))
    original_bytes = path.read_bytes()

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("scoutmb.adapters.files.atomic.os.replace", _boom)
    with pytest.raises(OSError):
        store.save(Checkpoint(version=1, completed_urls=("https://x/a", "https://x/b"), output_ids={}))

    assert path.read_bytes() == original_bytes
