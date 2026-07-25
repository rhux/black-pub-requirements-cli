"""Executable form of the Phase B spec's 'Dependency rules' and 'No __file__' sections."""

from __future__ import annotations

import ast
import tokenize
from collections import defaultdict
from pathlib import Path

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
    },
    "features": {"features", "core", "ports", "config", "errors"},
    "adapters": {"adapters", "core", "ports", "config", "errors", "network_policy"},
    "runtime": {"core", "ports", "config", "errors"},
    "core": {"core", "errors"},
    "ports": {"core", "errors"},
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


def _first_party_imports(tree: ast.AST, *, module: str) -> set[str]:
    """Absolute AND relative first-party imports.

    Relative imports carry node.level > 0 and node.module is None for `from . import x`, so a
    check that only reads node.module misses every one of them -- which is most of the ways an
    intra-package edge actually gets written.
    """
    found: set[str] = set()
    package = module.rsplit(".", 1)[0]
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
    return found


def _direct_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for path in _modules():
        dotted = _dotted(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        graph[dotted] = _first_party_imports(tree, module=dotted)
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
    """Lexical scan, not AST: an AST walk misses __file__ inside a string handed to eval."""
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


def test_no_first_party_sys_path_mutation() -> None:
    offenders: list[str] = []
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = ast.unparse(node.func)
                if target in {"sys.path.append", "sys.path.insert", "sys.path.extend"}:
                    offenders.append(f"{path}:{node.lineno} {target}")
    assert offenders == [], "\n".join(offenders)
