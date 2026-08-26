"""One-time COPY of legacy app/ user data into data/. Never moves or deletes.

One install exists with a season of real records. If this migration is wrong, the data must
still be where it always was. Staging happens in a SIBLING directory of data_dir (never inside
app_dir, which may be on a different filesystem/volume than data_dir on some installs) so the
final promotion is always same-filesystem os.replace/Path.rename -- atomic, never a partial
write visible at the destination. Each item is staged, hash-verified, then individually
promoted; a rerun after interruption skips items already promoted and recopies-from-scratch any
item that was staged but not yet promoted, since a partial stage is never trusted."""

from __future__ import annotations

import hashlib
import json
import os
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
    src_files = sorted(p for p in src.rglob("*") if p.is_file())
    for src_file in src_files:
        dst_file = dst / src_file.relative_to(src)
        if not dst_file.is_file() or _sha256(src_file) != _sha256(dst_file):
            raise RuntimeError(f"migration hash verify failed for {src_file.relative_to(src)}")


def _stage_item(src: Path, staging: Path, name: str, is_dir: bool) -> Path:
    """Copies src into staging/name from scratch every time -- a partial stage from an earlier
    interrupted run is never reused, only overwritten, since a partial copy cannot be trusted."""
    staged_path = staging / name
    if staged_path.exists():
        shutil.rmtree(staged_path) if staged_path.is_dir() else staged_path.unlink()
    if is_dir:
        shutil.copytree(src, staged_path)
        _verify_tree(src, staged_path)
    else:
        shutil.copy2(src, staged_path)
        if _sha256(src) != _sha256(staged_path):
            raise RuntimeError(f"migration hash verify failed for {name}")
    return staged_path


def _promote_staged_item(staged_path: Path, data_dir: Path, name: str) -> str:
    """Renames staged_path into data_dir (same filesystem, per the sibling-staging contract) --
    a real collision (already-promoted data with the same name) gets a deterministic
    .legacy/.legacy-N sibling name, never an overwrite."""
    dst = data_dir / name
    if dst.exists():
        candidate = data_dir / f"{name}.legacy"
        suffix = 1
        while candidate.exists():
            suffix += 1
            candidate = data_dir / f"{name}.legacy-{suffix}"
        dst = candidate
    if staged_path.is_file():
        os.replace(staged_path, dst)
    else:
        shutil.move(str(staged_path), str(dst))
    return dst.name


def migrate_legacy_data(
    app_dir: Path, data_dir: Path, *, production: bool = False
) -> dict[str, object] | None:
    if production and os.environ.get("SCOUTMB_MIGRATION_BACKUP_CONFIRMED") != "1":
        raise RuntimeError(
            "Production-mode migration requires a manual backup of the existing app data "
            "before it runs. Back up the app folder, then set "
            "SCOUTMB_MIGRATION_BACKUP_CONFIRMED=1 and retry."
        )
    if (data_dir / MIGRATION_MARKER).is_file() or not app_dir.is_dir():
        return None
    present = [(n, d) for n, d in _ITEMS if (app_dir / n).exists()]
    if not present:
        return None

    data_dir.mkdir(parents=True, exist_ok=True)
    staging = data_dir.parent / f".{data_dir.name}.staging"
    staging.mkdir(parents=True, exist_ok=True)

    # Resumability is tracked by a per-item marker INSIDE staging, never by checking whether
    # data_dir/name already exists -- a genuine naming collision with unrelated pre-existing
    # data at that path would look identical to "already promoted by a prior interrupted
    # attempt", and the two must never be conflated (a real collision still needs its own
    # staging+promote+.legacy pass; only a marker proves this exact migration already did it).
    copied, collisions = [], []
    for name, is_dir in present:
        marker = staging / f".{name}.promoted"
        if marker.is_file():
            continue  # resumed run: this item was already promoted in a prior attempt
        src = app_dir / name
        staged_path = _stage_item(src, staging, name, is_dir)
        promoted_name = _promote_staged_item(staged_path, data_dir, name)
        marker.write_text("", encoding="utf-8")
        if promoted_name != name:
            collisions.append(name)
        copied.append(promoted_name)

    # Every present item is now promoted (any failure above would have raised out of this
    # function first) -- staging holds nothing but promotion markers at this point, pure
    # migration-run bookkeeping, so the whole scratch directory is discarded.
    shutil.rmtree(staging, ignore_errors=True)

    # Write the old-root explanatory marker BEFORE the .migrated completion marker -- see
    # module docstring precedent in the original Slice 1 version; unchanged here.
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
