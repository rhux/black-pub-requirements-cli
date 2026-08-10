"""Atomic JSON checkpoint file (ACQ-RESUME). Reuses atomic_write_text's same-dir-temp-then-
replace contract (D11) -- a failed save never truncates the previous checkpoint.

load() validates every field's TYPE, not just presence -- a hand-edited or partially-written
file can have the right keys with the wrong shapes (a string where a list is expected, a bool
where an int is expected), and each of those must fail closed rather than silently produce
garbage (json.loads("...")'s dynamic typing means Python raises nothing on its own for most of
these; only an explicit type check does)."""

from __future__ import annotations

import json
from pathlib import Path

from scoutmb.adapters.files.atomic import atomic_write_text
from scoutmb.ports.checkpoint_store import CHECKPOINT_VERSION, Checkpoint, CorruptCheckpoint


class AtomicFileCheckpointStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Checkpoint | None:
        if not self._path.exists():
            return None
        try:
            raw_bytes = self._path.read_bytes()
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CorruptCheckpoint(f"{self._path} is not valid UTF-8") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CorruptCheckpoint(f"{self._path} is not valid JSON") from exc

        if not isinstance(data, dict):
            raise CorruptCheckpoint(f"{self._path} does not contain a JSON object")

        version = data.get("version")
        # type(version) is int (not isinstance, not ==) is deliberate -- bool is an int
        # subclass (isinstance(True, int) is True, True == 1 is True), and core/output_schemas.py's
        # check_schema_version already documents this exact hazard for the same reason.
        if type(version) is not int or version != CHECKPOINT_VERSION:
            raise CorruptCheckpoint(
                f"{self._path} has version {version!r}, this build reads {CHECKPOINT_VERSION!r}"
            )

        try:
            raw_completed_urls = data["completed_urls"]
            raw_output_ids = data["output_ids"]
        except KeyError as exc:
            raise CorruptCheckpoint(f"{self._path} is missing required key {exc}") from exc

        if not isinstance(raw_completed_urls, list) or not all(
            isinstance(url, str) for url in raw_completed_urls
        ):
            raise CorruptCheckpoint(f"{self._path}'s completed_urls must be a list of strings")

        if not isinstance(raw_output_ids, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in raw_output_ids.items()
        ):
            raise CorruptCheckpoint(f"{self._path}'s output_ids must be a string-to-string object")

        # .get, not data["completed_results"] -- a checkpoint file saved before this field
        # existed has no such key at all, and that must still load (backward compatible), not
        # be treated as corruption the way a genuinely wrong-shaped value is.
        raw_completed_results = data.get("completed_results", {})
        if not isinstance(raw_completed_results, dict) or not all(
            isinstance(key, str) and isinstance(value, dict)
            for key, value in raw_completed_results.items()
        ):
            raise CorruptCheckpoint(
                f"{self._path}'s completed_results must be a string-to-object mapping"
            )
        # Every completed_results key must also appear in completed_urls -- an orphaned entry
        # (a URL never marked complete, but present in completed_results) would otherwise inject
        # a bogus reconstructed ScoutResult into the run's report the moment run_batch reads
        # completed_results.values(), since that reconstruction never cross-checks against
        # completed_urls itself. The reverse (a completed_urls entry absent from
        # completed_results) is explicitly NOT required here -- that's the legitimate
        # backward-compat shape run_batch handles by re-processing the scout, not a corruption.
        if not set(raw_completed_results).issubset(raw_completed_urls):
            raise CorruptCheckpoint(
                f"{self._path}'s completed_results has a URL not present in completed_urls"
            )

        return Checkpoint(
            version=version,
            completed_urls=tuple(raw_completed_urls),
            output_ids=raw_output_ids,
            completed_results=raw_completed_results,
        )

    def save(self, checkpoint: Checkpoint) -> None:
        payload = {
            "version": checkpoint.version,
            "completed_urls": list(checkpoint.completed_urls),
            "output_ids": dict(checkpoint.output_ids),
            "completed_results": {
                url: dict(row) for url, row in checkpoint.completed_results.items()
            },
        }
        atomic_write_text(self._path, json.dumps(payload, indent=2), encoding="utf-8")
