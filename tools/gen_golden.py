"""Generate a golden projection from the CURRENT implementation.

A golden records what the code DOES, not what it SHOULD do. It is drift detection, never a
correctness oracle -- where it disagrees with a matrix case, the case wins.

Usage:
    uv run python tools/gen_golden.py v1   # operational projection (before reporting moves)
    uv run python tools/gen_golden.py v2   # shareable projection (after the tiering)
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

_UUID = re.compile(r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}")

# write_outputs reads the wall clock for both timestamps, so they change every run. They are
# replaced with fixed sentinels rather than dropped: their PRESENCE and KEY are part of
# ART-SCHEMA-006's pinned top-level key set.
_FIXED_LOCAL = "GENERATED_AT_LOCAL"
_FIXED_ISO = "GENERATED_AT_ISO"
_TIMESTAMP_KEYS = {"generated_at_local": _FIXED_LOCAL, "generated_at_iso": _FIXED_ISO}


def _normalize(value: object, uuid_map: dict[str, str]) -> object:
    """Replace run-scoped UUIDs with stable ordinals so the golden is comparable.

    The MAPPING is preserved, not discarded: two rows sharing an output_id still share their
    placeholder, which is what makes same-name attendee separation visible in the diff.

    Dict KEYS are normalized too, not just values: `write_email_reports` embeds the per-run
    output UUID directly in email filenames (`attendee_filename_stem`), and the `emails` dict
    built by `build()` below is keyed by exactly those filenames. A version that normalized
    only values would leave those keys holding a fresh random UUID every run, making the
    golden compare unequal to itself on every single invocation.
    """
    if isinstance(value, str):

        def swap(match: re.Match[str]) -> str:
            raw = match.group(0)
            return uuid_map.setdefault(raw.replace("-", ""), f"OUTPUT_ID_{len(uuid_map):02d}")

        return _UUID.sub(swap, value)
    if isinstance(value, dict):
        return {
            _normalize(key, uuid_map): (
                _TIMESTAMP_KEYS[key] if key in _TIMESTAMP_KEYS else _normalize(item, uuid_map)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(item, uuid_map) for item in value]
    return value


def build(kind: str) -> dict[str, object]:
    """Render the fixture through the CURRENT implementation and normalize.

    `kind` LABELS the output; it does not select a projection -- the running implementation
    decides that. Calling build("v1") after Task 23 therefore produces shareable data tagged
    "v1", which is deliberate: the V1 golden comparison must FAIL loudly rather than silently
    regenerate. To make that impossible to trip over by accident, the writer refuses to
    overwrite a golden whose stored `kind` differs from the one requested; use --force to
    re-baseline intentionally.
    """
    import scout_schedule_cli as legacy
    from tests.goldens.fixture import golden_results

    results = golden_results()
    identity = legacy.RunIdentity()
    uuid_map: dict[str, str] = {}

    with tempfile.TemporaryDirectory() as raw_dir:
        out = Path(raw_dir) / "run"
        legacy.write_outputs(
            out, results, generate_html=True, generate_email_report=True, run_identity=identity
        )
        report = (out / "report.html").read_text(encoding="utf-8")
        embedded = json.loads(
            re.search(r'<script id="report-data"[^>]*>(.*?)</script>', report, re.S).group(1)
        )
        emails = {
            path.name: path.read_text(encoding="utf-8-sig")
            for path in sorted((out / "emails").iterdir())
            if path.is_file()
        }

    # Seed the ordinal map in FIXTURE order, not filesystem-encounter order. Email filenames
    # for two same-named attendees differ only by their random per-run UUID suffix, so
    # `sorted((out / "emails").iterdir())` sorts them by that UUID -- a coin flip every run.
    # Letting `_normalize` assign ordinals by first regex-match in that filesystem order would
    # make OUTPUT_ID_00 vs OUTPUT_ID_01 non-deterministic for exactly the same-name case this
    # golden exists to pin down. `identity.output_id` is idempotent (RunIdentity caches per
    # attendee_id), so replaying it here returns the SAME uuid write_outputs already assigned.
    for result in results:
        attendee_id = (result.attendee_id or "").strip()
        if not attendee_id:
            continue  # pre-identity failure: never had an output id to seed
        output_id = identity.output_id(legacy.AttendeeId.parse(attendee_id, result.name))
        uuid_map.setdefault(output_id.replace("-", ""), f"OUTPUT_ID_{len(uuid_map):02d}")

    return {
        "kind": kind,
        "report_data": _normalize(embedded, uuid_map),
        "emails": _normalize(emails, uuid_map),
    }


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else "v1"
    target = (
        REPO_ROOT
        / "tests"
        / "goldens"
        / f"{kind}_{'operational' if kind == 'v1' else 'shareable'}.json"
    )
    payload = json.dumps(build(kind), indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    if target.exists():
        stored = json.loads(target.read_text(encoding="utf-8"))
        if stored["kind"] != kind and "--force" not in sys.argv:
            print(
                f"refusing to overwrite {target.name}: it holds kind={stored['kind']!r} and the "
                f"running implementation now produces kind={kind!r}. V1 is a fixed reference "
                "point for the V1->V2 diff; pass --force only to deliberately re-baseline."
            )
            return 1
        if target.read_text(encoding="utf-8") == payload:
            print(f"{target.name}: unchanged")
            return 0

    target.write_text(payload, encoding="utf-8")
    print(f"{target.name}: written — REVIEW THE DIFF before committing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
