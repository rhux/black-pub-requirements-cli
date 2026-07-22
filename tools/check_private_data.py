"""Fail closed if committed content looks like real Scout data.

Two layers:
  * patterns  — run everywhere (CI included): live scoutingevent QR tokens.
  * corpus    — run where the private raw_data corpus is present: cross-reference
                every real name, attendee ID, and surname fragment against scanned
                file contents AND filenames, longest-first.

Findings report the offending file and a reason ONLY — never the matched value — so
the scanner itself cannot leak what it found.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

LIVE_TOKEN = re.compile(r"scoutingevent\.com/mobile/[^\s\"'<>]*?[?&]t=([A-Za-z0-9_-]+)")


def _iter_files(roots: list[Path]):
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                yield path


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def scan_patterns(roots: list[Path]) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    for path in _iter_files(roots):
        text = _read(path)
        if text is None:
            continue
        for token in LIVE_TOKEN.findall(text):
            if not token.startswith("TESTTOKEN"):
                findings.append((str(path), "live-qr-token"))
    return findings


def load_corpus_identifiers(corpus_dir: Path) -> tuple[set[str], set[str]]:
    """Real names + attendee IDs from a private corpus's classes.csv files (local only)."""
    names: set[str] = set()
    ids: set[str] = set()
    for classes in corpus_dir.glob("*/classes.csv"):
        with classes.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("scout_name"):
                    names.add(row["scout_name"].strip())
                if row.get("attendee_id"):
                    ids.add(row["attendee_id"].strip())
    return names, ids


def _redact(path: Path, values: list[str]) -> str:
    """Report a path with any matched sensitive value masked — a filename can itself BE the
    leak, so the finding must not echo it. Also hashes the parent dir name if it matches."""
    reported = str(path)
    for value in values:
        if value and value in reported:
            reported = reported.replace(value, "***")
    return reported


def scan_corpus(roots: list[Path], names: set[str], ids: set[str]) -> list[tuple[str, str]]:
    # Full values (longest first, so a substring name never masks its superstring) plus
    # surname-level fragments matched on a word boundary.
    exact = sorted((v for v in (names | ids) if v), key=len, reverse=True)
    fragments = {p for n in names for p in n.split() if len(p) > 3}
    frag_res = {p: re.compile(rf"\b{re.escape(p)}\b") for p in fragments}

    findings: list[tuple[str, str]] = []
    for path in _iter_files(roots):
        blob = str(path)  # filenames leak too
        text = _read(path)
        if text is not None:
            blob += "\n" + text
        if any(value in blob for value in exact):
            findings.append((_redact(path, exact), "corpus-exact"))  # never echo the value
            continue
        matched_frags = [p for p, rx in frag_res.items() if rx.search(blob)]
        if matched_frags:
            findings.append((_redact(path, matched_frags), "corpus-fragment"))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=None,
        help="Private corpus dir; enables real-value cross-reference when present.",
    )
    args = parser.parse_args(argv)

    findings = scan_patterns(args.roots)
    if args.corpus and args.corpus.is_dir():
        names, ids = load_corpus_identifiers(args.corpus)
        findings += scan_corpus(args.roots, names, ids)

    print(f"private-data findings: {len(findings)}")
    for path, reason in findings:
        print(f"  {path}: {reason}")  # reason only, never the matched value
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
