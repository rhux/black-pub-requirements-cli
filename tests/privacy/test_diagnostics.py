from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY = REPO_ROOT / "src" / "scoutmb" / "adapters" / "scoutevent" / "playwright_gateway.py"


def test_the_three_intentional_swallows_are_documented_inline():
    """D5: the three intentional selector-probe/route-interception swallows in
    playwright_gateway.py stay silent by design, but must each carry a one-line comment
    explaining why -- a future edit silently dropping that comment is what this guards
    against, not the swallow behavior itself (already covered by
    tests/unit/scoutevent/test_playwright_gateway.py)."""
    lines = GATEWAY.read_text(encoding="utf-8").splitlines()
    swallow_line_numbers = [
        i for i, line in enumerate(lines) if line.strip() == "except Exception:"
    ]
    assert len(swallow_line_numbers) == 3, (
        f"expected exactly the three known intentional swallows, found {len(swallow_line_numbers)}"
    )
    for line_number in swallow_line_numbers:
        next_line = lines[line_number + 1]
        assert "#" in next_line, f"line {line_number + 2} has no explanatory comment: {next_line!r}"


def test_noop_observability_is_the_only_shipped_implementation():
    obs_dir = REPO_ROOT / "src" / "scoutmb" / "adapters" / "observability"
    implementations = sorted(p.name for p in obs_dir.glob("*.py") if p.name != "__init__.py")
    assert implementations == ["noop.py"]


def test_ports_and_adapters_never_import_opentelemetry_by_name():
    for layer in ("ports", "features", "core"):
        for path in (REPO_ROOT / "src" / "scoutmb" / layer).rglob("*.py"):
            assert "opentelemetry" not in path.read_text(encoding="utf-8"), (
                f"{path} references opentelemetry -- forbidden in this layer"
            )
