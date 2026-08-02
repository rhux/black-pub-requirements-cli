"""Digest over every preserve-case expected observation.

The oracle invariant says a move may never edit an expected value. Visible-in-review is not
enforced; this is. On failure it names the changed case IDs rather than just failing.

Usage:
    uv run python tools/check_case_digest.py --check
    uv run python tools/check_case_digest.py --update
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DIGEST_PATH = REPO_ROOT / "tests" / "baselines" / "preserve_cases.json"

if TYPE_CHECKING:
    from tests.matrix.model import CaseMetadata


class _PreserveCase(Protocol):
    """Structural type for the four domain case dataclasses (InputCase, PdfCase,
    RequirementCase, ArtifactCase). Each carries a ``meta: CaseMetadata`` field, but there is
    no shared base class to import at runtime without pulling the per-domain modules in early --
    a Protocol gives ``case.meta`` a real type without changing the deferred-import structure
    below (the domain modules are only imported inside ``_case_tuples`` itself).

    ``meta`` is declared as a read-only property, not a plain attribute: all four dataclasses
    are ``frozen=True``, so their ``meta`` field is a read-only attribute, and a plain
    ``meta: CaseMetadata`` Protocol member declares a *settable* variable -- mypy then rejects
    every one of them with "expected settable variable, got read-only attribute"."""

    @property
    def meta(self) -> CaseMetadata: ...


# tests.matrix.cases.ALL_CASES is CaseMetadata ONLY -- it carries no expectations, so hashing
# it would digest None for all 478 rows and never detect anything. The per-domain tuples hold
# the real data, and the expectation FIELD NAME differs by domain (input uses expected_legacy,
# requirement uses expected_by_context), so the provider is explicit rather than duck-typed.
_EXPECTATION_FIELDS = ("expected_by_context", "expected_legacy", "expected")


def _case_tuples() -> list[tuple[str, tuple[_PreserveCase, ...]]]:
    from tests.matrix.cases.artifact_cases import ARTIFACT_CASES
    from tests.matrix.cases.input_cases import INPUT_CASES
    from tests.matrix.cases.pdf_cases import PDF_CASES
    from tests.matrix.cases.requirement_cases import REQUIREMENT_CASES

    return [
        ("input", INPUT_CASES),
        ("pdf", PDF_CASES),
        ("requirement", REQUIREMENT_CASES),
        ("artifact", ARTIFACT_CASES),
    ]


def _canonicalize(value: object) -> object:
    """Recursively convert to a JSON-safe, order-stable structure.

    NOT repr(). `repr(frozenset)` iterates in hash order, and string hashing is randomized per
    process (PEP 456), so a repr-based digest changes between CI runs and reports oracle drift
    that did not happen. Verified: three interpreters printed three different orderings for the
    same frozenset. Sets are sorted, mappings are key-sorted, dataclasses become dicts, and
    tuples and lists are distinguished by a tag so a shape change is still detected.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "__dc__": type(value).__name__,
            **{f.name: _canonicalize(getattr(value, f.name)) for f in dataclasses.fields(value)},
        }
    if isinstance(value, Mapping):
        # Sorts by the RAW key's repr, not _canonicalize(k)'s -- fine while every case
        # dataclass's Mapping-typed fields (none exist today) key on plain str/int, but a
        # future dataclass or dict key would reintroduce the same hash-order instability
        # this function exists to eliminate. Sort by repr(_canonicalize(k)) instead if that
        # ever happens.
        return {
            "__map__": [
                [_canonicalize(k), _canonicalize(v)]
                for k, v in sorted(value.items(), key=lambda kv: repr(kv[0]))
            ]
        }
    if isinstance(value, (set, frozenset)):
        return {"__set__": sorted((_canonicalize(v) for v in value), key=repr)}
    if isinstance(value, tuple):
        return {"__tuple__": [_canonicalize(v) for v in value]}
    if isinstance(value, list):
        return [_canonicalize(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return {"__repr__": repr(value)}


def _canonical(case: object) -> str:
    payload = {
        field: _canonicalize(getattr(case, field))
        for field in sorted(_EXPECTATION_FIELDS)
        if hasattr(case, field)
    }
    if not payload:
        raise RuntimeError(f"no expectation field on {type(case).__name__}; update the provider")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute() -> dict[str, str]:
    from tests.matrix.model import Classification

    digests: dict[str, str] = {}
    for domain, cases in _case_tuples():
        for case in cases:
            if case.meta.classification is not Classification.PRESERVE:
                continue
            payload = f"{domain}:{_canonical(case)}"
            digests[case.meta.case_id] = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    if not digests:
        raise RuntimeError("digest covered zero cases -- the provider is broken, not the catalog")
    return digests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true")
    parser.add_argument(
        "--print",
        dest="show",
        action="store_true",
        help="write the computed digests to stdout and exit",
    )
    args = parser.parse_args()

    current = compute()

    if args.show:
        print(json.dumps(current, indent=2, sort_keys=True))
        return 0

    if args.update or not DIGEST_PATH.exists():
        DIGEST_PATH.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {len(current)} preserve-case digests")
        return 0

    stored = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))
    changed = sorted(k for k in current.keys() & stored.keys() if current[k] != stored[k])
    added = sorted(current.keys() - stored.keys())
    removed = sorted(stored.keys() - current.keys())

    if changed:
        print("CHANGED preserve-case expectations (the oracle invariant forbids this in a move):")
        for case_id in changed:
            print(f"  {case_id}")
    if added:
        print(f"ADDED cases (bump the baseline deliberately): {', '.join(added)}")
    if removed:
        print(f"REMOVED cases: {', '.join(removed)}")
    return 1 if (changed or added or removed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
