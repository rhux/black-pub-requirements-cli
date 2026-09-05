"""License-policy enforcement against a permissive allowlist (D6).

uv.lock records only each package's name/version -- never a license field (confirmed
empirically: zero `license` keys anywhere in the lock file, not merely a different key path
than expected). Local installed-package metadata (importlib.metadata) is not a reliable
fallback either: under half of this project's real dependencies carry any license info there,
and the one that does can return the entire license TEXT rather than a short identifier.

License identity is instead resolved via PyPI's JSON API per (name, version), in this order:
  1. `license_expression` -- PEP 639's SPDX-based field, most reliable when present.
  2. `license` -- used only when it looks like a short identifier, not a pasted license body.
  3. `classifiers` -- mapped through a small, explicit table (ambiguous ones, like the generic
     "BSD License" classifier which doesn't distinguish 2- vs 3-clause, are deliberately NOT
     mapped -- they fall through to unresolved rather than guessing).

A package no source resolves, and that isn't listed in the policy file's [overrides] table
(hand-maintained, for real humans to add a checked entry to), is a REJECTION requiring manual
review -- never a silent pass. Styled after tools/check_private_data.py's argparse + exit-code
convention.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import urllib.request
from pathlib import Path

_CLASSIFIER_TO_SPDX = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    # Deliberately NOT mapped: "License :: OSI Approved :: BSD License" is ambiguous between
    # BSD-2-Clause and BSD-3-Clause -- falls through to unresolved rather than guessing.
}

# Non-SPDX strings some packages self-report in the plain `license` field, normalized to the
# SPDX identifier they actually mean -- distinct from _CLASSIFIER_TO_SPDX's ambiguous cases
# (there is no generic un-normalizable "BSD License" plain-string form observed here).
_LICENSE_STRING_ALIASES = {
    "apache 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "mit license": "MIT",
}

_SHORT_LICENSE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-+ ]{0,39}$")
_REQUEST_TIMEOUT_SECONDS = 10

# scoutmb is this project's own package, not a third-party dependency -- never look it up on
# PyPI (it isn't published there), and its license is pyproject.toml's own [project].license.
_SELF_PACKAGE_NAME = "scoutmb"


def load_lock_packages(lock_path: Path) -> list[tuple[str, str]]:
    data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    return [
        (pkg["name"], pkg["version"])
        for pkg in data.get("package", [])
        if pkg["name"] != _SELF_PACKAGE_NAME
    ]


def _is_allowed(license_id: str, allowed: set[str]) -> bool:
    """Evaluates a (possibly compound) SPDX expression against the allowlist: every component
    of an AND-expression must be allowed (all its terms apply simultaneously); any one component
    of an OR-expression suffices (the recipient may choose which license to comply under). Real
    data here never mixes AND and OR in one expression without parentheses, so this flat split
    is sufficient -- it does not attempt to be a general SPDX expression parser."""
    if " OR " in license_id:
        return any(_is_allowed(part.strip(), allowed) for part in license_id.split(" OR "))
    if " AND " in license_id:
        return all(_is_allowed(part.strip(), allowed) for part in license_id.split(" AND "))
    return license_id in allowed


def resolve_license(name: str, version: str) -> str | None:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    request = urllib.request.Request(url, headers={"User-Agent": "scoutmb-license-check"})
    with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
        info = json.load(response)["info"]

    license_expression = info.get("license_expression")
    if license_expression:
        return str(license_expression)

    license_field = (info.get("license") or "").strip()
    if license_field:
        aliased = _LICENSE_STRING_ALIASES.get(license_field.lower())
        if aliased:
            return aliased
        if _SHORT_LICENSE_RE.match(license_field):
            return license_field

    for classifier in info.get("classifiers", []):
        mapped = _CLASSIFIER_TO_SPDX.get(classifier)
        if mapped:
            return mapped

    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    args = parser.parse_args(argv)

    policy = tomllib.loads(args.policy.read_text(encoding="utf-8"))
    allowed = set(policy["allowed"])
    overrides: dict[str, str] = policy.get("overrides", {})
    # [exceptions]: named, reviewed, DOCUMENTED policy violations -- distinct from [overrides]
    # (which only supplies a license identity for automation that can't resolve one; the
    # resulting identity still has to pass the allowlist). An exception is explicitly granted
    # despite failing the allowlist, and stays visibly printed on every run, never silent.
    exceptions: dict[str, str] = policy.get("exceptions", {})

    packages = load_lock_packages(args.lock)
    violations: dict[str, str] = {}
    unresolved: list[str] = []
    granted_exceptions: dict[str, str] = {}

    for name, version in packages:
        if name in exceptions:
            granted_exceptions[f"{name}=={version}"] = exceptions[name]
            continue

        license_id = overrides.get(name)
        if license_id is None:
            try:
                license_id = resolve_license(name, version)
            except Exception as exc:  # noqa: BLE001 - a lookup failure is a finding, not a crash
                unresolved.append(f"{name}=={version}: lookup failed ({exc})")
                continue

        if license_id is None:
            unresolved.append(
                f"{name}=={version}: no resolvable license "
                f"(add a checked entry to [overrides] in {args.policy})"
            )
        elif not _is_allowed(license_id, allowed):
            violations[f"{name}=={version}"] = license_id

    for key, license_id in sorted(granted_exceptions.items()):
        print(f"GRANTED EXCEPTION: {key} ({license_id}) -- see {args.policy}'s [exceptions] comment")

    if violations or unresolved:
        for key, license_id in sorted(violations.items()):
            print(f"disallowed license: {key} ({license_id})")
        for entry in sorted(unresolved):
            print(f"unresolved license: {entry}")
        return 1

    print(
        f"{len(packages)} package license(s) checked, all allowed "
        f"({len(granted_exceptions)} under a granted exception)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
