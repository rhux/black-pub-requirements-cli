"""An explicit file list silently stops covering new modules. This is the tripwire."""

from __future__ import annotations

from pathlib import Path

from tests.matrix.boundaries import COVERAGE_AREAS

SRC = Path(__file__).resolve().parents[2] / "src"
_PREFIXES = ("core", "ports", "adapters", "features")


def test_every_package_module_belongs_to_a_coverage_area() -> None:
    # Only the pkg-* areas cover src/scoutmb/{core,ports,adapters,features}; COVERAGE_AREAS also
    # holds the legacy flat-module areas (schedule, pdf, ui, desktop, bootstrap), whose files
    # (scout_schedule_cli.py, ui/server.py, ...) live outside src/ entirely and would make a
    # blanket "every declared file is on disk under src/" comparison fail on files that were
    # never meant to be there.
    declared = {
        name for area in COVERAGE_AREAS if area.area_id.startswith("pkg-") for name in area.files
    }
    on_disk = {
        str(path.relative_to(SRC.parent))
        for prefix in _PREFIXES
        for path in (SRC / "scoutmb" / prefix).rglob("*.py")
        if path.name != "__init__.py"
    }
    assert on_disk - declared == set(), sorted(on_disk - declared)
    assert declared - on_disk == set(), sorted(declared - on_disk)
