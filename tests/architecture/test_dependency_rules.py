"""Executable form of the Phase B spec's 'Dependency rules' and 'No __file__' sections."""

from __future__ import annotations

import ast
import io
import sys
import tokenize
from collections import defaultdict
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[2] / "src" / "scoutmb"

ALLOWED: dict[str, set[str]] = {
    "interfaces": {
        "interfaces",
        "features",
        "core",
        "ports",
        "config",
        "errors",
        "adapters",
        "network_policy",
        "runtime",
    },
    "features": {"features", "core", "ports", "config", "errors"},
    "adapters": {"adapters", "core", "ports", "config", "errors", "network_policy"},
    "runtime": {"runtime", "core", "ports", "config", "errors"},
    "core": {"core", "errors"},
    "ports": {"ports", "core", "errors"},
}

# Fully-qualified call targets, plus the BARE names an aliased import produces:
# `from importlib import import_module` makes the call site read `import_module(...)`, which a
# dotted-name-only list never sees.
BANNED_DYNAMIC = {
    "importlib.import_module",
    "importlib.__import__",
    "import_module",
    "__import__",
    "imp.load_module",
    "exec",
    "eval",
}
DYNAMIC_BANNED_LAYERS = {"core", "ports", "features"}


def _modules() -> list[Path]:
    return sorted(p for p in PKG_ROOT.rglob("*.py"))


def _layer(path: Path) -> str:
    rel = path.relative_to(PKG_ROOT)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def _dotted(path: Path) -> str:
    rel = path.relative_to(PKG_ROOT).with_suffix("")
    parts = [p for p in rel.parts if p != "__init__"]
    return ".".join(["scoutmb", *parts])


def _first_party_imports(tree: ast.AST, *, module: str, is_package: bool) -> set[str]:
    """Absolute AND relative first-party imports.

    Relative imports carry node.level > 0 and node.module is None for `from . import x`, so a
    check that only reads node.module misses every one of them -- which is most of the ways an
    intra-package edge actually gets written.

    `package` must match what Python's import machinery would use as `__package__` when
    resolving the relative import, which for a package's `__init__.py` is the package's OWN
    dotted name (e.g. `scoutmb.core`), not one level up. `_dotted()` already returns that own
    name for `__init__.py` (it strips the `__init__` path segment), so for a package we must NOT
    also strip a trailing component -- doing so would resolve `from .model import T` inside
    `scoutmb/core/__init__.py` to the nonexistent `scoutmb.model` instead of the correct
    `scoutmb.core.model`.
    """
    found: set[str] = set()
    package = module if is_package else module.rsplit(".", 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.startswith("scoutmb"))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                target = f"{base}.{node.module}" if node.module else base
                found.add(target)
                found.update(f"{target}.{a.name}" for a in node.names)
            elif node.module and node.module.startswith("scoutmb"):
                found.add(node.module)
                found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


