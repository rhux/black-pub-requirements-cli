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
            raw = match.group(0).replace("-", "")
            try:
                return uuid_map[raw]
            except KeyError:
                # Every UUID this golden should ever see comes from the single RunIdentity
                # `build()` constructs, and the fixture-order pre-seed loop below populates
                # `uuid_map` with all of them BEFORE this function ever runs. Falling through
                # here means some OTHER source produced a UUID-shaped value -- e.g. a second
                # RunIdentity accidentally constructed somewhere (the exact bug Task 7 fixed).
                # `setdefault`-ing a fresh ordinal in that case would silently assign it by
                # first-regex-match order, reintroducing the coin-flip nondeterminism the
                # fixture-order seeding exists to eliminate, just for a rarer trigger. Fail
                # loudly and immediately instead.
                raise AssertionError(
                    f"unseeded UUID {raw!r} encountered while normalizing the golden. All "
                    "UUIDs must be pre-seeded from fixture order before _normalize runs; an "
                    "unseeded UUID means an unexpected source produced it."
                ) from None

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


def _content_shape(report_data: dict[str, object]) -> str | None:
    """Fingerprint the row shape ACTUALLY PRESENT in report_data, independent of any label.

    `kind` is just a string the caller passed to `build()` -- it is echoed back, never derived
    from the content, so comparing a stored file's `kind` against the requested `kind` can
    never catch a real mismatch (both sides trace back to the same CLI argument). This looks
    at the one thing the V1->V2 substitution actually changes: whether a scouts row carries
    `attendee_id` (V1, pre-Task 23) or `output_id` (V2, post-Task 23). Returns None when there
    is no row to inspect -- callers must not treat that as a mismatch.
    """
    scouts = report_data.get("scouts") or []
    if not isinstance(scouts, list) or not scouts:
        return None
    first = scouts[0]
    if not isinstance(first, dict):
        return None
    if "output_id" in first:
        return "v2"
    if "attendee_id" in first:
        return "v1"
    return None


def build(kind: str) -> dict[str, object]:
    """Render the fixture through the CURRENT implementation and normalize.

    `kind` LABELS the output; it does not select a projection -- the running implementation
    decides that. Calling build("v1") after Task 23 therefore produces shareable data tagged
    "v1", which is deliberate: the V1 golden comparison must FAIL loudly rather than silently
    regenerate. To make that impossible to trip over by accident, the writer compares an
    actual content fingerprint (`_content_shape`: does the first scouts row carry
    `attendee_id` or `output_id`?) of the freshly-built payload against the stored file's
    fingerprint, refusing to overwrite when they disagree -- NOT the self-reported `kind`
    label, which is always self-consistent and so can never catch a real reshape. Use --force
    to re-baseline intentionally.
    """
    import scout_schedule_cli as legacy
    from tests.goldens.fixture import golden_results

    results = golden_results()
    identity = legacy.RunIdentity()
    uuid_map: dict[str, str] = {}

    with tempfile.TemporaryDirectory() as raw_dir:
        out = Path(raw_dir) / "run"
        legacy.write_outputs(
            out,
            results,  # type: ignore[arg-type]  # ScoutResult twin types are duck-type
            # compatible; real alias deferred to Slice 2b (see class ScoutResult comment in
            # scout_schedule_cli.py)
            generate_html=True,
            generate_email_report=True,
            run_identity=identity,
        )
        report = (out / "report.html").read_text(encoding="utf-8")
        match = re.search(r'<script id="report-data"[^>]*>(.*?)</script>', report, re.S)
        if match is None:
            raise AssertionError(
                'report.html missing the embedded <script id="report-data"> block; '
                "write_outputs's HTML template may have changed."
            )
        embedded = json.loads(match.group(1))
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

    # `emails` is a gen_golden-only construct (write_outputs has no equivalent single dict to
    # preserve the "true build order" of), and its raw insertion order above is
    # filesystem-sorted by the UNNORMALIZED, per-run-random UUID filename -- so, unlike
    # report_data, that raw order is itself nondeterministic across runs. Previously
    # sort_keys=True on the final json.dump masked this; now that the dump preserves real dict
    # order (for report_data's benefit), `emails` needs an explicit, order-stable sort of its
    # own -- done here, AFTER normalization, so it sorts on the deterministic OUTPUT_ID_NN
    # placeholder rather than the random raw UUID.
    normalized_emails = _normalize(emails, uuid_map)
    assert isinstance(normalized_emails, dict)

    return {
        "kind": kind,
        "report_data": _normalize(embedded, uuid_map),
        "emails": dict(sorted(normalized_emails.items())),
    }


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else "v1"
    target = (
        REPO_ROOT
        / "tests"
        / "goldens"
        / f"{kind}_{'operational' if kind == 'v1' else 'shareable'}.json"
    )
    built = build(kind)
    # No sort_keys: the stored JSON must reflect TRUE build-time key order (dict insertion
    # order from write_outputs's dict construction), not an alphabetized re-canonicalization.
    # A key-order regression should show up as a diff; alphabetizing on every write would
    # erase it, and Task 23's positional key-order assertion depends on the real order too.
    payload = json.dumps(built, indent=2, ensure_ascii=False) + "\n"

    if target.exists():
        stored = json.loads(target.read_text(encoding="utf-8"))
        stored_shape = _content_shape(stored.get("report_data", {}))
        built_report_data = built["report_data"]
        built_shape = (
            _content_shape(built_report_data) if isinstance(built_report_data, dict) else None
        )
        if (
            stored_shape is not None
            and built_shape is not None
            and stored_shape != built_shape
            and "--force" not in sys.argv
        ):
            print(
                f"refusing to overwrite {target.name}: its rows are shaped like {stored_shape!r} "
                f"(attendee_id/output_id), but the running implementation now produces "
                f"{built_shape!r}-shaped rows. V1 is a fixed reference point for the V1->V2 "
                "diff; pass --force only to deliberately re-baseline."
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
