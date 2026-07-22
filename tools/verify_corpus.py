"""Reproduce the design spec's corpus counts. Aggregate output only — never PII."""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Any


def number_shape(value: str) -> str:
    shaped = re.sub(r"[A-Z]", "A", str(value))
    shaped = re.sub(r"[a-z]", "a", shaped)
    return re.sub(r"[0-9]+", "N", shaped)


def summarize_run(run_dir: Path) -> dict[str, Any]:
    raw = run_dir / "raw"
    payloads = sorted(raw.glob("*.json")) if raw.is_dir() else []
    requirements = 0
    flags: collections.Counter[str] = collections.Counter()
    shapes: collections.Counter[str] = collections.Counter()
    for p in payloads:
        try:
            data = json.loads(p.read_text(encoding="utf-8")).get("data") or []
        except (OSError, json.JSONDecodeError):
            continue
        for row in data:
            if not isinstance(row, dict):
                continue
            requirements += 1
            flags[str((row.get("COMPLETED_REQ_FLAG"), row.get("COMPLETED_CLASS_FLAG")))] += 1
            shapes[number_shape(row.get("REQ_NBR_WEB_DISPLAY") or "")] += 1
    return {
        "raw_payloads": len(payloads),
        "requirements": requirements,
        "flag_combos": dict(flags),
        "number_shapes": dict(shapes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args(argv)
    if not args.corpus.is_dir():
        print(f"corpus not found: {args.corpus}", file=sys.stderr)
        return 2
    for run in sorted(p for p in args.corpus.iterdir() if p.is_dir()):
        s = summarize_run(run)
        print(f"{run.name}: {s['requirements']} requirements, {s['raw_payloads']} payloads")
        for combo, n in sorted(s["flag_combos"].items()):
            print(f"    flags {combo}: {n}")  # the 5 (REQ, CLASS) combinations
        for shape, n in sorted(s["number_shapes"].items(), key=lambda kv: -kv[1]):
            print(f"    shape {shape!r}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