def _direct_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for path in _modules():
        dotted = _dotted(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        is_package = path.name == "__init__.py"
        graph[dotted] = _first_party_imports(tree, module=dotted, is_package=is_package)
    return graph


def _transitive(graph: dict[str, set[str]], start: str) -> set[str]:
    seen: set[str] = set()
    stack = list(graph.get(start, ()))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(graph.get(current, ()))
    return seen


def _layer_of_dotted(dotted: str) -> str:
    parts = dotted.split(".")
    return parts[1] if len(parts) > 1 else ""


def test_transitive_import_edges_are_allowed() -> None:
    graph = _direct_graph()
    violations: list[str] = []
    for module in graph:
        source_layer = _layer_of_dotted(module)
        permitted = ALLOWED.get(source_layer)
        if permitted is None:
            continue
        for reached in _transitive(graph, module):
            target_layer = _layer_of_dotted(reached)
            if target_layer and target_layer not in permitted:
                violations.append(f"{module} -> {reached} ({source_layer} -> {target_layer})")
    assert violations == [], "\n".join(sorted(violations))


def test_adapter_imports_confined_to_composition_roots() -> None:
    graph = _direct_graph()
    violations = [
        f"{module} imports {reached}"
        for module, targets in graph.items()
        if _layer_of_dotted(module) == "interfaces" and not module.endswith(".composition")
        for reached in targets
        if _layer_of_dotted(reached) == "adapters"
    ]
    assert violations == [], "\n".join(sorted(violations))


def test_no_dunder_file_token_anywhere_in_package() -> None:
    """Lexical scan, not AST: an AST walk misses __file__ used as attribute access.

    `some_module.__file__` never appears as an ast.Name node -- it's
    Attribute(value=Name(...), attr='__file__'), and `attr` is a bare string, not a Name
    subnode, so an ast.Name-only walk would miss it. It DOES remain a NAME token after the
    dot, though, so the tokenize scan below still catches it.
    """
    offenders: list[str] = []
    for path in _modules():
        with path.open("rb") as handle:
            for token in tokenize.tokenize(handle.readline):
                if token.type == tokenize.NAME and token.string == "__file__":
                    offenders.append(f"{path}:{token.start[0]}")
    assert offenders == [], (
        "Use importlib.resources.files('scoutmb.resources') for package data.\n"
        + "\n".join(offenders)
    )


def test_no_dynamic_imports_in_core_ports_features() -> None:
    offenders: list[str] = []
    for path in _modules():
        if _layer(path) not in DYNAMIC_BANNED_LAYERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = {
            alias.asname or alias.name: alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                # `import importlib as il` then `il.import_module(...)` unparses as
                # "il.import_module", which a fixed dotted-name list never matches. Resolve
                # the alias back to its real module first.
                head, _, tail = name.partition(".")
                resolved = f"{aliases[head]}.{tail}" if tail and head in aliases else name
                if resolved in BANNED_DYNAMIC or name in BANNED_DYNAMIC:
                    offenders.append(f"{path}:{node.lineno} {name}")
            # Importing the callable is as much a violation as calling it, and is what an
            # aliased `from importlib import import_module` looks like at the import site.
            elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
                offenders.extend(
                    f"{path}:{node.lineno} from importlib import {a.name}"
                    for a in node.names
                    if a.name in {"import_module", "__import__"}
                )
    assert offenders == [], "\n".join(offenders)


def test_first_party_imports_resolves_relative_import_in_package_init() -> None:
    """A package's __init__.py has __package__ == its own dotted name, not one level up.

    `from .model import T` written inside scoutmb/core/__init__.py must resolve to the
    same-layer scoutmb.core.model, not the incorrect, layer-less scoutmb.model that a naive
    `rsplit(".", 1)` would produce.
    """
    tree = ast.parse("from .model import T\n")
    found = _first_party_imports(tree, module="scoutmb.core", is_package=True)
    assert "scoutmb.core.model" in found
    assert "scoutmb.model" not in found


def test_first_party_imports_resolves_relative_import_in_leaf_module() -> None:
    """Regression guard: a non-package module's __package__ is still its parent package."""
    tree = ast.parse("from . import model\n")
    found = _first_party_imports(tree, module="scoutmb.core.service", is_package=False)
    assert "scoutmb.core.model" in found


def test_first_party_imports_resolves_absolute_submodule_import() -> None:
    """`from scoutmb import adapters` must record scoutmb.adapters (a real, layered node),
    not just the layer-less root `scoutmb` -- otherwise this spelling of a cross-layer
    import silently evades every dependency-rule check in this file.
    """
    tree = ast.parse("from scoutmb import adapters\n")
    found = _first_party_imports(tree, module="scoutmb.interfaces.foo", is_package=False)
    assert "scoutmb.adapters" in found


def test_dunder_file_token_scan_catches_attribute_access() -> None:
    """Proves the corrected rationale for the tokenize scan: `mod.__file__` is
    Attribute(value=Name('mod'), attr='__file__'), so `__file__` never appears as an
    ast.Name node -- but it does remain a NAME token after the dot, which is what the
    tokenize-based scan in test_no_dunder_file_token_anywhere_in_package relies on.
    """
    source = b"import scoutmb\nx = scoutmb.__file__\n"
    tokens = list(tokenize.tokenize(io.BytesIO(source).readline))
    assert any(t.type == tokenize.NAME and t.string == "__file__" for t in tokens)
    tree = ast.parse(source.decode())
    assert not any(isinstance(n, ast.Name) and n.id == "__file__" for n in ast.walk(tree))


def test_no_first_party_sys_path_mutation_catches_aliased_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`import sys as s; s.path.append(...)` unparses as "s.path.append", which the fixed
    {"sys.path.append", ...} set never matches without alias resolution. Point the tripwire
    at a synthetic package containing exactly this pattern and confirm it still fires.
    """
    pkg_root = tmp_path / "scoutmb"
    pkg_root.mkdir()
    (pkg_root / "__init__.py").write_text("")
    (pkg_root / "leaky.py").write_text("import sys as s\ns.path.append('/nope')\n")
    monkeypatch.setattr(sys.modules[__name__], "PKG_ROOT", pkg_root)
    with pytest.raises(AssertionError, match=r"s\.path\.append"):
        test_no_first_party_sys_path_mutation()


def test_same_layer_imports_within_ports_and_runtime_are_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ALLOWED` must include a self-entry for every layer, mirroring `interfaces`/`features`/
    `adapters`/`core`, which already list themselves. `ports` and `runtime` previously lacked
    this self-entry, so a same-layer import -- e.g. `ports/ids.py` importing from
    `ports/clock.py`, or one `runtime` module importing another -- was flagged as a false-positive
    cross-layer violation even though same-layer imports are always architecturally legal.

    This builds a synthetic package with exactly that shape in both layers and confirms the
    dependency-rule test now passes against it instead of raising.
    """
    pkg_root = tmp_path / "scoutmb"
    pkg_root.mkdir()
    (pkg_root / "__init__.py").write_text("")

    ports_dir = pkg_root / "ports"
    ports_dir.mkdir()
    (ports_dir / "__init__.py").write_text("")
    (ports_dir / "clock.py").write_text("")
    (ports_dir / "ids.py").write_text("from scoutmb.ports.clock import Clock\n")

    runtime_dir = pkg_root / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "__init__.py").write_text("")
    (runtime_dir / "a.py").write_text("")
    (runtime_dir / "b.py").write_text("from scoutmb.runtime.a import X\n")

    monkeypatch.setattr(sys.modules[__name__], "PKG_ROOT", pkg_root)
    test_transitive_import_edges_are_allowed()


def test_no_first_party_sys_path_mutation() -> None:
    offenders: list[str] = []
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # `import sys as s` then `s.path.append(...)` unparses as "s.path.append", which the
        # fixed dotted-name set never matches. Resolve the alias back to the real module first,
        # mirroring the same resolution done for BANNED_DYNAMIC above.
        aliases = {
            alias.asname or alias.name: alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = ast.unparse(node.func)
                head, _, tail = target.partition(".")
                resolved = f"{aliases[head]}.{tail}" if tail and head in aliases else target
                if resolved in {"sys.path.append", "sys.path.insert", "sys.path.extend"}:
                    offenders.append(f"{path}:{node.lineno} {target}")
    assert offenders == [], "\n".join(offenders)


def test_shape_check_special_cases_only_the_canonical_main_guard(tmp_path: Path) -> None:
    """The canonical `if __name__ == "__main__": raise SystemExit(main())` guard must NOT trip
    the shape check. A structurally different top-level `if` (e.g. a real conditional branch)
    still must -- this proves the special case is narrow, not a blanket ast.If allowance."""
    canonical = tmp_path / "canonical_shim.py"
    canonical.write_text(
        "from scoutmb.core.models import ScoutInput  # noqa: F401\n"
        'if __name__ == "__main__":\n'
        "    raise SystemExit(0)\n"
    )
    assert _shape_check_offenders(canonical) == []

    real_conditional = tmp_path / "not_a_shim.py"
    real_conditional.write_text(
        "import sys\n"
        "if sys.platform == 'win32':\n"
        "    import winreg  # noqa: F401\n"
    )
    assert _shape_check_offenders(real_conditional) != []


def test_shape_check_ignores_union_type_annotations_but_not_body_binops(tmp_path: Path) -> None:
    """PEP 604 `X | None` parameter annotations parse to ast.BinOp -- structurally identical to
    a real arithmetic/bitwise expression, but not business logic. A clean-bodied shim using this
    (extremely common) modern annotation style must still pass; a function whose BODY actually
    contains a BinOp must still fail -- this proves the fix narrows scope to annotations, it
    does not blanket-disable BinOp detection."""
    clean_shim = tmp_path / "clean_shim.py"
    clean_shim.write_text(
        "from typing import Any\n"
        "def process(name: str, config: Any | None = None) -> str:\n"
        "    return name\n"
    )
    assert _shape_check_offenders(clean_shim) == []

    dirty_body = tmp_path / "dirty_body.py"
    dirty_body.write_text(
        "def compute(a: int, b: int) -> int:\n"
        "    return a | b\n"
    )
    assert _shape_check_offenders(dirty_body) != []


def _is_canonical_main_guard(node: ast.If) -> bool:
    """`if __name__ == "__main__": raise SystemExit(main())` -- exactly this shape, nothing
    looser. Matched structurally (comparison target/operator/value, and the body being exactly
    one `raise SystemExit(<call>)` statement) rather than by source-text comparison, so
    formatting differences (quotes, spacing) don't matter but a semantically different guard
    still fails to match."""
    test = node.test
    if not (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    ):
        return False
    if node.orelse:
        return False
    if len(node.body) != 1:
        return False
    (stmt,) = node.body
    return (
        isinstance(stmt, ast.Raise)
        and isinstance(stmt.exc, ast.Call)
        and isinstance(stmt.exc.func, ast.Name)
        and stmt.exc.func.id == "SystemExit"
    )


def _shape_check_offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.If) and _is_canonical_main_guard(node):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr)):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Walk each BODY STATEMENT individually, never the FunctionDef/ClassDef node
            # itself -- ast.walk(node) would also descend into node.args (parameter
            # annotations/defaults), and a PEP 604 `X | None` annotation parses to ast.BinOp,
            # indistinguishable from a real arithmetic expression to this check. Scoping the
            # walk to node.body excludes annotations entirely while still catching a genuine
            # BinOp INSIDE the body (e.g. `return a | b`).
            for stmt in node.body:
                for inner in ast.walk(stmt):
                    if isinstance(inner, (ast.If, ast.For, ast.While, ast.Try, ast.BinOp)):
                        offenders.append(f"{path}:{inner.lineno} {type(inner).__name__}")
            continue
        offenders.append(f"{path}:{node.lineno} {type(node).__name__}")
    return offenders


# Task 24, step 5: once a legacy flat module becomes pure delegation to the package, its
# coverage floor proves nothing (every line is a forwarding import/call), so it gets a shape
# check here instead. Both flat modules (pdf_to_scouts.py, scout_schedule_cli.py) armed this
# check in turn during Slice 2b B10.1/B10.4, then were deleted outright once nothing referenced
# them anymore -- there is currently nothing left to shape-check, but the mechanism (and this
# empty parametrization) stays in place for any future flat-module-to-package migration.
SHIMMED_MODULES: tuple[str, ...] = ()


@pytest.mark.parametrize("relative", SHIMMED_MODULES)
def test_shimmed_module_contains_no_business_logic(relative: str) -> None:
    """Once a module is pure delegation its coverage floor proves nothing, so it gets a shape
    check instead. Permitted: imports, literal/imported-name bindings, forwarding calls, and the
    canonical main-guard."""
    path = Path(__file__).resolve().parents[2] / relative
    assert _shape_check_offenders(path) == []
