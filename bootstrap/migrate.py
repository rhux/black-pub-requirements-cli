"""One-time COPY of legacy app/ user data into data/. Never moves or deletes.

One install exists with a season of real records. If this migration is wrong, the
data must still be where it always was. Every copied file is verified by SHA-256, not
just size — the data is irreplaceable, and hashing it is cheap. Staging, resumability,
and the marker-ordering contract are Slice 3 hardening; Slice 1 copies + hash-verifies.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

MIGRATION_MARKER = ".migrated"
_ITEMS = [("scouts.csv", False), ("pdf-uploads", True), ("runs", True)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_tree(src: Path, dst: Path) -> None:
    """Every file under src has a byte-identical (SHA-256) twin under dst."""
    src_files = sorted(p for p in src.rglob("*") if p.is_file())
    for src_file in src_files:
        dst_file = dst / src_file.relative_to(src)
        if not dst_file.is_file() or _sha256(src_file) != _sha256(dst_file):
            raise RuntimeError(f"migration hash verify failed for {src_file.relative_to(src)}")


def migrate_legacy_data(app_dir: Path, data_dir: Path) -> dict[str, object] | None:
    if (data_dir / MIGRATION_MARKER).is_file() or not app_dir.is_dir():
        return None
    present = [(n, d) for n, d in _ITEMS if (app_dir / n).exists()]
    if not present:
        return None
    data_dir.mkdir(parents=True, exist_ok=True)
    copied, collisions = [], []
    for name, is_dir in present:
        src = app_dir / name
        dst = data_dir / name
        if dst.exists():
            # Preserve every prior copy — NEVER delete an existing .legacy. Pick the first
            # free .legacy / .legacy-2 / .legacy-3 ... name instead.
            collisions.append(name)
            candidate = data_dir / f"{name}.legacy"
            suffix = 1
            while candidate.exists():
                suffix += 1
                candidate = data_dir / f"{name}.legacy-{suffix}"
            dst = candidate
        if is_dir:
            shutil.copytree(src, dst)
            _verify_tree(src, dst)
        else:
            shutil.copy2(src, dst)
            if _sha256(src) != _sha256(dst):
                raise RuntimeError(f"migration hash verify failed for {name}")
        copied.append(dst.name)
    # Write the old-root explanatory marker BEFORE the .migrated completion marker. If the
    # README write failed after .migrated existed, every rerun would return early (marker
    # present) and the old root would never get its notice. Completion marker is always last.
    (app_dir / "MOVED-README.txt").write_text(
        "This folder's data was copied to the app's data directory. Originals are "
        "retained here but no longer used. Do not run the old app from here.\n",
        encoding="utf-8",
    )
    report = {
        "migrated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(app_dir),
        "copied": copied,
        "collisions": collisions,
        "verification": "sha256",
        "originals_retained": True,
    }
    (data_dir / MIGRATION_MARKER).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
