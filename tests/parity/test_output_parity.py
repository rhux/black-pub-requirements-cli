"""Byte-for-byte: the six output files must be identical before and after the move."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from tests.goldens.fixture import golden_results

# Matches a UUIDv4 with OR without its canonical dashes: email filenames embed the dashless
# 32-hex form (attendee_filename_stem strips dashes), but report.html's embedded output_id
# (Task 23) is the dashed str(uuid.uuid4()) form -- both must normalize to the same ordinal or
# report.html's random per-run UUIDs would make this comparison spuriously fail on every run.
_UUID32 = re.compile(r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}")
# Match ONLY the two timestamp grammars write_outputs emits:
#   local: "2026-07-24 09:00:00 UTC"   (time.strftime("%Y-%m-%d %H:%M:%S %Z"))
#   iso:   "2026-07-24T09:00:00+00:00" (datetime.isoformat(timespec="seconds"))
# An open-ended tail like [^"<]* would swallow whatever text follows a timestamp and could
# mask a real regression sitting right after it.
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}"
    r"(?:T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z)"  # ISO with offset
    r"| \d{2}:\d{2}:\d{2}(?: [A-Z]{2,5})?)"  # local with optional tz abbrev
)


def _mask_timestamps(text: str) -> str:
    return _TIMESTAMP.sub("TIMESTAMP", text)


def _mask_uuids(text: str) -> str:
    """Map each distinct UUID encountered (dashed or dashless) to a stable ordinal, using a
    mapping local to this one call. report.html now embeds output_id (Task 23) -- a fresh
    random UUID every run -- so a raw comparison would fail even when nothing meaningful
    changed."""
    mapping: dict[str, str] = {}
    return _UUID32.sub(lambda m: mapping.setdefault(m.group(0), f"UUID{len(mapping):02d}"), text)


def _normalized_tree(root: Path) -> dict[str, str]:
    """Relative paths and content digests, with per-run UUIDs mapped to stable ordinals.

    Filenames embed the run UUID, so a raw digest map can never be equal between two runs;
    normalizing makes the comparison meaningful instead of vacuous.

    Two attendees sharing a display name (the golden fixture's "Jordan Sample" pair) produce
    email filenames that differ ONLY in their random per-run UUID. Sorting by the raw path
    before assigning ordinals would order them by the lexical value of that UUID -- pure
    chance, independent between the two runs being compared, so an earlier version of this
    helper picked up a spurious ~50% failure rate confirmed empirically (content matched
    correctly when paired by real attendee_id; only the ordinal LABELING disagreed). Content
    digest is used as the tie-breaker instead: it depends on attendee DATA, not the random
    UUID, so for the same fixture it orders identically in both trees.
    """
    mapping: dict[str, str] = {}

    def normalize(value: str) -> str:
        return _UUID32.sub(
            lambda m: mapping.setdefault(m.group(0), f"UUID{len(mapping):02d}"), value
        )

    entries: list[tuple[str, str, Path]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root))
        body = _mask_timestamps(path.read_text(encoding="utf-8-sig", errors="replace"))
        digest = hashlib.sha256(body.encode()).hexdigest()
        entries.append((_UUID32.sub("\0", rel), digest, path))
    entries.sort(key=lambda entry: (entry[0], entry[1]))

    tree: dict[str, str] = {}
    for _, _, path in entries:
        rel = str(path.relative_to(root))
        body = _mask_timestamps(path.read_text(encoding="utf-8-sig", errors="replace"))
        tree[normalize(rel)] = hashlib.sha256(normalize(body).encode()).hexdigest()
    return tree


def test_write_outputs_is_byte_identical_through_the_service(tmp_path: Path) -> None:
    import scout_schedule_cli as legacy

    from scoutmb.interfaces.cli.composition import build_reporting_service

    fixed_local, fixed_iso = "2026-07-24 09:00:00 UTC", "2026-07-24T09:00:00+00:00"

    # Both output dirs share the basename "output": write_outputs/publish set report.html's
    # embedded run_id to output_dir.name, so a "direct" vs "via" basename would leak into the
    # JSON payload as a real (if harmless) difference unrelated to the move being tested.
    direct = tmp_path / "direct_root" / "output"
    identity_a = legacy.RunIdentity()
    legacy.write_outputs(
        direct, golden_results(), generate_email_report=True, run_identity=identity_a
    )

    via = tmp_path / "via_root" / "output"
    identity_b = legacy.RunIdentity()
    build_reporting_service().publish(
        via,
        golden_results(),
        generate_email_report=True,
        run_identity=identity_b,
        generated_at_local=fixed_local,
        generated_at_iso=fixed_iso,
    )

    # Deterministic files: byte-for-byte.
    for name in ("classes.csv", "requirements.csv", "errors.csv", "scouts.json"):
        assert (direct / name).read_bytes() == (via / name).read_bytes(), name

    # UUID-bearing paths: compare the normalized tree shape, and the CONTENT of each email
    # after mapping its per-run UUID to a positional placeholder. `or True` on a set
    # comparison, which an earlier draft used here, asserts nothing at all.
    assert _normalized_tree(direct) == _normalized_tree(via)

    # report.html embeds the two wall-clock timestamps and (Task 23) each attendee's output_id;
    # mask both before comparing.
    assert _mask_uuids(
        _mask_timestamps((direct / "report.html").read_text(encoding="utf-8"))
    ) == _mask_uuids(_mask_timestamps((via / "report.html").read_text(encoding="utf-8")))
