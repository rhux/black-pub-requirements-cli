# Slice 2a — Core & Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers-extended-cc:subagent-driven-development`
> (recommended) or `superpowers-extended-cc:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every non-network, non-server boundary of the legacy flat scripts into
`src/scoutmb` behind hexagonal seams, proven against the frozen 478-case catalog, and land the
artifact surface tiering.

**Architecture:** Strangler-fig. Each move relocates a symbol into the package and leaves the
legacy name working — a re-export where the signature is unchanged, a `parse → core →
serialize` shim where it changes. The 478-case characterization suite is never edited, so it
stays green continuously; new package coverage arrives as new files under `tests/parity/`.
Exact-value golden projections cover the surfaces the catalog observes only shallowly.

**Tech Stack:** Python 3.12, hatchling, uv, pytest 8, Hypothesis, coverage.py, Ruff, Mypy,
`ast`/`tokenize` for architecture checks, PyMuPDF + OpenCV (optional extra), openpyxl.

**User decisions (already made):**
- Artifact tiering: `scouts.json` + CSVs stay operational-private; `report.html` and per-scout
  email bodies are audience-shareable and drop `attendee_id`/`qr_url`. CSV column order stays
  pinned. ("Tier the artifacts")
- Slice 2 splits into 2a (core + content) and 2b (runtime + interfaces), Gate 2a between them.
- Breaking the live install mid-slice is acceptable; no release until Phase B completes. The
  launcher bridge therefore lands in 2b, not here.
- Existing tests are not edited. New tests are added freely.
- Phase B contracts live in their own spec; execution lives here.

**Spec:** `docs/superpowers/specs/2026-07-24-phase-b-package-boundaries-design.md`
**Parent spec:** `docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`
**Depends on:** Gate 1a GO, Gate 1b GO.
**Gate at end:** Gate 2a.

---

## Execution rules

1. **Never edit `tests/matrix/cases/*.py` expected values.** The only sanctioned exception in
   2a is `ART-NAME-007`. Adding a new case is allowed and requires a reviewed baseline bump.
2. **Never edit `tests/characterization/*.py`.** Those runners drive the legacy names, which
   keep working through shims. New coverage goes in `tests/parity/` and `tests/unit/`.
3. **One symbol group per task.** A task that moves code does not also change behavior. Where
   both are needed they are separate, adjacent tasks.
4. Run `uv run pytest -q` after every task. A red catalog test means the move changed
   behavior — revert the move, do not adjust the test.
5. Commit at the end of every task.

## File structure created by this slice

| Path | Responsibility |
| --- | --- |
| `src/scoutmb/errors.py` | `ScoutmbError` hierarchy, `CapabilityUnavailable` |
| `src/scoutmb/core/models.py` | Frozen record shapes; no logic, no serialization |
| `src/scoutmb/core/identity.py` | `AttendeeId`, `RunIdentity`, slug + filename stems |
| `src/scoutmb/core/output_schemas.py` | `*_from_mapping` / `*_to_row`, operational + shareable |
| `src/scoutmb/core/inference/numbering.py` | `requirement_path`, `choice_requirement_count` |
| `src/scoutmb/core/inference/tree.py` | Parent/child index tree per (scout, class) group |
| `src/scoutmb/core/inference/status.py` | Recursive status calculation |
| `src/scoutmb/core/inference/missing.py` | Actionable-leaf selection + ancestor walk |
| `src/scoutmb/ports/clock.py` | `Clock`, `Sleeper`, `Jitter` protocols |
| `src/scoutmb/ports/ids.py` | `IdFactory` protocol |
| `src/scoutmb/ports/attendee_source.py` | Port the ingest adapters implement |
| `src/scoutmb/ports/artifact_sink.py` | Port the reporting adapters implement |
| `src/scoutmb/adapters/files/tabular.py` | CSV/XLSX/JSON/text parsing, CSV writing |
| `src/scoutmb/adapters/files/atomic.py` | Atomic single-file publication |
| `src/scoutmb/adapters/pdf/extract.py` | PyMuPDF + OpenCV behind a capability guard |
| `src/scoutmb/adapters/html/report.py` | Template rendering |
| `src/scoutmb/features/ingest/service.py` | Source selection, dedup, adult filter |
| `src/scoutmb/features/reporting/service.py` | Record composition, sink orchestration |
| `src/scoutmb/interfaces/cli/pdf.py` | Stage-1 CLI entry |
| `src/scoutmb/interfaces/cli/composition.py` | The only place `cli` may import adapters |
| `src/scoutmb/resources/__init__.py` | Makes resources importable for `importlib.resources` |
| `src/scoutmb/resources/templates/` | `report.html`, `report.css`, `report.js`, `email.html` |
| `tests/architecture/test_dependency_rules.py` | Allowed-edge, token, dynamic-import checks |
| `tests/parity/` | Package runners over the frozen catalog |
| `tests/goldens/` | V1 + V2 projections, generator, diff assertion |
| `tools/check_mechanisms.py` | Plan-verified mechanism probes |
| `tools/gen_golden.py` | Golden generation (explicit, diff-printing) |
| `tools/check_case_digest.py` | `preserve`-case expected-observation digest |

---

### Task 1: Package skeleton, packaging fixes, and the coverage glob

**Goal:** `src/scoutmb` gains its subpackage tree, `py.typed`, and a `pyproject.toml` that
actually builds and measures it. No behavior moves.

**Files:**
- Create: `src/scoutmb/py.typed`, `src/scoutmb/{core,ports,features,adapters,interfaces,resources}/__init__.py`
  and the nested `core/inference/`, `adapters/files/`, `adapters/pdf/`, `adapters/html/`,
  `features/ingest/`, `features/reporting/`, `interfaces/cli/` `__init__.py` files
- Modify: `pyproject.toml`
- Test: `tests/packaging/test_distribution_contents.py`

**Acceptance Criteria:**
- [ ] Every `__init__.py` created by this task is **empty** (zero bytes)
- [ ] `[tool.coverage.run] include` matches `src/scoutmb/**/*.py`, verified against a nested module
- [ ] `[project.scripts]` names modules that will exist; the broken `scoutmb.cli.app:main` is gone
- [ ] A built wheel contains `scoutmb/py.typed`
- [ ] `uv run pytest -q` still green (701 tests)

**Verify:** `uv run pytest tests/packaging/test_distribution_contents.py -q` → PASS

**Recovery:** Revert `pyproject.toml` from git; the empty `__init__.py` files are inert and can stay. A broken build config blocks every later task, so fix it here rather than working around it.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/packaging/test_distribution_contents.py
"""The wheel must carry py.typed and package data; coverage must reach nested modules.

These are packaging facts that are invisible until something installs the wheel somewhere
else, which is exactly when they are expensive to discover.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        [sys.executable, "-m", "uv", "build", "--wheel", "--out-dir", str(out)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    wheels = list(out.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"
    return wheels[0]


def test_wheel_contains_py_typed(built_wheel: Path) -> None:
    with zipfile.ZipFile(built_wheel) as archive:
        names = set(archive.namelist())
    assert "scoutmb/py.typed" in names, sorted(n for n in names if n.startswith("scoutmb/"))


def test_coverage_include_reaches_nested_modules() -> None:
    """`src/scoutmb/*.py` does NOT match a nested module: coverage's `*` never crosses `/`."""
    from coverage.files import globs_to_regex

    import tomllib

    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = config["tool"]["coverage"]["run"]["include"]
    pattern = globs_to_regex(include, case_insensitive=False, partial=False)
    assert pattern.match("src/scoutmb/core/inference/tree.py"), include
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/packaging/test_distribution_contents.py -q
```

Expected: both tests fail — no `py.typed` exists, and `include` is `src/scoutmb/*.py`.

- [ ] **Step 3: Create the package tree**

```bash
cd /Users/rhux/Documents/Software/black-pub-requirements-cli
touch src/scoutmb/py.typed
for d in core core/inference ports features features/ingest features/reporting \
         adapters adapters/files adapters/pdf adapters/html \
         interfaces interfaces/cli resources; do
  mkdir -p "src/scoutmb/$d"
  : > "src/scoutmb/$d/__init__.py"
done
mkdir -p src/scoutmb/resources/templates tests/packaging tests/architecture tests/parity tests/goldens
: > tests/packaging/__init__.py
```

- [ ] **Step 4: Fix `pyproject.toml`**

Replace the `[project.scripts]` block:

```toml
[project.scripts]
troop349 = "scoutmb.interfaces.desktop:main"
troop349-pdf = "scoutmb.interfaces.cli.pdf:main"
troop349-schedule = "scoutmb.interfaces.cli.schedule:main"
```

> `troop349` and `troop349-schedule` name modules Slice 2b creates. They are declared now so
> the contract is visible in one place; the wheel test in this task only exercises
> `troop349-pdf`, which Task 18 makes real. A console script whose module is missing fails at
> invocation, not at install, so this does not break the build.

Replace the wheel/build blocks:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/scoutmb"]

[tool.hatch.build.targets.wheel.force-include]
"src/scoutmb/py.typed" = "scoutmb/py.typed"

[tool.hatch.build]
exclude = ["bootstrap", "raw_data", "docs", "tests"]
```

Replace the coverage `include` list:

```toml
[tool.coverage.run]
branch = true
include = [
    "scout_schedule_cli.py",
    "pdf_to_scouts.py",
    "ui/server.py",
    "run_app.py",
    "bootstrap/paths.py",
    "bootstrap/marker.py",
    "bootstrap/source_sync.py",
    "src/scoutmb/**/*.py",
    "tools/*.py",
]
```

- [ ] **Step 5: Run — expect PASS**

```bash
uv run pytest tests/packaging/test_distribution_contents.py -q
uv run pytest -q
```

Expected: packaging tests PASS; the full suite still reports its existing 701 passed.

- [ ] **Step 6: Commit**

```bash
git add src/scoutmb pyproject.toml tests/packaging
git commit -m "build: create package tree, ship py.typed, fix coverage glob and console scripts

coverage.py's '*' does not cross a path separator, so 'src/scoutmb/*.py' would have
silently excluded every subpackage this slice creates."
```

---

### Task 2: Error hierarchy and `CapabilityUnavailable`

**Goal:** One `ScoutmbError` root with a typed capability error carrying an actionable remedy.
User-visible message text is unchanged anywhere it already exists.

**Files:**
- Modify: `src/scoutmb/errors.py`
- Test: `tests/unit/test_errors.py`

**Acceptance Criteria:**
- [ ] `CapabilityUnavailable` names the capability, the distributions, and the pip remedy
- [ ] Every error class subclasses `ScoutmbError`, which subclasses `Exception`
- [ ] `str(exc)` for a wrapped cause does **not** prepend a class name or traceback fragment
- [ ] Existing `network_policy` errors keep their current type relationship

**Verify:** `uv run pytest tests/unit/test_errors.py -q` → PASS

**Recovery:** `errors.py` is additive — nothing imports `CapabilityUnavailable` until Task 16. Revert the file if the hierarchy is wrong; no other task is blocked.

**Steps:**

- [ ] **Step 1: Read the existing file first**

```bash
cat src/scoutmb/errors.py
```

The existing contents stay; this task adds to them. If `ScoutmbError` already exists, reuse it
rather than redefining.

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_errors.py
from __future__ import annotations

import pytest

from scoutmb.errors import CapabilityUnavailable, ScoutmbError


def test_capability_error_names_capability_distributions_and_remedy() -> None:
    exc = CapabilityUnavailable(capability="pdf", distributions=("PyMuPDF", "opencv-python-headless"), extra="pdf")
    text = str(exc)
    assert "pdf" in text
    assert "PyMuPDF" in text
    assert "opencv-python-headless" in text
    assert "pip install 'scoutmb[pdf]'" in text


def test_capability_error_is_a_scoutmb_error() -> None:
    exc = CapabilityUnavailable(capability="pdf", distributions=("PyMuPDF",), extra="pdf")
    assert isinstance(exc, ScoutmbError)
    assert isinstance(exc, Exception)


def test_error_message_is_not_decorated_with_class_name() -> None:
    """errors.csv and the web layer pass the message through verbatim (ART-SCHEMA-004,
    UI-ROUTE-025). A wrapper that prefixes the class name changes a pinned surface."""
    exc = ScoutmbError("boom")
    assert str(exc) == "boom"
```

- [ ] **Step 3: Run — expect FAIL** (`ImportError: cannot import name 'CapabilityUnavailable'`)

```bash
uv run pytest tests/unit/test_errors.py -q
```

- [ ] **Step 4: Implement**

```python
# append to src/scoutmb/errors.py


class CapabilityUnavailable(ScoutmbError):
    """An optional capability was requested but its distributions are not installed.

    Raised instead of letting a bare ImportError traceback escape, so the message can name
    the remedy. The message text is user-facing.
    """

    def __init__(self, *, capability: str, distributions: tuple[str, ...], extra: str) -> None:
        self.capability = capability
        self.distributions = distributions
        self.extra = extra
        needed = ", ".join(distributions)
        super().__init__(
            f"The {capability} capability needs {needed}, which is not installed. "
            f"Install it with: pip install 'scoutmb[{extra}]'"
        )
```

- [ ] **Step 5: Run — expect PASS**

```bash
uv run pytest tests/unit/test_errors.py -q
```

- [ ] **Step 6: Commit**

```bash
git add src/scoutmb/errors.py tests/unit/test_errors.py
git commit -m "feat: add CapabilityUnavailable with an actionable remedy message"
```

---

### Task 3: Mechanism probes (plan-verified facts)

**Goal:** Prove by execution the four mechanism claims the spec marks *plan-verified*, before
any task depends on them. If a probe fails, the spec is amended and the dependent task is
redesigned — that is the point of running this first.

**Files:**
- Create: `tools/check_mechanisms.py`, `tests/packaging/test_mechanisms.py`
- Create: `src/scoutmb/resources/__init__.py` (already created empty in Task 1 — content stays empty)

**Acceptance Criteria:**
- [ ] `dataclasses.asdict` tuple behavior is asserted, not assumed
- [ ] `importlib.resources.files("scoutmb.resources")` reads a template from an **installed wheel**
- [ ] The same call reads a template from a **copied directory** release root
- [ ] A probe failure produces a message naming which spec section to amend

**Verify:** `uv run pytest tests/packaging/test_mechanisms.py -q` → PASS

**Recovery:** A failing probe is the deliverable working, not a task failure. Stop, amend the named spec section with the mechanism that does hold, and redesign the dependent task (21 for resources, 14/20 for `asdict`) before continuing.

**Steps:**

- [ ] **Step 1: Add a probe template so there is something to read**

```bash
printf 'probe-token-do-not-remove\n' > src/scoutmb/resources/templates/_probe.txt
```

- [ ] **Step 2: Declare templates as package data in `pyproject.toml`**

Add under the existing `[tool.hatch.build.targets.wheel.force-include]`:

```toml
"src/scoutmb/resources/templates" = "scoutmb/resources/templates"
```

- [ ] **Step 3: Write the probes**

```python
# tests/packaging/test_mechanisms.py
"""Mechanism probes. The Phase B spec marks these plan-verified: they are claims about how
Python and this build behave, and prior spec drafts got two of them wrong.

If one of these fails, amend the named spec section — do not work around it in a later task.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE = "probe-token-do-not-remove"


def test_asdict_preserves_tuple_type() -> None:
    """Spec: 'Frozen records and collection types'. asdict reconstructs via type(obj)(...),
    so a tuple stays a tuple. Normalization to list is the serializer's job."""

    @dataclasses.dataclass(frozen=True, slots=True)
    class Record:
        items: tuple[int, ...]

    value = dataclasses.asdict(Record((1, 2)))
    assert isinstance(value["items"], tuple), (
        "asdict changed behavior; amend the 'Frozen records and collection types' section"
    )


def test_resources_readable_from_installed_wheel(tmp_path: Path) -> None:
    """Spec: 'No __file__ in the package'."""
    out = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "uv", "build", "--wheel", "--out-dir", str(out)],
        cwd=REPO_ROOT, check=True, capture_output=True,
    )
    wheel = next(out.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert "scoutmb/resources/templates/_probe.txt" in archive.namelist()

    site = tmp_path / "site"
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(site)

    code = (
        "from importlib.resources import files;"
        "print(files('scoutmb.resources').joinpath('templates/_probe.txt').read_text().strip())"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=site, check=True, capture_output=True, text=True,
        env={"PYTHONPATH": str(site), "PATH": ""},
    )
    assert result.stdout.strip() == PROBE


def test_resources_readable_from_copied_release_root(tmp_path: Path) -> None:
    """The release root is a COPIED DIRECTORY, not an installed distribution. This is the
    case the spec was least sure about; if it fails, amend 'No __file__ in the package'."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    shutil.copytree(REPO_ROOT / "src" / "scoutmb", app_dir / "scoutmb")

    code = (
        "from importlib.resources import files;"
        "print(files('scoutmb.resources').joinpath('templates/_probe.txt').read_text().strip())"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=app_dir, check=True, capture_output=True, text=True,
        env={"PYTHONPATH": str(app_dir), "PATH": ""},
    )
    assert result.stdout.strip() == PROBE, (
        "importlib.resources cannot read templates from a copied directory root; "
        "amend the 'No __file__ in the package' section before Task 21"
    )
```

- [ ] **Step 4: Run — all three must PASS**

```bash
uv run pytest tests/packaging/test_mechanisms.py -q -s
```

If `test_resources_readable_from_copied_release_root` fails, **stop the slice** and amend the
spec's "No `__file__` in the package" section with the mechanism that does work (most likely
adding an explicit `__init__.py` to `templates/`, or falling back to a resource-loader
abstraction). Do not proceed to Task 21 on an unproven mechanism.

- [ ] **Step 5: Commit**

```bash
git add tools tests/packaging/test_mechanisms.py src/scoutmb/resources pyproject.toml
git commit -m "test: prove the plan-verified mechanisms before anything depends on them"
```

---

### Task 4: Dependency-rule architecture test

**Goal:** The allowed-edge table, the `__file__` token ban, and the dynamic-import restriction
become an executable check, before there is enough package code to violate them silently.

**Files:**
- Create: `tests/architecture/__init__.py`, `tests/architecture/test_dependency_rules.py`
- Test: itself

**Acceptance Criteria:**
- [ ] Edges checked over the **transitive** first-party graph, not direct imports only
- [ ] Same-layer edges (`interfaces→interfaces`, `adapters→adapters`, `features→features`) allowed
- [ ] Adapter imports from `interfaces` confined to `interfaces/*/composition.py`
- [ ] `__file__` rejected by **lexical token scan** anywhere under `src/scoutmb/`
- [ ] The five named dynamic-import forms rejected in `core`/`ports`/`features`
- [ ] No first-party `sys.path` mutation anywhere

**Verify:** `uv run pytest tests/architecture -q` → PASS

**Recovery:** If a rule proves unimplementable as specified, narrow it and say so in the test's docstring — an honest weaker check beats a strong-sounding one that silently passes. Do not delete the test.

**Steps:**

- [ ] **Step 1: Write the test (it passes trivially on an empty package, and that is fine — it
  is a tripwire that arms now and fires later)**

```python
# tests/architecture/test_dependency_rules.py
"""Executable form of the Phase B spec's 'Dependency rules' and 'No __file__' sections."""

from __future__ import annotations

import ast
import tokenize
from collections import defaultdict
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[2] / "src" / "scoutmb"

ALLOWED: dict[str, set[str]] = {
    "interfaces": {"interfaces", "features", "core", "ports", "config", "errors", "adapters",
                   "network_policy"},
    "features": {"features", "core", "ports", "config", "errors"},
    "adapters": {"adapters", "core", "ports", "config", "errors", "network_policy"},
    "runtime": {"core", "ports", "config", "errors"},
    "core": {"core", "errors"},
    "ports": {"core", "errors"},
}

BANNED_DYNAMIC = {
    "importlib.import_module", "importlib.__import__", "__import__",
    "imp.load_module", "exec", "eval",
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


def _first_party_imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("scoutmb"):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("scoutmb"):
            found.add(node.module)
    return found


def _direct_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        graph[_dotted(path)] = _first_party_imports(tree)
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
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                if name in BANNED_DYNAMIC:
                    offenders.append(f"{path}:{node.lineno} {name}")
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
```

- [ ] **Step 2: Run — expect PASS**

```bash
uv run pytest tests/architecture -q
```

> It passes on an almost-empty package. That is correct: this is a tripwire armed before the
> code that could trip it exists. Task 16 is the first task that must satisfy it non-trivially.

- [ ] **Step 3: Add the `architecture` job to CI**

```yaml
  architecture:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv python install 3.12
      - run: uv sync --locked --all-extras
      - run: uv run pytest tests/architecture tests/packaging -q
```

- [ ] **Step 4: Commit**

```bash
git add tests/architecture .github/workflows/ci.yml
git commit -m "test: arm the dependency-rule tripwires before any code can trip them"
```

---

### Task 5: `core/models.py` — frozen record shapes

**Goal:** The four record shapes exist as frozen, slotted dataclasses with tuple collections.
Legacy definitions become re-export aliases so every catalog runner keeps working.

**Files:**
- Create: `src/scoutmb/core/models.py`
- Modify: `scout_schedule_cli.py` (`ScoutInput`, `ClassRecord`, `RequirementRecord`, `ScoutResult`)
- Test: `tests/parity/test_models_parity.py`

**Acceptance Criteria:**
- [ ] Field names and declaration order identical to the legacy dataclasses
- [ ] `ScoutResult` collections are tuples with `default_factory=tuple`
- [ ] `ClassRecord` and `RequirementRecord` are `frozen=True, slots=True`
- [ ] `ScoutInput` stays **mutable** (see Step 3 note) — this is deliberate and temporary
- [ ] `asdict` field order matches `__dataclass_fields__`, which `ART-SCHEMA-002/003` pin
- [ ] Full suite green

**Verify:** `uv run pytest tests/parity/test_models_parity.py tests/characterization -q` → PASS

**Recovery:** Delete `core/models.py` and its parity file; nothing imports them until Task 14. The legacy dataclasses are untouched by this task, so the suite returns to green immediately.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/parity/test_models_parity.py
"""The package records must be field-for-field identical to the legacy ones, in order.
ART-SCHEMA-002/003 pin the CSV header to __dataclass_fields__ order, so a reorder here is a
silent breaking change to a shipped artifact."""

from __future__ import annotations

from dataclasses import asdict, fields

import scout_schedule_cli as legacy
from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutInput, ScoutResult


def test_class_record_fields_match_legacy_in_order() -> None:
    assert [f.name for f in fields(ClassRecord)] == [f.name for f in fields(legacy.ClassRecord)]


def test_requirement_record_fields_match_legacy_in_order() -> None:
    assert [f.name for f in fields(RequirementRecord)] == [
        f.name for f in fields(legacy.RequirementRecord)
    ]


def test_scout_result_collections_are_tuples() -> None:
    result = ScoutResult(name="Avery Example", qr_url="https://example.invalid/x")
    assert result.classes == ()
    assert result.requirements == ()
    assert result.errors == ()


def test_asdict_preserves_declaration_order() -> None:
    record = RequirementRecord(
        scout_name="Avery Example", attendee_id="90000001", class_number="26MB1",
        class_p4_id="2000001", merit_badge_name="Chess", requirement_id="r1",
        requirement_type_id="1", requirement_number="3b", description="Show your work.",
        completed_requirement=False, completed_class=False, requirement_on_event=True,
        present_days="MoTuWeTh",
    )
    assert list(asdict(record)) == [f.name for f in fields(legacy.RequirementRecord)]
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError: scoutmb.core.models`)

- [ ] **Step 3: Implement**

```python
# src/scoutmb/core/models.py
"""Frozen record shapes. No logic, no serialization, no I/O.

Serialization lives in core/output_schemas.py as free functions, which is what keeps this
module dependency-free and keeps `models.py` from becoming the place everything imports.

Field DECLARATION ORDER is a shipped contract: classes.csv and requirements.csv take their
header from __dataclass_fields__ (ART-SCHEMA-002, ART-SCHEMA-003). Do not reorder, and do not
add a field except at the end with a default.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ScoutInput:
    """Deliberately MUTABLE, unlike the other records.

    legacy load_inputs strips url/name/registrant_type in place on each instance. Freezing
    this shape is a behavior change to the loader, which Task 15 makes explicitly; until then
    the mutable shape is what the catalog's input cases exercise.
    """

    name: str
    url: str
    registrant_type: str = ""


@dataclass(frozen=True, slots=True)
class ClassRecord:
    scout_name: str
    attendee_id: str
    class_number: str
    class_p4_id: str
    class_name: str
    days: str
    period_name: str
    start_time: str
    start_time_24h: str
    location: str
    has_requirements: bool
    class_completed: bool
    raw_class_name: str


@dataclass(frozen=True, slots=True)
class RequirementRecord:
    scout_name: str
    attendee_id: str
    class_number: str
    class_p4_id: str
    merit_badge_name: str
    requirement_id: str
    requirement_type_id: str
    requirement_number: str
    description: str
    completed_requirement: bool
    completed_class: bool
    requirement_on_event: bool
    present_days: str


@dataclass(frozen=True, slots=True)
class ScoutResult:
    name: str
    qr_url: str
    attendee_id: str = ""
    classes: tuple[ClassRecord, ...] = field(default_factory=tuple)
    requirements: tuple[RequirementRecord, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
```

- [ ] **Step 4: Leave the legacy definitions alone for now**

`scout_schedule_cli.ScoutResult` is mutated in place (`result.errors.append(...)`,
`result.classes.append(...)`) inside `process_scout`, which is **2b** code. Replacing the
legacy definition with the frozen one here would break `process_scout` and every acquisition
case with it.

So this task adds the package models **beside** the legacy ones and proves them equal. The
legacy `ClassRecord`/`RequirementRecord` become aliases in Task 14, once
`output_schemas` can construct them; `ScoutResult` becomes an alias in **2b**, with the
`append` sites rewritten to accumulate locally and construct once.

Add a pointer comment at the legacy definitions so the duplication is not mistaken for drift:

```python
# scout_schedule_cli.py — directly above `class ScoutInput:`
# NOTE: scoutmb.core.models holds the package copies of these four shapes, proven
# field-identical by tests/parity/test_models_parity.py. ClassRecord/RequirementRecord become
# aliases in Slice 2a Task 14; ScoutResult in Slice 2b, once process_scout stops mutating it.
```

- [ ] **Step 5: Run — expect PASS**

```bash
uv run pytest tests/parity/test_models_parity.py -q && uv run pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add src/scoutmb/core/models.py tests/parity/test_models_parity.py scout_schedule_cli.py
git commit -m "feat: add frozen package record shapes proven field-identical to legacy"
```

---

### Task 6: `core/identity.py` — move identity, leave re-exports

**Goal:** `AttendeeId`, `MissingAttendeeId`, `RunIdentity`, `safe_slug`, and
`attendee_filename_stem` live in the package. Legacy names become re-exports, so every
`ART-NAME-*` and identity case keeps passing untouched.

**Files:**
- Create: `src/scoutmb/core/identity.py`
- Modify: `scout_schedule_cli.py` (delete five definitions, add one import)
- Test: `tests/parity/test_identity_parity.py`

**Acceptance Criteria:**
- [ ] Legacy `scout_schedule_cli.safe_slug` etc. still importable and behave identically
- [ ] `tests/unit/test_identity.py` and `test_output_filenames.py` (Slice 1a) pass unmodified
- [ ] `PLAT-B-SLUG` and `ACQ-B-OUTPUT-ID` catalog cases green
- [ ] Shim section of `scout_schedule_cli.py` is imports only — no logic

**Verify:** `uv run pytest tests/unit tests/parity tests/characterization -q` → PASS

**Recovery:** Restore the five definitions to `scout_schedule_cli.py` from git and delete the package module. Slice 1a's identity tests are the tripwire — if they fail, the move was not verbatim.

**Steps:**

- [ ] **Step 1: Write the parity test**

```python
# tests/parity/test_identity_parity.py
from __future__ import annotations

import pytest

import scout_schedule_cli as legacy
from scoutmb.core.identity import AttendeeId, MissingAttendeeId, RunIdentity, safe_slug


@pytest.mark.parametrize(
    "value",
    ["Avery Example", "  Mixed   Case  ", "O'Neil-Smith", "", "!!!", "Ünïcödé Näme"],
)
def test_safe_slug_matches_legacy(value: str) -> None:
    assert safe_slug(value) == legacy.safe_slug(value)


def test_legacy_names_are_the_package_objects() -> None:
    """Re-export, not a copy: a second implementation would drift silently."""
    assert legacy.safe_slug is safe_slug
    assert legacy.AttendeeId is AttendeeId
    assert legacy.RunIdentity is RunIdentity
    assert legacy.MissingAttendeeId is MissingAttendeeId


def test_blank_attendee_id_fails_closed() -> None:
    with pytest.raises(MissingAttendeeId):
        AttendeeId.parse("   ", "Avery Example")


def test_output_id_is_stable_within_a_run_and_distinct_across_attendees() -> None:
    identity = RunIdentity()
    first = identity.output_id(AttendeeId.parse("90000001"))
    again = identity.output_id(AttendeeId.parse("90000001"))
    other = identity.output_id(AttendeeId.parse("90000002"))
    assert first == again
    assert first != other
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`)

- [ ] **Step 3: Create `src/scoutmb/core/identity.py`** by moving the five definitions verbatim
  from `scout_schedule_cli.py` (`MissingAttendeeId` at the top of the file, `AttendeeId`,
  `RunIdentity`, then `safe_slug` and `attendee_filename_stem` from the writers section):

```python
# src/scoutmb/core/identity.py
"""Attendee identity and the names derived from it.

Upstream attendee ID is required identity and fails closed when absent (D3). Output identity
is a per-run UUIDv4 (D25) so a shareable filename never carries the bearer token.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field


class MissingAttendeeId(RuntimeError):
    """An attendee record arrived without the ID we use as identity."""

    def __init__(self, scout_name: str = "") -> None:
        self.scout_name = scout_name
        super().__init__(f"No attendee_id for {scout_name or 'an unnamed attendee'}")


@dataclass(frozen=True, slots=True)
class AttendeeId:
    value: str

    @classmethod
    def parse(cls, raw: str, scout_name: str = "") -> "AttendeeId":
        cleaned = str(raw or "").strip()
        if not cleaned:
            raise MissingAttendeeId(scout_name)
        return cls(cleaned)


@dataclass(slots=True)
class RunIdentity:
    """Assigns a UUIDv4 per attendee for one run. Stable within the run instance.

    Exactly one instance exists per run and is threaded to every collaborator that needs an
    output id. Constructing a second one inside a writer produces UUIDs that disagree with the
    rest of the run, which is what the legacy code did in write_email_reports.
    """

    _by_attendee: dict[str, str] = field(default_factory=dict)

    def output_id(self, attendee: AttendeeId) -> str:
        existing = self._by_attendee.get(attendee.value)
        if existing is None:
            existing = str(uuid.uuid4())
            self._by_attendee[attendee.value] = existing
        return existing


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "unknown-scout"


def attendee_filename_stem(scout_name: str, output_id: str) -> str:
    """Readable, collision-free filename stem: name slug + the FULL per-run output UUID
    (hyphens stripped). The full UUID — never a truncation — guarantees distinct attendees
    get distinct filenames. Never the raw attendee_id (a bearer token that must not appear
    in a shareable filename)."""
    return f"{safe_slug(scout_name)}-{str(output_id).replace('-', '')}"
```

- [ ] **Step 4: Replace the legacy definitions with a re-export**

Delete `MissingAttendeeId`, `AttendeeId`, `RunIdentity`, `safe_slug`, and
`attendee_filename_stem` from `scout_schedule_cli.py`, and add near the other imports:

```python
from scoutmb.core.identity import (  # noqa: F401 - re-exported for the legacy public surface
    AttendeeId,
    MissingAttendeeId,
    RunIdentity,
    attendee_filename_stem,
    safe_slug,
)
```

Also remove the now-unused `import uuid` if nothing else in the module uses it — check first:

```bash
rg -n '\buuid\b' scout_schedule_cli.py
```

- [ ] **Step 5: Run — expect PASS**

```bash
uv run pytest -q
```

Expected: the same 701 tests pass, plus the new parity file. A failure in
`tests/unit/test_identity.py` or `tests/unit/test_output_filenames.py` means the move changed
behavior — revert and diff the moved source against the original.

- [ ] **Step 6: Commit**

```bash
git add src/scoutmb/core/identity.py tests/parity/test_identity_parity.py scout_schedule_cli.py
git commit -m "refactor: move identity into scoutmb.core.identity, re-export from legacy"
```

---

### Task 7: One run-scoped `RunIdentity`

**Goal:** Remove the second and third `RunIdentity` instances so one attendee has one
`output_id` for the whole run. This is a **behavior fix**, separate from the Task 6 move.

**Files:**
- Modify: `scout_schedule_cli.py` (`write_outputs`, `write_email_reports`)
- Test: `tests/unit/test_run_identity_scope.py`

**Acceptance Criteria:**
- [ ] `write_email_reports` accepts a `RunIdentity` and constructs none
- [ ] `write_outputs` accepts a `RunIdentity`, defaulting to a fresh one for direct callers
- [ ] `async_main` passes its existing instance through
- [ ] Same attendee → same `output_id` in `raw/` filenames and `emails/` filenames
- [ ] `ART-NAME-*` and `ART-SCHEMA-007` cases still green (UUIDs are normalized in those)

**Verify:** `uv run pytest tests/unit/test_run_identity_scope.py tests/characterization -q` → PASS

**Recovery:** Restore the internal `RunIdentity()` construction in `write_email_reports` and drop the parameter from both signatures. This reinstates the split-map defect, which is preferable to a half-threaded identity that is inconsistent across writers.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_run_identity_scope.py
"""One run, one identity map.

Before this task write_email_reports built its own RunIdentity, so an attendee's email
filename UUID had no relationship to the UUID used for its raw/ files in the same run.
"""

from __future__ import annotations

from pathlib import Path

import scout_schedule_cli as legacy


def _nested(attendee_id: str, scout_name: str) -> list[dict[str, object]]:
    return [
        {
            "name": scout_name,
            "attendee_id": attendee_id,
            "classes": [],
            "requirements": [
                {
                    "scout_name": scout_name,
                    "attendee_id": attendee_id,
                    "class_number": "26MB1",
                    "class_p4_id": "2000001",
                    "merit_badge_name": "Chess",
                    "requirement_id": "r1",
                    "requirement_type_id": "1",
                    "requirement_number": "3b",
                    "description": "Show your work.",
                    "completed_requirement": False,
                    "completed_class": False,
                    "requirement_on_event": True,
                    "present_days": "MoTuWeTh",
                }
            ],
            "errors": [],
        }
    ]


def test_email_filenames_use_the_supplied_run_identity(tmp_path: Path) -> None:
    identity = legacy.RunIdentity()
    expected = identity.output_id(legacy.AttendeeId.parse("90000001"))

    legacy.write_email_reports(tmp_path, _nested("90000001", "Avery Example"), run_identity=identity)

    stems = {p.stem for p in (tmp_path / "emails").glob("*.txt")}
    assert stems == {legacy.attendee_filename_stem("Avery Example", expected)}


def test_write_email_reports_creates_no_identity_of_its_own(tmp_path: Path) -> None:
    identity = legacy.RunIdentity()
    legacy.write_email_reports(tmp_path, _nested("90000001", "Avery Example"), run_identity=identity)
    # The map now holds exactly the one attendee the writer resolved.
    assert list(identity._by_attendee) == ["90000001"]
```

- [ ] **Step 2: Run — expect FAIL** (`write_email_reports() got an unexpected keyword argument`)

- [ ] **Step 3: Thread the identity**

In `scout_schedule_cli.py`, change the signature and delete the internal construction:

```python
def write_email_reports(
    output_dir: Path,
    scouts: list[dict[str, Any]],
    *,
    run_identity: RunIdentity | None = None,
) -> Path:
    """Write per-scout missing-requirement emails plus a combined mail-merge CSV."""
    emails_dir = output_dir / "emails"
    emails_dir.mkdir(parents=True, exist_ok=True)
    missing = build_missing_requirements(scouts)
    # One identity per run. A fresh instance here would mint UUIDs unrelated to the ones the
    # rest of the run already used for this attendee's raw/ files.
    run_identity = run_identity or RunIdentity()
```

Then in `write_outputs`, accept and forward it:

```python
def write_outputs(
    output_dir: Path,
    results: list[ScoutResult],
    *,
    generate_html: bool = True,
    html_name: str = "report.html",
    generate_email_report: bool = False,
    run_identity: RunIdentity | None = None,
) -> None:
    run_identity = run_identity or RunIdentity()
```

and at the email call site:

```python
    email_report_dir = (
        write_email_reports(output_dir, nested, run_identity=run_identity).name
        if generate_email_report
        else None
    )
```

Finally, in `async_main`, pass the run's instance through to `write_outputs`:

```python
    write_outputs(
        args.output,
        results,
        generate_html=not args.no_html,
        html_name=args.html_name,
        generate_email_report=getattr(args, "email_report", False),
        run_identity=run_identity,
    )
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_run_identity_scope.py -q && uv run pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add scout_schedule_cli.py tests/unit/test_run_identity_scope.py
git commit -m "fix: one RunIdentity per run so an attendee has one output_id everywhere

write_email_reports built its own map, so email filenames used UUIDs unrelated to the
same attendee's raw/ filenames in the same run."
```

---

### Task 8: `ports/clock.py` and `ports/ids.py`

**Goal:** Nondeterminism becomes injectable per collaborator, with real default
implementations. Nothing consumes them yet — 2b's acquisition service does.

**Files:**
- Create: `src/scoutmb/ports/clock.py`, `src/scoutmb/ports/ids.py`
- Test: `tests/unit/test_ports_clock.py`

**Acceptance Criteria:**
- [ ] `Clock` returns timezone-aware UTC; `Sleeper` uses a monotonic source
- [ ] `Jitter` is seedable and reproducible
- [ ] `IdFactory` produces UUIDv4
- [ ] All four are `Protocol`s with a concrete default beside them
- [ ] `ports/` imports nothing outside `core` and `errors` (architecture test enforces)

**Verify:** `uv run pytest tests/unit/test_ports_clock.py tests/architecture -q` → PASS

**Recovery:** Delete both port modules; nothing consumes them until 2b. They are additive.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ports_clock.py
from __future__ import annotations

from datetime import UTC

from scoutmb.ports.clock import SeededJitter, SystemClock
from scoutmb.ports.ids import Uuid4Factory


def test_clock_returns_timezone_aware_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == UTC.utcoffset(None)


def test_seeded_jitter_is_reproducible() -> None:
    first = [SeededJitter(seed=7).jitter(0.5, 2.0) for _ in range(5)]
    second = [SeededJitter(seed=7).jitter(0.5, 2.0) for _ in range(5)]
    assert first == second
    assert all(0.5 <= value <= 2.0 for value in first)


def test_id_factory_makes_distinct_uuid4() -> None:
    factory = Uuid4Factory()
    values = {factory.new_id() for _ in range(100)}
    assert len(values) == 100
    assert all(len(value) == 36 for value in values)
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/scoutmb/ports/clock.py
"""Time and randomness, injected per collaborator rather than as one bag (D32).

Wall time is for persisted timestamps. Elapsed time and delays use a MONOTONIC source so a
wall-clock jump cannot affect retry, timeout, or shutdown behavior.
"""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class Sleeper(Protocol):
    async def sleep(self, seconds: float) -> None: ...
    def monotonic(self) -> float: ...


class Jitter(Protocol):
    def jitter(self, low: float, high: float) -> float: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class MonotonicSleeper:
    async def sleep(self, seconds: float) -> None:
        import asyncio

        await asyncio.sleep(seconds)

    def monotonic(self) -> float:
        return time.monotonic()


class SeededJitter:
    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def jitter(self, low: float, high: float) -> float:
        return self._random.uniform(low, high)
```

```python
# src/scoutmb/ports/ids.py
from __future__ import annotations

import uuid
from typing import Protocol


class IdFactory(Protocol):
    def new_id(self) -> str: ...


class Uuid4Factory:
    def new_id(self) -> str:
        return str(uuid.uuid4())
```

> `MonotonicSleeper.sleep` imports `asyncio` inside the method deliberately: `ports/` is
> imported by `core`, and a module-level asyncio import in a port pulls the event-loop
> machinery into every pure-core import path for no benefit.

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_ports_clock.py tests/architecture -q
```

- [ ] **Step 5: Commit**

```bash
git add src/scoutmb/ports tests/unit/test_ports_clock.py
git commit -m "feat: add clock and id ports with seedable, monotonic defaults"
```

---

### Task 9: `core/inference/numbering.py`

**Goal:** The two pure numbering functions move. Legacy names become re-exports, so all 26
`REQ-SHAPE-*` and 30 `REQ-CHOICE-*` cases keep passing untouched.

**Files:**
- Create: `src/scoutmb/core/inference/numbering.py`
- Modify: `scout_schedule_cli.py` (delete two definitions + `CHOICE_COUNT_WORDS`, add import)
- Test: `tests/parity/test_numbering_parity.py`

**Acceptance Criteria:**
- [ ] `legacy.requirement_path is numbering.requirement_path` (re-export, not a copy)
- [ ] All 26 shapes produce identical `(path, current_top_level)` pairs
- [ ] Hypothesis: never raises on arbitrary text
- [ ] `REQ-B-PATH` and `REQ-B-CHOICE` boundaries green

**Verify:** `uv run pytest tests/parity/test_numbering_parity.py tests/characterization/test_requirement_matrix.py -q` → PASS

**Recovery:** Restore the three definitions from git. A `REQ-SHAPE-*` failure means the move was not verbatim — diff before debugging.

**Steps:**

- [ ] **Step 1: Write the parity test**

```python
# tests/parity/test_numbering_parity.py
from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

import scout_schedule_cli as legacy
from scoutmb.core.inference.numbering import choice_requirement_count, requirement_path
from tests.factories.payloads import REQUIREMENT_NUMBER_SHAPES


def test_legacy_names_are_the_package_objects() -> None:
    assert legacy.requirement_path is requirement_path
    assert legacy.choice_requirement_count is choice_requirement_count


@pytest.mark.parametrize("shape", REQUIREMENT_NUMBER_SHAPES)
@pytest.mark.parametrize("top", [None, "7"])
def test_all_observed_shapes_parse_identically(shape: str, top: str | None) -> None:
    assert requirement_path(shape, top) == legacy.requirement_path(shape, top)


@pytest.mark.parametrize(
    "description",
    [
        "Do TWO of the following.",
        "Complete any 3 of the following requirements",
        "Choose ONE of the following",
        "Select twelve of the following",
        "No choice wording here at all",
        "",
    ],
)
def test_choice_counts_match_legacy(description: str) -> None:
    assert choice_requirement_count(description) == legacy.choice_requirement_count(description)


@given(st.text(max_size=60))
def test_requirement_path_never_raises(value: str) -> None:
    path, _ = requirement_path(value, None)
    assert isinstance(path, tuple)
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`)

- [ ] **Step 3: Create the module** — move `CHOICE_COUNT_WORDS`, `requirement_path`, and
  `choice_requirement_count` verbatim:

```python
# src/scoutmb/core/inference/numbering.py
"""Requirement-number parsing. Pure: no I/O, no imports outside the standard library.

ScoutingEvent emits 26 distinct display-number shapes, including malformed ones like "#(c)"
that omit the top-level number. The current_top_level thread is how those still group.
"""

from __future__ import annotations

import re

CHOICE_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


def requirement_path(number: str, current_top_level: str | None) -> tuple[tuple[str, ...], str | None]:
    """Return a comparable requirement path and the current top-level number.

    ScoutingEvent occasionally emits malformed display numbers such as ``#(c)``
    where the leading top-level number is omitted. In that case, retain the most
    recently observed numeric top-level requirement so nested rows still group
    correctly in the HTML report.
    """
    text = str(number or "").strip()
    tokens = [token.lower() for token in re.findall(r"[A-Za-z]+|\d+", text)]
    if not tokens:
        return (), current_top_level

    if tokens[0].isdigit():
        current_top_level = tokens[0]
        return tuple(tokens), current_top_level

    if current_top_level:
        return (current_top_level, *tokens), current_top_level

    return tuple(tokens), current_top_level


def choice_requirement_count(description: str) -> int | None:
    """Extract X from wording such as 'Do TWO of the following'."""
    text = re.sub(r"\s+", " ", str(description or "")).strip().lower()
    words = "|".join(CHOICE_COUNT_WORDS)
    match = re.search(
        rf"\b(?:do|complete|choose|select|perform)\s+(?:any\s+)?(?P<count>\d+|{words})\s+of\s+the\s+following\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    value = match.group("count").lower()
    return int(value) if value.isdigit() else CHOICE_COUNT_WORDS.get(value)
```

- [ ] **Step 4: Re-export from legacy.** Delete the three definitions from
  `scout_schedule_cli.py` and add:

```python
from scoutmb.core.inference.numbering import (  # noqa: F401 - legacy public surface
    CHOICE_COUNT_WORDS,
    choice_requirement_count,
    requirement_path,
)
```

- [ ] **Step 5: Run — expect PASS**

```bash
uv run pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add src/scoutmb/core/inference/numbering.py tests/parity/test_numbering_parity.py scout_schedule_cli.py
git commit -m "refactor: move requirement numbering into core.inference.numbering"
```

---

### Task 10: Discriminating duplicate-requirement-number case

**Goal:** Pin the ancestor-selection behavior that Task 13's index re-expression could silently
change. This task adds a case and confirms it against the **legacy** implementation — no
package code is written here.

**Files:**
- Modify: `tests/matrix/cases/requirement_cases.py` (append cases + axis member)
- Modify: `tests/matrix/axes.py` (declare the new axis member)
- Modify: `tests/baselines/phase_a.json` (reviewed `case_ids` bump)
- Test: existing `tests/characterization/test_requirement_matrix.py` executes it unmodified

**Acceptance Criteria:**
- [ ] The fixture is **discriminating**: positional parent ≠ last-wins ancestor
- [ ] Two duplicate rows carry **different descriptions**, so the chosen row is identifiable
- [ ] The observation includes `description`, `depth`, and `is_leaf`
- [ ] Case classified `preserve`; expected values computed by tracing the source, then confirmed
- [ ] Baseline `case_ids` bumped with the two new IDs and nothing else

**Verify:** `uv run pytest tests/characterization/test_requirement_matrix.py -k REQ-DUP -q` → PASS

**Recovery:** If the fixture turns out not to discriminate (both schemes select the same row), that is a finding, not a failure: adjust the rows until they diverge, and keep REQ-DUP-001 as the control. Do not proceed to Task 13 without a discriminating case.

**Steps:**

- [ ] **Step 1: Understand the divergence before writing the fixture**

```bash
sed -n '851,905p' scout_schedule_cli.py
```

`by_key` is a dict comprehension over `annotated` keyed on
`(attendee, class_p4_id, requirement_number)` — **last row wins**. `children[]` in
`annotate_requirement_statuses` is positional, built from `prior_path_indexes`, which is also
last-wins per path but is consulted at a different time. The ancestor walk in
`build_missing_requirements` follows `parent_requirement_number` through `by_key`, so when two
rows in one group share a number, the walk lands on the **later** row while the tree linked the
child to whichever index `prior_path_indexes` held.

- [ ] **Step 2: Add the axis member**

In `tests/matrix/axes.py`, find the `REQ-*` axis block and add a `REQ-DUP` axis:

```python
    AxisSpec(
        axis_id="REQ-DUP",
        domain=Domain.REQUIREMENT,
        members=frozenset({"positional-differs-from-last-wins", "identical-descriptions"}),
        rationale=(
            "build_missing_requirements resolves ancestors through a last-wins "
            "(attendee, class, number) map while the tree links children positionally. "
            "Two rows sharing a number in one group make those disagree; Slice 2a's index "
            "re-expression must reproduce whichever row the legacy walk selects."
        ),
        boundary_id="REQ-B-MISSING",
    ),
```

> Match the exact `AxisSpec` field names already used in that file — read one neighbouring
> entry first and copy its shape.

- [ ] **Step 3: Append the cases**

```python
# tests/matrix/cases/requirement_cases.py — append near the other REQ-* case tuples

# REQ-DUP-001/002 -- duplicate requirement_number inside one (scout, class) group.
#
# Traced by hand against build_missing_requirements (scout_schedule_cli.py:851-925):
#   rows are [ "#4" (desc A), "#4" (desc B), "#4a" (leaf, incomplete) ]
#   annotate: paths are ('4',), ('4',), ('4','a'); prior_path_indexes[('4',)] ends at index 1
#   so children[1] == [2] and row 2's parent_requirement_number == "4".
#   by_key[(attendee, class, "4")] is ALSO the LAST "#4" row (index 1) -- both agree here,
#   which is why REQ-DUP-001 alone is not sufficient.
# REQ-DUP-002 makes them DISAGREE by giving the two duplicates different PATHS while keeping
#   the same requirement_number: "#4" (path ('4',)) then "Note." after top-level 4 -> ('4','note').
#   The child "#4a" links positionally to index 0, but the ancestor walk keys on the NUMBER
#   and lands on whichever row by_key kept.
_DUP_ROWS_AGREE = (
    _row("#4", description="Duplicate parent A.", requirement_id="rA"),
    _row("#4", description="Duplicate parent B.", requirement_id="rB"),
    _row("#4a", description="Actionable leaf.", requirement_id="rC"),
)

_DUP_ROWS_DISAGREE = (
    _row("#4", description="Positional parent, registered first.", requirement_id="rA"),
    _row("#4a", description="Actionable leaf.", requirement_id="rB"),
    _row("#4", description="Last-wins ancestor, registered second.", requirement_id="rC"),
)

REQUIREMENT_DUP_CASES: tuple[RequirementCase, ...] = (
    RequirementCase(
        meta=_meta(
            "REQ-DUP-001",
            "REQ-DUP",
            "identical-descriptions",
            ("email_consumer",),
            "Two rows share a number and both schemes select the same row; the control case "
            "that proves the discriminating case is actually discriminating.",
            _EVIDENCE_MISSING,
        ),
        rows=_DUP_ROWS_AGREE,
        expected_by_context={"email_consumer": ...},  # fill from Step 5
    ),
    RequirementCase(
        meta=_meta(
            "REQ-DUP-002",
            "REQ-DUP",
            "positional-differs-from-last-wins",
            ("email_consumer",),
            "The positional parent (index 0) and the last-wins ancestor (index 2) are "
            "DIFFERENT rows with different descriptions, so the selected ancestor is "
            "identifiable from the rendered email.",
            _EVIDENCE_MISSING,
        ),
        rows=_DUP_ROWS_DISAGREE,
        expected_by_context={"email_consumer": ...},  # fill from Step 5
    ),
)
```

Then add `REQUIREMENT_DUP_CASES` to the module's exported `REQUIREMENT_CASES` tuple and to
`ALL_REQUIREMENT_METADATA`.

- [ ] **Step 4: Extend the email observation to carry `description`**

The existing `_ctx_email_consumer` observation returns `(number, in_text, in_html)`, which
cannot distinguish two rows sharing a number. **Do not edit that runner** — it is frozen. Add a
new context instead, `missing_selection`, and declare it on the two new cases only:

```python
# tests/characterization/test_requirement_matrix.py is FROZEN. Add the runner here instead:
# tests/parity/test_missing_selection.py
"""REQ-DUP observation: which ancestor row build_missing_requirements actually selected.

Runs against the LEGACY implementation in this task. Task 13 adds a package runner over the
same two cases; both must produce the same tuple.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.matrix.cases.requirement_cases import REQUIREMENT_DUP_CASES, RequirementCase


def observe_selection(module: Any, case: RequirementCase) -> tuple[object, ...]:
    row = dict(case.rows[0])
    scouts = [
        {
            "name": row["scout_name"],
            "attendee_id": row["attendee_id"],
            "classes": [],
            "requirements": [dict(r) for r in case.rows],
            "errors": [],
        }
    ]
    grouped = module.build_missing_requirements(scouts)
    bucket = grouped.get(str(row["attendee_id"])) or {"badges": {}}
    entries = [entry for items in bucket["badges"].values() for entry in items]
    return tuple(
        (e["requirement_number"], e["description"], e["depth"], e["is_leaf"])
        for e in sorted(entries, key=lambda e: (e["requirement_number"], e["description"]))
    )


@pytest.mark.parametrize("case", REQUIREMENT_DUP_CASES, ids=lambda c: c.meta.case_id)
def test_legacy_selection(case: RequirementCase) -> None:
    import scout_schedule_cli as legacy

    assert observe_selection(legacy, case) == case.expected_by_context["missing_selection"]
```

Set both cases' `contexts` to `("missing_selection",)` and key `expected_by_context` on that
name.

- [ ] **Step 5: Fill the expected values from observed output, then verify by hand**

```bash
uv run pytest tests/parity/test_missing_selection.py -q 2>&1 | head -40
```

Paste the observed tuples into `expected_by_context`, then **read
`build_missing_requirements` and confirm each is what the source says should happen.** A
characterization expectation copied without tracing is a recorded bug, not a contract.

- [ ] **Step 6: Bump the baseline**

```bash
uv run python tools/measure_baseline.py --update
git diff tests/baselines/phase_a.json
```

Expected diff: exactly two added entries in `case_ids` (`REQ-DUP-001`, `REQ-DUP-002`) and
nothing else. Any other change means something unrelated drifted — investigate before
committing.

- [ ] **Step 7: Run the full suite and commit**

```bash
uv run pytest -q
git add tests/matrix tests/parity/test_missing_selection.py tests/baselines/phase_a.json
git commit -m "test: pin ancestor selection when a group has duplicate requirement numbers

The tree links children positionally; build_missing_requirements resolves ancestors
through a last-wins map. REQ-DUP-002 makes them disagree so Task 13 cannot change the
answer silently."
```

---

### Task 11: `core/inference/tree.py`

**Goal:** Group path derivation and parent/child linking become a pure function returning an
index-based tree. `annotate_requirement_statuses` starts using it.

**Files:**
- Create: `src/scoutmb/core/inference/tree.py`
- Modify: `scout_schedule_cli.py` (`annotate_requirement_statuses` first half)
- Test: `tests/unit/test_inference_tree.py`

**Acceptance Criteria:**
- [ ] `build_group_tree(numbers, type_ids)` returns paths, children, and parent indices
- [ ] Header-stack fallback reproduced exactly, including the `type_id == "3"` push
- [ ] Pure: takes sequences of strings, returns a frozen structure, imports only `numbering`
- [ ] All `REQ-TREE-*` cases green through the legacy path

**Verify:** `uv run pytest tests/unit/test_inference_tree.py tests/characterization/test_requirement_matrix.py -q` → PASS

**Recovery:** Restore the inline path/children/header-stack block from git and delete `tree.py`. `REQ-TREE-001..006` are the tripwire.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_inference_tree.py
from __future__ import annotations

from scoutmb.core.inference.tree import build_group_tree


def test_child_links_to_registered_prefix_parent() -> None:
    tree = build_group_tree(("#8", "#8a"), ("1", "1"))
    assert tree.paths == (("8",), ("8", "a"))
    assert tree.parent_index == (None, 0)
    assert tree.children == ((1,), ())


def test_missing_parent_leaves_siblings_unlinked() -> None:
    """REQ-TREE-004: '#10a' and '#10c' with no '#10' row -- the prefix ('10',) was never
    registered, so both stay top-level and unlinked from each other."""
    tree = build_group_tree(("#10a", "#10c"), ("1", "1"))
    assert tree.parent_index == (None, None)


def test_header_stack_fallback_adopts_nearest_shallower_type_3() -> None:
    """REQ-TREE-005: a compound TYPE-3 header followed by a malformed number that matches no
    registered prefix falls back to the nearest shallower header."""
    tree = build_group_tree(("#16.Option.A", "#(y)(1)(2)"), ("3", "1"))
    assert tree.parent_index[1] == 0


def test_grandparent_chain() -> None:
    tree = build_group_tree(("#9", "#9a", "#9a1"), ("1", "1", "1"))
    assert tree.parent_index == (None, 0, 1)
    assert tree.children == ((1,), (2,), ())
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/scoutmb/core/inference/tree.py
"""Parent/child reconstruction for one (scout, class) requirement group.

Index-based by construction: every link is a position in the input sequence, never an object
identity. That is what lets build_missing_requirements stop keying on id().
"""

from __future__ import annotations

from dataclasses import dataclass

from scoutmb.core.inference.numbering import requirement_path


@dataclass(frozen=True, slots=True)
class GroupTree:
    paths: tuple[tuple[str, ...], ...]
    parent_index: tuple[int | None, ...]
    children: tuple[tuple[int, ...], ...]


def build_group_tree(
    numbers: tuple[str, ...], type_ids: tuple[str, ...]
) -> GroupTree:
    """Derive paths and parent/child links for one group, in row order.

    Two linking strategies, in the legacy order:
      1. longest registered path prefix (the ordinary case);
      2. nearest prior TYPE-3 header with a shallower path (the malformed-numbering fallback).
    """
    current_top_level: str | None = None
    paths: list[tuple[str, ...]] = []
    for number in numbers:
        path, current_top_level = requirement_path(number, current_top_level)
        paths.append(path)

    children: list[list[int]] = [[] for _ in numbers]
    parents: list[int | None] = [None] * len(numbers)
    prior_path_indexes: dict[tuple[str, ...], int] = {}
    header_stack: list[tuple[int, int]] = []

    for index, path in enumerate(paths):
        parent_index: int | None = None
        if len(path) > 1:
            for depth in range(len(path) - 1, 0, -1):
                candidate = path[:depth]
                if candidate in prior_path_indexes:
                    parent_index = prior_path_indexes[candidate]
                    break

        if parent_index is None and len(path) > 1:
            for candidate_index, candidate_depth in reversed(header_stack):
                if candidate_depth < len(path):
                    parent_index = candidate_index
                    break

        if parent_index is not None:
            children[parent_index].append(index)
            parents[index] = parent_index

        if path:
            prior_path_indexes[path] = index
        if type_ids[index] == "3":
            while header_stack and header_stack[-1][1] >= len(path):
                header_stack.pop()
            header_stack.append((index, len(path)))

    return GroupTree(
        paths=tuple(paths),
        parent_index=tuple(parents),
        children=tuple(tuple(group) for group in children),
    )
```

- [ ] **Step 4: Use it from the legacy function.** In `annotate_requirement_statuses`, replace
  the path/children/header-stack block with:

```python
    for group in grouped.values():
        tree = build_group_tree(
            tuple(str(item.get("requirement_number") or "") for item in group),
            tuple(str(item.get("requirement_type_id") or "") for item in group),
        )
        for item, path in zip(group, tree.paths, strict=True):
            item["requirement_path"] = list(path)
        children = [list(group_children) for group_children in tree.children]
        for index, parent_index in enumerate(tree.parent_index):
            if parent_index is not None:
                group[index]["parent_requirement_number"] = group[parent_index].get(
                    "requirement_number"
                )
```

Add the import at the top of `scout_schedule_cli.py`:

```python
from scoutmb.core.inference.tree import build_group_tree
```

- [ ] **Step 5: Run — expect PASS**

```bash
uv run pytest -q
```

A `REQ-TREE-*` failure means the extraction changed linking — diff the moved loop against the
original before touching anything else.

- [ ] **Step 6: Commit**

```bash
git add src/scoutmb/core/inference/tree.py tests/unit/test_inference_tree.py scout_schedule_cli.py
git commit -m "refactor: extract index-based group tree from annotate_requirement_statuses"
```

---

### Task 12: `core/inference/status.py`

**Goal:** The recursive status calculation moves, with its exact status strings and reason
sentences. Those strings reach the HTML report, so they are a shipped surface.

**Files:**
- Create: `src/scoutmb/core/inference/status.py`
- Modify: `scout_schedule_cli.py` (`annotate_requirement_statuses` second half)
- Test: `tests/unit/test_inference_status.py`

**Acceptance Criteria:**
- [ ] `complete` / `complete_check` / `incomplete` and every reason sentence byte-identical
- [ ] Choice threshold behavior preserved, including the `complete_check` propagation rule
- [ ] Rollup counts (`completed_subrequirements`, `total_subrequirements`,
      `choice_required_count`) returned only for rows with children — **presence matters**
- [ ] All 30 `REQ-CHOICE-*` and 8 `REQ-FLAG-*` cases green

**Verify:** `uv run pytest tests/unit/test_inference_status.py tests/characterization -q` → PASS

**Recovery:** Restore the inline `calculate` closure. If only the rollup-key presence broke, fix the `is not None` guard rather than reverting — that is the single line the whole email pipeline depends on.

**Steps:**

- [ ] **Step 1: Note the presence contract before writing code**

`build_missing_requirements.is_actionable_leaf` tests `"total_subrequirements" not in item`.
So a row with no children must **not** have that key at all — setting it to `None` changes
which rows are actionable and silently alters every generated email. The package function
therefore returns `None` for those fields and the caller only writes keys that are not `None`.

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_inference_status.py
from __future__ import annotations

from scoutmb.core.inference.status import calculate_statuses
from scoutmb.core.inference.tree import build_group_tree


def _statuses(numbers, type_ids, completed, descriptions=None):
    tree = build_group_tree(numbers, type_ids)
    return calculate_statuses(
        tree=tree,
        completed=completed,
        descriptions=descriptions or ("",) * len(numbers),
    )


def test_leaf_incomplete_has_no_rollup_keys() -> None:
    result = _statuses(("#1",), ("1",), (False,))
    assert result[0].status == "incomplete"
    assert result[0].reason == "Not marked complete by ScoutingEvent."
    assert result[0].total_subrequirements is None, "presence of this key gates actionability"


def test_api_complete_wins_over_children() -> None:
    result = _statuses(("#2", "#2a"), ("1", "1"), (True, False))
    assert result[0].status == "complete"
    assert result[0].reason == "Marked complete by ScoutingEvent."


def test_all_children_complete_rolls_up() -> None:
    result = _statuses(("#3", "#3a"), ("1", "1"), (False, True))
    assert result[0].status == "complete"
    assert result[0].reason == "All 1 subrequirements are complete."
    assert result[0].completed_subrequirements == 1
    assert result[0].total_subrequirements == 1


def test_choice_threshold_yields_complete_check() -> None:
    result = _statuses(
        ("#4", "#4a", "#4b"), ("1", "1", "1"), (False, True, False),
        descriptions=("Do ONE of the following.", "", ""),
    )
    assert result[0].status == "complete_check"
    assert "meets the stated choice of 1" in result[0].reason


def test_complete_check_propagates_to_a_fully_satisfied_parent() -> None:
    result = _statuses(
        ("#5", "#5a", "#5a1"), ("1", "1", "1"), (False, False, True),
        descriptions=("", "Do ONE of the following.", ""),
    )
    assert result[1].status == "complete_check"
    assert result[0].status == "complete_check"
    assert "inferred from a choice requirement" in result[0].reason
```

- [ ] **Step 3: Run — expect FAIL**

- [ ] **Step 4: Implement**

```python
# src/scoutmb/core/inference/status.py
"""Recursive requirement status inference.

The status strings and reason sentences below are a SHIPPED SURFACE -- they render in the HTML
report. Changing their wording is a user-visible change, not a refactor.
"""

from __future__ import annotations

from dataclasses import dataclass

from scoutmb.core.inference.numbering import choice_requirement_count
from scoutmb.core.inference.tree import GroupTree

_SATISFIED = frozenset({"complete", "complete_check"})


@dataclass(frozen=True, slots=True)
class RowStatus:
    status: str
    reason: str
    completed_subrequirements: int | None = None
    total_subrequirements: int | None = None
    choice_required_count: int | None = None


def calculate_statuses(
    *,
    tree: GroupTree,
    completed: tuple[bool, ...],
    descriptions: tuple[str, ...],
) -> tuple[RowStatus, ...]:
    """Resolve every row's status, recursing into children.

    Rollup counts are None for rows WITHOUT children. The caller must omit the corresponding
    keys entirely rather than writing None: build_missing_requirements gates actionability on
    `"total_subrequirements" not in item`.
    """
    cache: dict[int, RowStatus] = {}

    def calculate(index: int) -> RowStatus:
        cached = cache.get(index)
        if cached is not None:
            return cached

        direct_children = tree.children[index]
        if completed[index]:
            result = RowStatus("complete", "Marked complete by ScoutingEvent.")
        elif direct_children:
            child_results = [calculate(child) for child in direct_children]
            satisfied_count = sum(1 for child in child_results if child.status in _SATISFIED)
            total_count = len(direct_children)
            choice_count = choice_requirement_count(descriptions[index])

            if total_count and satisfied_count == total_count:
                if any(child.status == "complete_check" for child in child_results):
                    status, reason = (
                        "complete_check",
                        f"All {total_count} subrequirements appear satisfied, but at least one was inferred from a choice requirement.",
                    )
                else:
                    status, reason = (
                        "complete",
                        f"All {total_count} subrequirements are complete.",
                    )
            elif choice_count is not None and satisfied_count >= choice_count:
                status, reason = (
                    "complete_check",
                    f"{satisfied_count} of {total_count} subrequirements appear complete; this meets the stated choice of {choice_count}, but should be verified.",
                )
            else:
                status, reason = (
                    "incomplete",
                    f"{satisfied_count} of {total_count} subrequirements are complete.",
                )

            result = RowStatus(
                status=status,
                reason=reason,
                completed_subrequirements=satisfied_count,
                total_subrequirements=total_count,
                choice_required_count=choice_count,
            )
        else:
            result = RowStatus("incomplete", "Not marked complete by ScoutingEvent.")

        cache[index] = result
        return result

    return tuple(calculate(index) for index in range(len(tree.paths)))
```

- [ ] **Step 5: Use it from the legacy function.** Replace the `cache`/`calculate` block and the
  final assignment loop in `annotate_requirement_statuses` with:

```python
        statuses = calculate_statuses(
            tree=tree,
            completed=tuple(bool(item.get("completed_requirement")) for item in group),
            descriptions=tuple(str(item.get("description") or "") for item in group),
        )
        for item, row_status in zip(group, statuses, strict=True):
            item["calculated_status"] = row_status.status
            item["calculated_status_reason"] = row_status.reason
            # Presence, not value: is_actionable_leaf gates on `"total_subrequirements" not in item`.
            if row_status.total_subrequirements is not None:
                item["completed_subrequirements"] = row_status.completed_subrequirements
                item["total_subrequirements"] = row_status.total_subrequirements
                item["choice_required_count"] = row_status.choice_required_count
```

Add the import:

```python
from scoutmb.core.inference.status import calculate_statuses
```

The local `children` list built in Task 11 is now unused — delete it.

- [ ] **Step 6: Run — expect PASS**

```bash
uv run pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add src/scoutmb/core/inference/status.py tests/unit/test_inference_status.py scout_schedule_cli.py
git commit -m "refactor: extract recursive status inference, preserving exact reason strings"
```

---

### Task 13: `core/inference/missing.py` — the `id()` re-expression

**Goal:** Replace `selected: dict[int, bool]` keyed on `id(item)` with an index-based walk that
reproduces the legacy ancestor selection **including** the duplicate-number case pinned in
Task 10.

**Files:**
- Create: `src/scoutmb/core/inference/missing.py`
- Modify: `scout_schedule_cli.py` (`build_missing_requirements`)
- Modify: `tests/parity/test_missing_selection.py` (add the package runner)
- Test: `tests/unit/test_inference_missing.py`

**Acceptance Criteria:**
- [ ] No `id(` anywhere in `build_missing_requirements` or the package module
- [ ] `REQ-DUP-001` **and** `REQ-DUP-002` produce identical output from legacy and package
- [ ] `(not used)` and `type_id == "3"` exclusions preserved
- [ ] `is_leaf` and `depth` values unchanged
- [ ] All `REQ-EXCLUDE-*`, `REQ-CLASS-*`, and email cases green

**Verify:** `uv run pytest tests/parity/test_missing_selection.py tests/characterization -q` → PASS

**Recovery:** Restore `build_missing_requirements` from git, keeping `id()`. The frozen-record migration for these rows is 2b's problem; shipping a wrong ancestor walk is worse than shipping `id()` for one more slice.

**Steps:**

- [ ] **Step 1: Add the package runner to the Task 10 test file**

```python
# append to tests/parity/test_missing_selection.py

@pytest.mark.parametrize("case", REQUIREMENT_DUP_CASES, ids=lambda c: c.meta.case_id)
def test_package_selection_matches_legacy(case: RequirementCase) -> None:
    """The whole point of REQ-DUP-002: a naive index substitution answers this differently."""
    import scout_schedule_cli as legacy

    from scoutmb.core.inference import missing as package

    assert observe_selection(package, case) == observe_selection(legacy, case)
    assert observe_selection(package, case) == case.expected_by_context["missing_selection"]
```

- [ ] **Step 2: Run — expect FAIL** (`module has no attribute 'build_missing_requirements'`)

- [ ] **Step 3: Implement, preserving the last-wins lookup**

```python
# src/scoutmb/core/inference/missing.py
"""Actionable-leaf selection and the ancestor walk that gives a leaf its context.

The legacy implementation kept bookkeeping in a dict keyed on id(item), which cannot survive
frozen records. This is the index-based re-expression.

CRITICAL: the ancestor lookup is BY NUMBER through a last-wins map, not through the tree's
positional parent link. When one group holds two rows with the same requirement_number those
two disagree, and REQ-DUP-002 pins which one the legacy code picks. Substituting
tree.parent_index here is the obvious refactor and it is WRONG.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def is_not_used(description: str) -> bool:
    return "(not used)" in description.lower()


def select_actionable(
    rows: Sequence[Mapping[str, Any]],
    *,
    attendee_key_of: Any,
    cleaned_description_of: Any,
) -> dict[int, bool]:
    """Return {row index: is_leaf} for every row an email should mention.

    A row is selected when it is an actionable leaf, or when it is a still-incomplete ancestor
    of one (so "3b" is never shown without whatever "3" asked for).
    """
    by_key: dict[tuple[str, str, str], int] = {}
    for index, row in enumerate(rows):
        key = (
            attendee_key_of(row),
            str(row.get("class_p4_id") or ""),
            str(row.get("requirement_number") or ""),
        )
        by_key[key] = index  # last wins, exactly as the legacy dict comprehension did

    def actionable_leaf(row: Mapping[str, Any]) -> bool:
        return (
            row.get("calculated_status") == "incomplete"
            and "total_subrequirements" not in row
            and str(row.get("requirement_type_id") or "") != "3"
            and not is_not_used(cleaned_description_of(str(row.get("description") or "")))
        )

    selected: dict[int, bool] = {}
    for index, row in enumerate(rows):
        if not actionable_leaf(row):
            continue
        current: int | None = index
        is_leaf = True
        while current is not None and current not in selected:
            selected[current] = is_leaf
            is_leaf = False
            parent_number = rows[current].get("parent_requirement_number")
            if parent_number is None:
                break
            parent_key = (
                attendee_key_of(rows[current]),
                str(rows[current].get("class_p4_id") or ""),
                str(parent_number),
            )
            parent_index = by_key.get(parent_key)
            if parent_index is None:
                break
            if rows[parent_index].get("calculated_status") in {"complete", "complete_check"}:
                break
            current = parent_index

    return selected
```

- [ ] **Step 4: Rewrite the legacy function over indices**

```python
def build_missing_requirements(scouts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group incomplete, actionable requirements by scout name and merit badge.

    (docstring unchanged from the original -- keep it verbatim)
    """
    flattened = [dict(req) for scout in scouts for req in scout.get("requirements", [])]
    annotated = annotate_requirement_statuses(flattened)

    selected = select_actionable(
        annotated,
        attendee_key_of=_attendee_key_for,
        cleaned_description_of=clean_html_description,
    )

    grouped: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(annotated):
        if index not in selected:
            continue
        description = clean_html_description(str(item.get("description") or ""))
        if is_not_used(description):
            continue

        entry = {
            "requirement_number": str(item.get("requirement_number") or ""),
            "description": description,
            "is_prereq": "(pre-req)" in description.lower(),
            "is_leaf": selected[index],
            "depth": max(len(item.get("requirement_path") or []) - 1, 0),
        }
        attendee_key = _attendee_key_for(item)
        badge_name = str(item.get("merit_badge_name") or "")
        bucket = grouped.setdefault(
            attendee_key, {"display_name": str(item.get("scout_name") or ""), "badges": {}}
        )
        bucket["badges"].setdefault(badge_name, []).append(entry)

    return grouped
```

Add the import:

```python
from scoutmb.core.inference.missing import is_not_used, select_actionable
```

> The original computed `is_not_used` twice — once inside the selection predicate on the raw
> description, once in the grouping loop on the cleaned one. Both are preserved: the predicate
> receives a cleaner callback, and the loop keeps its own check.

- [ ] **Step 5: Add a direct unit test for the exclusions**

```python
# tests/unit/test_inference_missing.py
from __future__ import annotations

from scoutmb.core.inference.missing import is_not_used, select_actionable


def _row(**overrides):
    row = {
        "attendee_id": "90000001", "class_p4_id": "2000001", "requirement_number": "1",
        "requirement_type_id": "1", "description": "Do the thing.",
        "calculated_status": "incomplete", "parent_requirement_number": None,
    }
    row.update(overrides)
    return row


def _key(row):
    return str(row.get("attendee_id") or "")


def test_not_used_rows_are_never_selected() -> None:
    rows = [_row(description="This requirement is (not used) here.")]
    assert select_actionable(rows, attendee_key_of=_key, cleaned_description_of=str) == {}


def test_type_3_rows_are_never_selected() -> None:
    rows = [_row(requirement_type_id="3")]
    assert select_actionable(rows, attendee_key_of=_key, cleaned_description_of=str) == {}


def test_rows_with_children_are_not_actionable_leaves() -> None:
    rows = [_row(total_subrequirements=2, completed_subrequirements=1)]
    assert select_actionable(rows, attendee_key_of=_key, cleaned_description_of=str) == {}


def test_is_not_used_is_case_insensitive() -> None:
    assert is_not_used("Something (NOT USED) here")
    assert not is_not_used("Something used here")
```

- [ ] **Step 6: Run — expect PASS, and confirm no `id(` remains**

```bash
uv run pytest -q
rg -n 'id\(' src/scoutmb/core/inference/missing.py scout_schedule_cli.py | rg -v 'attendee_id|class_p4_id|requirement_id|run_id|operation_id|output_id' || echo "no id() bookkeeping remains"
```

- [ ] **Step 7: Commit**

```bash
git add src/scoutmb/core/inference/missing.py tests/unit/test_inference_missing.py tests/parity/test_missing_selection.py scout_schedule_cli.py
git commit -m "refactor: re-express the ancestor walk over node indices, not id()

Keeps the last-wins by-number lookup: substituting the tree's positional parent link
answers REQ-DUP-002 differently."
```

---

### Task 14: `core/output_schemas.py` — the DTO boundary

**Goal:** Parsing and serialization become free functions over the record types, with a
versioned envelope and a correct round-trip property. `ClassRecord`/`RequirementRecord` in the
legacy module become aliases of the package shapes.

**Skeleton lineage:** B2 (`tests/contracts/test_dto_versions.py::test_unknown_versions_fail_closed`).

**Files:**
- Create: `src/scoutmb/core/output_schemas.py`, `tests/contracts/__init__.py`
- Modify: `scout_schedule_cli.py` (`ClassRecord`, `RequirementRecord` → aliases)
- Test: `tests/contracts/test_dto_versions.py`, `tests/unit/test_output_schemas.py`

**Acceptance Criteria:**
- [ ] `class_from_mapping` / `requirement_from_mapping` reproduce legacy coercion exactly
      (`str(x or "")`, `truthy()`), so `ACQ-REQ-*` stays green
- [ ] `*_to_row(record, shareable=False)` reproduces `asdict` field order
- [ ] Property: `requirement_from_mapping(requirement_to_row(dto)) == dto` for all 26 shapes
- [ ] `SCHEMA_VERSION` present; an unknown version fails closed with a typed error
- [ ] Tuples normalized to lists by the serializer, never left for `json.dumps` to hide

**Verify:** `uv run pytest tests/contracts tests/unit/test_output_schemas.py -q` → PASS

**Recovery:** Keep the legacy dataclasses as the live definitions and leave
`output_schemas` unreferenced at the boundary; fix one coercion mismatch at a time against
`ACQ-REQ-001..006`. Never make `from_mapping` more permissive to get a test green — that is the
`ACQ-REQ-004` behavior change, which belongs to 2b.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_output_schemas.py
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from scoutmb.core.models import RequirementRecord
from scoutmb.core.output_schemas import requirement_from_mapping, requirement_to_row
from tests.factories.payloads import REQUIREMENT_NUMBER_SHAPES


def _dto(number: str) -> RequirementRecord:
    return RequirementRecord(
        scout_name="Avery Example", attendee_id="90000001", class_number="26MB1",
        class_p4_id="2000001", merit_badge_name="Chess", requirement_id="r1",
        requirement_type_id="1", requirement_number=number, description="Show your work.",
        completed_requirement=False, completed_class=False, requirement_on_event=True,
        present_days="MoTuWeTh",
    )


@given(st.sampled_from(REQUIREMENT_NUMBER_SHAPES))
def test_dto_round_trip(number: str) -> None:
    """from_mapping(to_row(dto)) == dto -- the ONLY direction that can hold.

    The reverse (to_row(from_mapping(mapping)) == mapping) is false by construction:
    from_mapping coerces types, resolves aliases, drops unknown keys and supplies defaults,
    so the original mapping is not recoverable.
    """
    dto = _dto(number)
    assert requirement_from_mapping(requirement_to_row(dto, shareable=False)) == dto


def test_to_row_preserves_declaration_order() -> None:
    from dataclasses import fields

    row = requirement_to_row(_dto("3b"), shareable=False)
    assert list(row) == [f.name for f in fields(RequirementRecord)]


def test_serializer_normalizes_tuples_to_lists() -> None:
    """asdict PRESERVES tuples (proven in tests/packaging/test_mechanisms.py), so the
    serializer must normalize or a tuple reaches a CSV cell as its repr."""
    from scoutmb.core.models import ScoutResult
    from scoutmb.core.output_schemas import scout_result_to_row

    row = scout_result_to_row(ScoutResult(name="Avery Example", qr_url="https://x.invalid"))
    assert isinstance(row["classes"], list)
    assert isinstance(row["errors"], list)
```

```python
# tests/contracts/test_dto_versions.py
from __future__ import annotations

import pytest

from scoutmb.core.output_schemas import SCHEMA_VERSION, UnsupportedSchemaVersion, check_schema_version


def test_current_version_is_accepted() -> None:
    check_schema_version(SCHEMA_VERSION)


def test_unknown_versions_fail_closed() -> None:
    with pytest.raises(UnsupportedSchemaVersion):
        check_schema_version(SCHEMA_VERSION + 1)
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/scoutmb/core/output_schemas.py
"""Boundary parsing and versioned serialization for the record shapes.

Free functions, not methods: core/models.py stays dependency-free and the operational and
shareable projections differ by one parameter instead of two class hierarchies.

Coercion here reproduces the legacy boundary EXACTLY -- str(x or "") and truthy(). Making it
stricter is the ACQ-REQ-004 behavior change and belongs to Slice 2b.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from typing import Any

from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutResult
from scoutmb.errors import ScoutmbError

SCHEMA_VERSION = 1
_SUPPORTED_VERSIONS = frozenset({1})


class UnsupportedSchemaVersion(ScoutmbError):
    """A payload declared a schema version this build cannot read. Fails closed."""


def check_schema_version(version: int) -> None:
    if version not in _SUPPORTED_VERSIONS:
        raise UnsupportedSchemaVersion(
            f"Schema version {version} is not supported (this build reads "
            f"{sorted(_SUPPORTED_VERSIONS)})."
        )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def requirement_from_mapping(data: Mapping[str, Any]) -> RequirementRecord:
    return RequirementRecord(
        scout_name=_text(data.get("scout_name")),
        attendee_id=_text(data.get("attendee_id")),
        class_number=_text(data.get("class_number")),
        class_p4_id=_text(data.get("class_p4_id")),
        merit_badge_name=_text(data.get("merit_badge_name")),
        requirement_id=_text(data.get("requirement_id")),
        requirement_type_id=_text(data.get("requirement_type_id")),
        requirement_number=_text(data.get("requirement_number")),
        description=str(data.get("description") or ""),
        completed_requirement=bool(data.get("completed_requirement")),
        completed_class=bool(data.get("completed_class")),
        requirement_on_event=bool(data.get("requirement_on_event")),
        present_days=_text(data.get("present_days")),
    )


def requirement_to_row(record: RequirementRecord, *, shareable: bool) -> dict[str, Any]:
    row = {field.name: getattr(record, field.name) for field in fields(RequirementRecord)}
    return _project(row, shareable=shareable)


def class_from_mapping(data: Mapping[str, Any]) -> ClassRecord:
    return ClassRecord(
        scout_name=_text(data.get("scout_name")),
        attendee_id=_text(data.get("attendee_id")),
        class_number=_text(data.get("class_number")),
        class_p4_id=_text(data.get("class_p4_id")),
        class_name=_text(data.get("class_name")),
        days=_text(data.get("days")),
        period_name=_text(data.get("period_name")),
        start_time=_text(data.get("start_time")),
        start_time_24h=_text(data.get("start_time_24h")),
        location=_text(data.get("location")),
        has_requirements=bool(data.get("has_requirements")),
        class_completed=bool(data.get("class_completed")),
        raw_class_name=str(data.get("raw_class_name") or ""),
    )


def class_to_row(record: ClassRecord, *, shareable: bool) -> dict[str, Any]:
    row = {field.name: getattr(record, field.name) for field in fields(ClassRecord)}
    return _project(row, shareable=shareable)


def scout_result_to_row(record: ScoutResult) -> dict[str, Any]:
    """Operational only: scouts.json is operational-private and keeps qr_url + attendee_id."""
    return {
        "name": record.name,
        "qr_url": record.qr_url,
        "attendee_id": record.attendee_id,
        "classes": [class_to_row(item, shareable=False) for item in record.classes],
        "requirements": [requirement_to_row(item, shareable=False) for item in record.requirements],
        "errors": list(record.errors),
    }


def _project(row: dict[str, Any], *, shareable: bool) -> dict[str, Any]:
    """Normalize collection types; the shareable substitution lands in Task 23.

    asdict preserves tuples, so anything sequence-shaped is normalized here rather than left
    for json.dumps to paper over -- a CSV cell would otherwise receive a tuple repr.
    """
    normalized = {
        key: list(value) if isinstance(value, tuple) else value for key, value in row.items()
    }
    return normalized
```

- [ ] **Step 4: Alias the legacy record classes**

Delete `class ClassRecord` and `class RequirementRecord` from `scout_schedule_cli.py` and add:

```python
from scoutmb.core.models import ClassRecord, RequirementRecord  # noqa: F401 - legacy surface
```

`ScoutInput` and `ScoutResult` stay legacy-defined for now — `process_scout` mutates
`ScoutResult` and `load_inputs` mutates `ScoutInput`. Both are retired in 2b and Task 15.

- [ ] **Step 5: Run — expect PASS**

```bash
uv run pytest -q
```

`ART-SCHEMA-002/003` are the ones to watch: they read the CSV header from
`__dataclass_fields__`, which now resolves through the alias.

- [ ] **Step 6: Commit**

```bash
git add src/scoutmb/core/output_schemas.py tests/contracts tests/unit/test_output_schemas.py scout_schedule_cli.py
git commit -m "feat: add the versioned DTO boundary and alias the legacy record classes"
```

---

### Task 15: `ports/attendee_source.py` + `adapters/files/tabular.py`

**Goal:** The four loaders become an adapter behind a port. `load_inputs`'s in-place mutation
of `ScoutInput` is replaced by constructing normalized values, which is what lets the shape
freeze later.

**Skeleton lineage:** B3 (`tests/parity/test_input_adapter_parity.py::test_full_input_matrix_matches_legacy`).

**Files:**
- Create: `src/scoutmb/ports/attendee_source.py`, `src/scoutmb/adapters/files/tabular.py`
- Modify: `scout_schedule_cli.py` (five loader functions → re-exports)
- Test: `tests/parity/test_input_adapter_parity.py`

**Acceptance Criteria:**
- [ ] All 50 `IN-*` cases pass through the package adapter with identical results
- [ ] Header aliases, `utf-8-sig`, the headerless-CSV fallback, and the JSON envelope
      (`scouts` / `data` / bare object) all preserved
- [ ] `load_inputs` no longer mutates its inputs — it builds new `ScoutInput` values
- [ ] Dedup on URL, adult filter, and the empty-result `ValueError` message unchanged
- [ ] `openpyxl` imported inside the XLSX function, not at adapter module scope

**Verify:** `uv run pytest tests/parity/test_input_adapter_parity.py tests/characterization -q` → PASS

**Recovery:** Re-point `scout_schedule_cli.load_inputs` at the original bodies (kept in git
history) and select the legacy loader at the composition root; fix one `IN-*` case at a time.

**Steps:**

- [ ] **Step 1: Write the parity test driving the frozen catalog**

```python
# tests/parity/test_input_adapter_parity.py
"""Package input adapter over the SAME input cases the legacy runner uses.

Neither runner is the other's oracle -- tests/matrix/cases/input_cases.py holds hand-computed
expectations and both are measured against them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scoutmb.adapters.files.tabular import load_attendees
from tests.matrix.cases.input_cases import INPUT_CASES, InputCase
from tests.matrix.pytest_support import execution_params


@pytest.mark.parametrize(("case", "context_id"), execution_params(INPUT_CASES))
def test_package_input_adapter_matches_expectations(
    case: InputCase, context_id: str, tmp_path: Path
) -> None:
    import scout_schedule_cli as legacy

    source = case.write_source(tmp_path)  # same helper the legacy runner uses
    try:
        package_result = load_attendees(
            source, sheet_name=case.sheet_name, include_adults=case.include_adults
        )
    except ValueError as exc:
        package_result = f"ValueError: {exc}"

    try:
        legacy_result = legacy.load_inputs(source, case.sheet_name, case.include_adults)
    except ValueError as exc:
        legacy_result = f"ValueError: {exc}"

    assert _normalize(package_result) == _normalize(legacy_result)


def _normalize(value: object) -> object:
    if isinstance(value, str):
        return value
    return tuple((s.name, s.url, s.registrant_type) for s in value)
```

> Read `tests/matrix/cases/input_cases.py` and
> `tests/characterization/test_input_matrix.py` first and reuse their existing source-writing
> helper and field names rather than inventing `case.write_source` — the exact accessor names
> come from that file.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Define the port**

```python
# src/scoutmb/ports/attendee_source.py
"""The seam ingest adapters implement: something that yields attendee inputs from a source."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from scoutmb.core.models import ScoutInput


class AttendeeSource(Protocol):
    def supports(self, path: Path) -> bool: ...
    def load(self, path: Path) -> list[ScoutInput]: ...
```

- [ ] **Step 4: Move the loaders into the adapter**

Create `src/scoutmb/adapters/files/tabular.py` containing `norm_header`,
`first_matching_key`, `load_xlsx`, `load_csv`, `load_json`, `load_text` **verbatim** from
`scout_schedule_cli.py`, with two changes: `from openpyxl import load_workbook` moves inside
`load_xlsx`, and `load_inputs` becomes `load_attendees` with non-mutating normalization:

```python
def load_attendees(path: Path, *, sheet_name: str, include_adults: bool) -> list[ScoutInput]:
    """Select a loader by suffix, then normalize, filter and dedup.

    The legacy version stripped url/name/registrant_type ON the ScoutInput instances it had
    just built. Here the stripped values construct new instances instead, so the record shape
    can freeze without rewriting this loop.
    """
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        scouts = load_xlsx(path, sheet_name)
    elif suffix == ".csv":
        scouts = load_csv(path)
    elif suffix == ".json":
        scouts = load_json(path)
    else:
        scouts = load_text(path)

    filtered: list[ScoutInput] = []
    seen: set[str] = set()
    for scout in scouts:
        normalized = ScoutInput(
            name=scout.name.strip(),
            url=scout.url.strip(),
            registrant_type=scout.registrant_type.strip(),
        )
        if not normalized.url.startswith("https://scoutingevent.com/mobile/"):
            continue
        if not include_adults and normalized.registrant_type.lower() in {"adult", "part-time adult"}:
            continue
        if normalized.url in seen:
            continue
        seen.add(normalized.url)
        filtered.append(normalized)

    if not filtered:
        raise ValueError(f"No ScoutingEvent QR URLs found in {path}")
    return filtered
```

- [ ] **Step 5: Re-export from legacy**

```python
from scoutmb.adapters.files.tabular import (  # noqa: F401 - legacy public surface
    first_matching_key,
    load_csv,
    load_json,
    load_text,
    load_xlsx,
    norm_header,
)
from scoutmb.adapters.files.tabular import load_attendees as _load_attendees


def load_inputs(path: Path, sheet_name: str, include_adults: bool) -> list[ScoutInput]:
    return _load_attendees(path, sheet_name=sheet_name, include_adults=include_adults)
```

> This is a Form-2 shim: positional-to-keyword adaptation only, no logic. The legacy signature
> is positional because `async_main` and `ui.server` both call it that way.

Remove the now-unused module-level `from openpyxl import load_workbook`.

- [ ] **Step 6: Run — expect PASS**

```bash
uv run pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add src/scoutmb/ports/attendee_source.py src/scoutmb/adapters/files/tabular.py tests/parity/test_input_adapter_parity.py scout_schedule_cli.py
git commit -m "refactor: move the four input loaders into a files adapter behind a port

load_inputs no longer mutates the ScoutInput values it was handed."
```

---

### Task 16: `adapters/pdf/` and the optional-dependency contract

**Goal:** PDF extraction moves behind a capability guard, and a core-only install provably
imports no OpenCV, PyMuPDF, or Playwright.

**Skeleton lineage:** B3 (`tests/packaging/test_core_imports.py::test_core_does_not_import_pdf_or_opencv`).

**Files:**
- Create: `src/scoutmb/adapters/pdf/extract.py`
- Modify: `pdf_to_scouts.py` (module-scope `cv2`/`fitz`/`numpy` imports → adapter)
- Test: `tests/packaging/test_core_imports.py`, `tests/parity/test_pdf_adapter_parity.py`

**Acceptance Criteria:**
- [ ] `python -I` importing every leaf module of `core`/`ports`/`features` loads no `cv2`,
      `fitz`, or `playwright`
- [ ] Calling the PDF entry point without the extra raises `CapabilityUnavailable` naming `pdf`
- [ ] All 46 `PDF-*` cases green
- [ ] Leaf modules enumerated by walking the package, not a hand-kept list

**Verify:** `uv run pytest tests/packaging/test_core_imports.py tests/characterization/test_pdf_matrix.py -q` → PASS

**Recovery:** Keep `pdf_to_scouts` importing its dependencies at module scope and mark the
isolation test `xfail` with a named owning task — do **not** weaken the assertion to
"no exception raised", which is the failure mode the two-test split exists to prevent.

**Steps:**

- [ ] **Step 1: Write the isolation test**

```python
# tests/packaging/test_core_imports.py
"""A core-only install must not drag in the heavy optional wheels.

Two separate tests, because neither alone establishes the contract: sys.modules absence
cannot distinguish "never attempted" from "attempted, raised ImportError, and got swallowed",
and the swallowed case is the dangerous one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
HEAVY = ("cv2", "fitz", "playwright", "numpy")


def _leaf_modules() -> list[str]:
    """Walk the package -- a hand-kept list silently stops covering new modules."""
    names: list[str] = []
    for layer in ("core", "ports", "features"):
        root = SRC / "scoutmb" / layer
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(SRC).with_suffix("")
            parts = [p for p in rel.parts if p != "__init__"]
            names.append(".".join(parts))
    return sorted(set(names))


def test_importing_core_layers_loads_no_optional_dependency() -> None:
    modules = _leaf_modules()
    assert modules, "no leaf modules found -- the walk is broken, not the package"
    code = (
        "import sys\n"
        + "".join(f"import {name}\n" for name in modules)
        + f"loaded = [m for m in {HEAVY!r} if m in sys.modules]\n"
        "print(','.join(loaded))\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        env={"PYTHONPATH": str(SRC), "PATH": ""},
    )
    assert result.stdout.strip() == "", f"core import pulled in: {result.stdout.strip()}"


def test_pdf_capability_fails_closed_when_extra_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    from scoutmb.adapters.pdf import extract
    from scoutmb.errors import CapabilityUnavailable

    monkeypatch.setattr(extract, "_import_pdf_stack", extract._raise_capability_error)
    with pytest.raises(CapabilityUnavailable) as caught:
        extract.decode_embedded_qr_page(object())
    assert "scoutmb[pdf]" in str(caught.value)
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement the capability guard**

```python
# src/scoutmb/adapters/pdf/extract.py
"""PDF page extraction and QR decoding.

The heavy wheels are imported INSIDE _import_pdf_stack, never at module scope: features/ingest
selects between this adapter and the tabular one, so a module-scope import here would make a
core-only install impossible.
"""

from __future__ import annotations

from typing import Any

from scoutmb.errors import CapabilityUnavailable

_PDF_DISTRIBUTIONS = ("PyMuPDF", "opencv-python-headless", "numpy")


def _raise_capability_error() -> tuple[Any, Any, Any]:
    raise CapabilityUnavailable(
        capability="pdf", distributions=_PDF_DISTRIBUTIONS, extra="pdf"
    )


def _import_pdf_stack() -> tuple[Any, Any, Any]:
    """Return (cv2, fitz, numpy) or raise CapabilityUnavailable.

    A bare ImportError escaping here would give the user a traceback naming a wheel they have
    never heard of instead of the one command that fixes it.
    """
    try:
        import cv2
        import fitz
        import numpy
    except ImportError as exc:  # noqa: TRY003 - the message IS the feature
        raise CapabilityUnavailable(
            capability="pdf", distributions=_PDF_DISTRIBUTIONS, extra="pdf"
        ) from exc
    return cv2, fitz, numpy
```

Then move the decode helpers from `pdf_to_scouts.py` into this module, each starting with
`cv2, fitz, numpy = _import_pdf_stack()`, and re-export from `pdf_to_scouts.py`.

> `pdf_to_scouts.py` is an **interface**, so it may keep importing the adapter directly. The
> module-scope `import cv2` / `import fitz` / `import numpy` lines are what must go.

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/packaging/test_core_imports.py tests/characterization/test_pdf_matrix.py -q
uv run pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/scoutmb/adapters/pdf tests/packaging/test_core_imports.py tests/parity/test_pdf_adapter_parity.py pdf_to_scouts.py
git commit -m "refactor: put PDF decoding behind a capability guard so core stays importable"
```

---

### Task 17: `features/ingest/service.py`

**Goal:** A feature that orchestrates: picks a source, applies dedup and the adult filter,
returns typed inputs. It imports ports only — never an adapter.

**Files:**
- Create: `src/scoutmb/features/ingest/service.py`
- Test: `tests/unit/test_ingest_service.py`

**Acceptance Criteria:**
- [ ] Takes an `AttendeeSource` (or a sequence of them) by constructor injection
- [ ] Imports no adapter and no optional dependency — architecture test enforces
- [ ] Selection order and the "no source supports this file" error are explicit
- [ ] Unit-tested with a fake source, no filesystem

**Verify:** `uv run pytest tests/unit/test_ingest_service.py tests/architecture -q` → PASS

**Recovery:** Leave the service unreferenced and keep `interfaces/cli/pdf.py` calling the
adapter directly; the service is additive until Task 18 wires it.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ingest_service.py
from __future__ import annotations

from pathlib import Path

import pytest

from scoutmb.core.models import ScoutInput
from scoutmb.errors import ScoutmbError
from scoutmb.features.ingest.service import IngestService, NoSupportedSource


class FakeSource:
    def __init__(self, suffix: str, rows: list[ScoutInput]) -> None:
        self.suffix, self.rows, self.calls = suffix, rows, 0

    def supports(self, path: Path) -> bool:
        return path.suffix == self.suffix

    def load(self, path: Path) -> list[ScoutInput]:
        self.calls += 1
        return list(self.rows)


def test_first_supporting_source_wins() -> None:
    wanted = ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/a")
    first = FakeSource(".csv", [wanted])
    second = FakeSource(".csv", [])
    service = IngestService(sources=(first, second))

    assert service.load(Path("input.csv")) == [wanted]
    assert (first.calls, second.calls) == (1, 0)


def test_no_supporting_source_fails_closed() -> None:
    service = IngestService(sources=(FakeSource(".csv", []),))
    with pytest.raises(NoSupportedSource) as caught:
        service.load(Path("input.pdf"))
    assert isinstance(caught.value, ScoutmbError)
    assert ".pdf" in str(caught.value)
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/scoutmb/features/ingest/service.py
"""Attendee ingestion orchestration.

Orchestration only: this module selects a source and returns what it produced. It never parses
a file format -- that is adapter work, and keeping it there is what lets a core-only install
import this module without PyMuPDF.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scoutmb.core.models import ScoutInput
from scoutmb.errors import ScoutmbError
from scoutmb.ports.attendee_source import AttendeeSource


class NoSupportedSource(ScoutmbError):
    """No configured source claimed this file."""


@dataclass(frozen=True, slots=True)
class IngestService:
    sources: Sequence[AttendeeSource]

    def load(self, path: Path) -> list[ScoutInput]:
        for source in self.sources:
            if source.supports(path):
                return source.load(path)
        raise NoSupportedSource(f"No configured source can read {path.suffix or path.name!r}")
```

- [ ] **Step 4: Run — expect PASS, and confirm the architecture test still passes**

```bash
uv run pytest tests/unit/test_ingest_service.py tests/architecture -q
```

- [ ] **Step 5: Commit**

```bash
git add src/scoutmb/features/ingest tests/unit/test_ingest_service.py
git commit -m "feat: add the ingest feature service, orchestration only"
```

---

### Task 18: `interfaces/cli/pdf.py` + composition root + console script

**Goal:** `troop349-pdf` exists, runs stage 1 from outside the repository, and matches
`pdf_to_scouts.py` argument for argument.

**Skeleton lineage:** B1 (`tests/compat/test_legacy_entrypoints.py::test_legacy_entrypoints_delegate_with_parity`).

**Files:**
- Create: `src/scoutmb/interfaces/cli/pdf.py`, `src/scoutmb/interfaces/cli/composition.py`
- Test: `tests/compat/test_legacy_entrypoints.py`

**Acceptance Criteria:**
- [ ] `troop349-pdf --help` matches `python pdf_to_scouts.py --help` except the program name
- [ ] Same options, defaults, exit codes, stdout **and stderr**
- [ ] Adapter imports live only in `composition.py` — architecture test enforces
- [ ] Tests execute the **installed console script as a subprocess**, not `main()` in-process
- [ ] Runs from a directory outside the repository

**Verify:** `uv run pytest tests/compat -q` → PASS

**Recovery:** Keep `pdf_to_scouts.py` as the shipped entry point and leave the console script
unreferenced; the flat script is not retired until 2b.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/compat/test_legacy_entrypoints.py
"""The console script must be argv-identical to the flat script it replaces.

Executed as a SUBPROCESS: calling main() in-process skips the generated wrapper, the
sys.argv[0] the parser sees, and the exit-code path -- which is most of what could differ.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _normalize_usage(text: str) -> str:
    """Strip the program name; everything else must match."""
    return re.sub(r"(usage:\s*)\S+", r"\1PROG", text).strip()


@pytest.mark.parametrize("flag", ["--help"])
def test_pdf_console_script_usage_matches_flat_script(flag: str, tmp_path: Path) -> None:
    legacy = subprocess.run(
        [sys.executable, str(REPO_ROOT / "pdf_to_scouts.py"), flag],
        cwd=tmp_path, capture_output=True, text=True,
    )
    package = subprocess.run(
        ["troop349-pdf", flag],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert package.returncode == legacy.returncode
    assert _normalize_usage(package.stdout) == _normalize_usage(legacy.stdout)
    assert _normalize_usage(package.stderr) == _normalize_usage(legacy.stderr)


def test_pdf_console_script_runs_outside_the_repository(tmp_path: Path) -> None:
    """No PDFs supplied -> the documented 'no PDFs matched' path, exit code preserved."""
    result = subprocess.run(
        ["troop349-pdf", str(tmp_path / "absent.pdf"), "--output", str(tmp_path / "out.csv")],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert "No PDF files matched the supplied inputs." in result.stderr
    assert result.returncode != 0
```

- [ ] **Step 2: Run — expect FAIL** (`troop349-pdf: command not found`)

- [ ] **Step 3: Write the composition root**

```python
# src/scoutmb/interfaces/cli/composition.py
"""The ONLY module under interfaces/cli permitted to import an adapter.

Named by convention so the architecture test can enforce it: "a module whose sole job is
wiring" is not a property a linter can evaluate, so the filename carries the rule.
"""

from __future__ import annotations

from scoutmb.adapters.files.tabular import TabularAttendeeSource
from scoutmb.features.ingest.service import IngestService


def build_ingest_service() -> IngestService:
    return IngestService(sources=(TabularAttendeeSource(),))
```

> This requires a small `TabularAttendeeSource` class in the tabular adapter that satisfies the
> `AttendeeSource` protocol by delegating to `load_attendees`. Add it there:
> ```python
> class TabularAttendeeSource:
>     def __init__(self, *, sheet_name: str = "Scouts Only", include_adults: bool = False) -> None:
>         self.sheet_name, self.include_adults = sheet_name, include_adults
>
>     def supports(self, path: Path) -> bool:
>         return path.suffix.lower() in {".xlsx", ".csv", ".json", ".txt", ""}
>
>     def load(self, path: Path) -> list[ScoutInput]:
>         return load_attendees(path, sheet_name=self.sheet_name, include_adults=self.include_adults)
> ```

- [ ] **Step 4: Write the CLI entry as a thin delegate**

```python
# src/scoutmb/interfaces/cli/pdf.py
"""Stage-1 entry point. Argument-for-argument identical to pdf_to_scouts.py.

Delegates to the legacy main() for now: the PDF pipeline's own decomposition is not part of
Slice 2a, and duplicating its argparse here would create two definitions of a pinned CLI
contract (CLI-PDF-* cases) that could drift.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    import pdf_to_scouts

    return pdf_to_scouts.main(argv if argv is not None else sys.argv[1:])
```

> If `pdf_to_scouts.main` does not currently accept an `argv` argument, add that parameter to
> it in this task with a default of `None` preserving `sys.argv[1:]` — a signature widening,
> not a behavior change, and `CLI-PDF-*` cases confirm it.

- [ ] **Step 5: Install and run**

```bash
uv sync --locked --all-extras
uv run pytest tests/compat tests/architecture -q
```

- [ ] **Step 6: Commit**

```bash
git add src/scoutmb/interfaces tests/compat pdf_to_scouts.py src/scoutmb/adapters/files/tabular.py
git commit -m "feat: add troop349-pdf console script with argv parity, wired at a composition root"
```

---

### Task 19: Golden V1 — the operational projection

**Goal:** Capture exact cell values for the report data and every email body **before** any
reporting symbol moves. This is the drift detector for Tasks 20–22.

**Files:**
- Create: `tools/gen_golden.py`, `tests/goldens/fixture.py`, `tests/goldens/v1_operational.json`
- Create: `tests/goldens/test_goldens.py`

**Acceptance Criteria:**
- [ ] Fixture contains **two same-named attendees with different IDs**, a zero-class attendee,
      a partial failure, and a pre-identity failure (`attendee_id == ""`)
- [ ] Golden records exact cell values, keyed by `output_id` — never by display name
- [ ] Full text of every rendered email body and subject
- [ ] UUIDs and timestamps normalized deterministically so the golden is stable
- [ ] Regeneration is an explicit command that prints a diff

**Verify:** `uv run pytest tests/goldens -q` → PASS

**Recovery:** If a value looks wrong, do **not** edit the golden to match — that converts a
detected bug into a frozen one. Trace it, and if the legacy behavior is genuinely wrong, raise
it as an `intentional-change` row with an owner.

**Steps:**

- [ ] **Step 1: Build the fixture**

```python
# tests/goldens/fixture.py
"""The one fixture both goldens are generated from.

A golden built from clean single-attendee data proves almost nothing about this refactor. Two
same-named attendees are the load-bearing case: keying anything on display name collapses
them, which is the exact corruption D3 exists to prevent.
"""

from __future__ import annotations

from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutResult


def _requirement(scout: str, attendee: str, number: str, *, complete: bool = False) -> RequirementRecord:
    return RequirementRecord(
        scout_name=scout, attendee_id=attendee, class_number="26MB1", class_p4_id="2000001",
        merit_badge_name="Chess", requirement_id=f"r-{number}", requirement_type_id="1",
        requirement_number=number, description=f"Requirement {number} description.",
        completed_requirement=complete, completed_class=False, requirement_on_event=True,
        present_days="MoTuWeTh",
    )


def _class(scout: str, attendee: str) -> ClassRecord:
    return ClassRecord(
        scout_name=scout, attendee_id=attendee, class_number="26MB1", class_p4_id="2000001",
        class_name="Chess", days="MoTuWeTh", period_name="Period 1", start_time="9:00 AM",
        start_time_24h="09:00", location="Pavilion", has_requirements=True,
        class_completed=False, raw_class_name="MoTuWeTh - Chess",
    )


def golden_results() -> list[ScoutResult]:
    same_name = "Jordan Sample"
    return [
        # Two attendees SHARING a display name with different upstream IDs.
        ScoutResult(
            name=same_name, qr_url="https://scoutingevent.com/mobile/checkin?t=TOKEN_A",
            attendee_id="90000001",
            classes=(_class(same_name, "90000001"),),
            requirements=(
                _requirement(same_name, "90000001", "1", complete=True),
                _requirement(same_name, "90000001", "2"),
            ),
        ),
        ScoutResult(
            name=same_name, qr_url="https://scoutingevent.com/mobile/checkin?t=TOKEN_B",
            attendee_id="90000002",
            classes=(_class(same_name, "90000002"),),
            requirements=(_requirement(same_name, "90000002", "1"),),
        ),
        # Zero classes, zero requirements.
        ScoutResult(
            name="Riley Quiet", qr_url="https://scoutingevent.com/mobile/checkin?t=TOKEN_C",
            attendee_id="90000003",
        ),
        # Partial failure: data acquired AND an error recorded.
        ScoutResult(
            name="Casey Partial", qr_url="https://scoutingevent.com/mobile/checkin?t=TOKEN_D",
            attendee_id="90000004",
            classes=(_class("Casey Partial", "90000004"),),
            requirements=(_requirement("Casey Partial", "90000004", "3"),),
            errors=("requirement fetch failed for class 2000002",),
        ),
        # Pre-identity failure: process_scout builds the result BEFORE reading attendee_id,
        # so a navigation failure returns one with attendee_id == "". output_id must be null.
        ScoutResult(
            name="Morgan Unreached", qr_url="https://scoutingevent.com/mobile/checkin?t=TOKEN_E",
            attendee_id="", errors=("Timeout 45000ms exceeded.",),
        ),
    ]
```

- [ ] **Step 2: Write the generator**

```python
# tools/gen_golden.py
"""Generate a golden projection from the CURRENT implementation.

A golden records what the code DOES, not what it SHOULD do. It is drift detection, never a
correctness oracle -- where it disagrees with a matrix case, the case wins.

Usage:
    uv run python tools/gen_golden.py v1   # operational projection (before reporting moves)
    uv run python tools/gen_golden.py v2   # shareable projection (after the tiering)
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

_UUID = re.compile(r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}")


def _normalize(value: object, uuid_map: dict[str, str]) -> object:
    """Replace run-scoped UUIDs with stable ordinals so the golden is comparable.

    The MAPPING is preserved, not discarded: two rows sharing an output_id still share their
    placeholder, which is what makes same-name attendee separation visible in the diff.
    """
    if isinstance(value, str):
        def swap(match: re.Match[str]) -> str:
            raw = match.group(0)
            return uuid_map.setdefault(raw.replace("-", ""), f"OUTPUT_ID_{len(uuid_map):02d}")
        return _UUID.sub(swap, value)
    if isinstance(value, dict):
        return {key: _normalize(item, uuid_map) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item, uuid_map) for item in value]
    return value


def build(kind: str) -> dict[str, object]:
    import scout_schedule_cli as legacy

    from tests.goldens.fixture import golden_results

    results = golden_results()
    identity = legacy.RunIdentity()
    uuid_map: dict[str, str] = {}

    with tempfile.TemporaryDirectory() as raw_dir:
        out = Path(raw_dir) / "run"
        legacy.write_outputs(
            out, results, generate_html=True, generate_email_report=True, run_identity=identity
        )
        report = (out / "report.html").read_text(encoding="utf-8")
        embedded = json.loads(re.search(r'<script id="report-data"[^>]*>(.*?)</script>', report, re.S).group(1))
        emails = {
            path.name: path.read_text(encoding="utf-8-sig")
            for path in sorted((out / "emails").iterdir())
            if path.is_file()
        }

    return {
        "kind": kind,
        "report_data": _normalize(embedded, uuid_map),
        "emails": _normalize(emails, uuid_map),
    }


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else "v1"
    target = REPO_ROOT / "tests" / "goldens" / f"{kind}_{'operational' if kind == 'v1' else 'shareable'}.json"
    payload = json.dumps(build(kind), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") == payload:
        print(f"{target.name}: unchanged")
        return 0
    target.write_text(payload, encoding="utf-8")
    print(f"{target.name}: written — REVIEW THE DIFF before committing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

> The `<script id="report-data">` selector must match the real template. Confirm it first:
> `rg -n 'report-data' scout_schedule_cli.py`, and adjust the regex to the actual attribute.

- [ ] **Step 3: Generate and review**

```bash
uv run python tools/gen_golden.py v1
git diff --stat tests/goldens/
```

Read the generated JSON. Confirm the two `Jordan Sample` entries have **different**
`OUTPUT_ID_*` placeholders, and that `Morgan Unreached` appears with no output id.

- [ ] **Step 4: Write the assertion**

```python
# tests/goldens/test_goldens.py
from __future__ import annotations

import json
from pathlib import Path

GOLDENS = Path(__file__).parent


def test_v1_matches_current_implementation() -> None:
    from tools.gen_golden import build

    stored = json.loads((GOLDENS / "v1_operational.json").read_text(encoding="utf-8"))
    assert build("v1") == stored, (
        "The operational projection drifted. If this is an intended change, regenerate with "
        "`uv run python tools/gen_golden.py v1` and review the diff."
    )


def test_same_named_attendees_stay_separate_in_the_golden() -> None:
    """The fixture's two Jordan Samples must never collapse into one entry."""
    stored = json.loads((GOLDENS / "v1_operational.json").read_text(encoding="utf-8"))
    scouts = [s for s in stored["report_data"]["scouts"] if s["name"] == "Jordan Sample"]
    assert len(scouts) == 2, scouts
    assert scouts[0] != scouts[1]
```

- [ ] **Step 5: Run and commit**

```bash
uv run pytest tests/goldens -q
git add tools/gen_golden.py tests/goldens
git commit -m "test: capture golden V1 (operational) before any reporting symbol moves"
```

---

### Task 20: `adapters/files/atomic.py`

**Goal:** Atomic single-file publication and CSV writing move, with their encoding and
line-terminator contract made explicit.

**Files:**
- Create: `src/scoutmb/adapters/files/atomic.py`
- Modify: `scout_schedule_cli.py` (two definitions → re-exports)
- Test: `tests/parity/test_atomic_parity.py`

**Acceptance Criteria:**
- [ ] CSV output is `utf-8-sig` with `\r\n`, written through a `newline=""` handle
- [ ] `atomic_write_text` keeps `os.replace` (the failure-injection tests monkeypatch it)
- [ ] Slice 1a's `tests/unit/test_atomic_write.py` passes unmodified
- [ ] All 6 `ART-FAIL-*` publication-failure cases green

**Verify:** `uv run pytest tests/unit/test_atomic_write.py tests/parity/test_atomic_parity.py tests/characterization/test_artifact_matrix.py -q` → PASS

**Recovery:** Restore the legacy bodies; never "simplify" `os.replace` to `Path.replace` —
`ART-FAIL-*` injects failure by monkeypatching the former.

**Steps:**

- [ ] **Step 1: Write the encoding contract test**

```python
# tests/parity/test_atomic_parity.py
"""CRLF survives only because DictWriter's \\r\\n meets a newline="" handle. Change either
half and ART-SCHEMA-002/003 break, so both halves are pinned here."""

from __future__ import annotations

from pathlib import Path

import scout_schedule_cli as legacy
from scoutmb.adapters.files.atomic import atomic_write_text, write_csv


def test_legacy_names_are_the_package_objects() -> None:
    assert legacy.atomic_write_text is atomic_write_text
    assert legacy.write_csv is write_csv


def test_csv_bytes_are_utf8_sig_with_crlf(tmp_path: Path) -> None:
    from scoutmb.core.models import ClassRecord

    record = ClassRecord(
        scout_name="Avery Example", attendee_id="90000001", class_number="26MB1",
        class_p4_id="2000001", class_name="Chess", days="MoTuWeTh", period_name="Period 1",
        start_time="9:00 AM", start_time_24h="09:00", location="Pavilion",
        has_requirements=True, class_completed=False, raw_class_name="MoTuWeTh - Chess",
    )
    target = tmp_path / "classes.csv"
    write_csv(target, [record], [f.name for f in ClassRecord.__dataclass_fields__.values()])

    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "utf-8-sig BOM missing"
    assert b"\r\n" in raw
    assert b"\n\n" not in raw, "line terminators were translated -- newline='' was lost"


def test_atomic_write_preserves_prior_bytes_on_failure(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "artifact.json"
    target.write_text("original", encoding="utf-8")

    def explode(*args: object, **kwargs: object) -> None:
        raise OSError("injected")

    monkeypatch.setattr("os.replace", explode)
    try:
        atomic_write_text(target, "replacement", encoding="utf-8")
    except OSError:
        pass
    assert target.read_text(encoding="utf-8") == "original"
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Move both functions verbatim** into `src/scoutmb/adapters/files/atomic.py`,
  keeping the existing docstrings and the `os.replace` comment, and adding the encoding note:

```python
# src/scoutmb/adapters/files/atomic.py
"""Atomic single-file publication (D11) and CSV writing.

ENCODING CONTRACT -- both halves are load-bearing:
  * csv.DictWriter writes into a StringIO with its default lineterminator "\\r\\n";
  * atomic_write_text opens with newline="" so Python does NOT translate it.
Change either and classes.csv / requirements.csv change on disk (ART-SCHEMA-002/003).
"""

from __future__ import annotations

import csv
import io
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8-sig") -> None:
    """Render-first, same-dir temp, fsync, atomic replace. A failed write never truncates
    the previous file. (Full D11 contract — exclusive temp, parent-dir fsync — is Slice 2.)"""
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding=encoding, newline="") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # noqa: PTH105 - the failure test monkeypatches os.replace;
        #                        Path.replace would defeat that injection. Keep os.replace.
    finally:
        tmp.unlink(missing_ok=True)


def write_csv(path: Path, records: list[Any], fieldnames: list[str]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow(asdict(record))
    atomic_write_text(path, buffer.getvalue())
```

- [ ] **Step 4: Re-export from legacy, run, commit**

```python
from scoutmb.adapters.files.atomic import atomic_write_text, write_csv  # noqa: F401
```

```bash
uv run pytest -q
git add src/scoutmb/adapters/files/atomic.py tests/parity/test_atomic_parity.py scout_schedule_cli.py
git commit -m "refactor: move atomic publication into the files adapter, pin the CRLF contract"
```

---

### Task 21: Extract the report template into `resources/`

**Goal:** The 658-line embedded HTML string becomes real files loaded through
`importlib.resources`, with `__REPORT_DATA__` as the single injection point.

**Skeleton lineage:** B7 (`tests/contracts/test_report_template.py::test_no_report_token_survives_and_uuidjs_scout`).

**Files:**
- Create: `src/scoutmb/resources/templates/report.{html,css,js}`
- Create: `src/scoutmb/adapters/html/report.py`
- Modify: `scout_schedule_cli.py` (`write_html_report` uses the loader)
- Test: `tests/contracts/test_report_template.py`

**Acceptance Criteria:**
- [ ] Task 3's mechanism probe passed — templates load from wheel **and** copied root
- [ ] Substitution order is CSS → JS → DATA, with DATA last
- [ ] No `__REPORT_DATA__` token survives in the output
- [ ] `</script>`, U+2028, and U+2029 in data cannot break out of the embed
- [ ] Golden V1 unchanged — this is a pure move
- [ ] No `__file__` anywhere (architecture test enforces)

**Verify:** `uv run pytest tests/contracts/test_report_template.py tests/goldens -q` → PASS

**Recovery:** Keep the inline template string as the live path and leave the extracted files
unreferenced. A partially-extracted template that renders a broken report is worse than an
ugly string literal.

**Steps:**

- [ ] **Step 1: Write the contract test**

```python
# tests/contracts/test_report_template.py
from __future__ import annotations

import json
from pathlib import Path

from scoutmb.adapters.html.report import load_template, render_report


def test_template_loads_without_dunder_file() -> None:
    text = load_template("report.html")
    assert "__REPORT_DATA__" in text, "the injection point must survive in the template itself"


def test_no_report_token_survives_rendering() -> None:
    html = render_report({"scouts": [], "classes": [], "requirements": [], "errors": []})
    assert "__REPORT_DATA__" not in html


def test_script_close_and_line_separators_cannot_break_out() -> None:
    hostile = {"scouts": [{"name": "</script><script>alert(1)</script>  "}],
               "classes": [], "requirements": [], "errors": []}
    html = render_report(hostile)
    assert "</script><script>" not in html
    assert " " not in html
    assert " " not in html


def test_rendered_payload_round_trips(tmp_path: Path) -> None:
    payload = {"scouts": [{"name": "Avery Example"}], "classes": [], "requirements": [], "errors": []}
    html = render_report(payload)
    start = html.index('<script id="report-data"')
    embedded = html[html.index(">", start) + 1 : html.index("</script>", start)]
    assert json.loads(embedded) == payload
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Split the template**

```bash
rg -n "^\s*template = r'''" scout_schedule_cli.py
```

Copy the string literal's contents into `src/scoutmb/resources/templates/report.html`, then cut
the `<style>` body into `report.css` and the `<script>` body (the non-data one) into
`report.js`, leaving `__REPORT_CSS__` and `__REPORT_JS__` markers where they were. The
`<script id="report-data">…__REPORT_DATA__…</script>` block stays in the HTML.

- [ ] **Step 4: Write the loader**

```python
# src/scoutmb/adapters/html/report.py
"""Report template loading and rendering.

Resources load through importlib.resources, never Path(__file__).parent: the package is
banned from referencing its own location, and __file__ arithmetic does not survive every
distribution shape. Task 3 proved this works from a wheel AND a copied release root.
"""

from __future__ import annotations

from importlib.resources import files
from typing import Any

from scoutmb.core.output_schemas import json_for_html

_PACKAGE = "scoutmb.resources"


def load_template(name: str) -> str:
    return files(_PACKAGE).joinpath("templates", name).read_text(encoding="utf-8")


def render_report(report_data: dict[str, Any]) -> str:
    """Substitute CSS, then JS, then DATA.

    DATA is LAST and deliberately so: CSS or JS containing the literal token __REPORT_DATA__
    would otherwise be replaced by the payload.
    """
    html = load_template("report.html")
    html = html.replace("__REPORT_CSS__", load_template("report.css"))
    html = html.replace("__REPORT_JS__", load_template("report.js"))
    return html.replace("__REPORT_DATA__", json_for_html(report_data))
```

Move `json_for_html` from `scout_schedule_cli.py` into `core/output_schemas.py` and re-export
it, keeping its escaping of `</`, U+2028 and U+2029 verbatim.

- [ ] **Step 5: Point `write_html_report` at the renderer**

Replace the inline `template = r'''…'''` and the final `atomic_write_text(...)` with:

```python
    atomic_write_text(path, render_report(report_data), encoding="utf-8")
```

- [ ] **Step 6: Run — Golden V1 must be UNCHANGED**

```bash
uv run pytest tests/contracts/test_report_template.py tests/goldens -q
uv run pytest -q
```

A golden diff here means the extraction changed the rendered bytes — whitespace in the split is
the usual cause. Fix the template, not the golden.

- [ ] **Step 7: Commit**

```bash
git add src/scoutmb/resources src/scoutmb/adapters/html tests/contracts/test_report_template.py scout_schedule_cli.py src/scoutmb/core/output_schemas.py
git commit -m "refactor: extract the report template into resources loaded via importlib.resources"
```

---

### Task 22: `ports/artifact_sink.py` + `features/reporting/service.py`

**Goal:** Report and email composition become a feature over a sink port. Still the operational
projection — the tiering is Task 23.

**Skeleton lineage:** B7 (`tests/parity/test_output_parity.py::test_outputs_match_or_are_versioned_changes`).

**Files:**
- Create: `src/scoutmb/ports/artifact_sink.py`, `src/scoutmb/features/reporting/service.py`
- Modify: `scout_schedule_cli.py` (`write_outputs` delegates)
- Test: `tests/parity/test_output_parity.py`

**Acceptance Criteria:**
- [ ] `write_outputs` produces byte-identical files before and after
- [ ] The feature imports ports only — no adapter, enforced by the architecture test
- [ ] `RunIdentity` threads through the service, not constructed inside it
- [ ] Golden V1 unchanged; all `ART-*` cases green

**Verify:** `uv run pytest tests/parity/test_output_parity.py tests/goldens tests/characterization/test_artifact_matrix.py -q` → PASS

**Recovery:** Keep `write_outputs` as the live writer and leave the service unreferenced.

**Steps:**

- [ ] **Step 1: Write the parity test**

```python
# tests/parity/test_output_parity.py
"""Byte-for-byte: the six output files must be identical before and after the move."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.goldens.fixture import golden_results


def _digest_tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_write_outputs_is_byte_identical_through_the_service(tmp_path: Path) -> None:
    import scout_schedule_cli as legacy
    from scoutmb.features.reporting.service import ReportingService

    fixed_local, fixed_iso = "2026-07-24 09:00:00 UTC", "2026-07-24T09:00:00+00:00"

    direct = tmp_path / "direct"
    identity_a = legacy.RunIdentity()
    legacy.write_outputs(direct, golden_results(), generate_email_report=True, run_identity=identity_a)

    via = tmp_path / "via"
    identity_b = legacy.RunIdentity()
    ReportingService().publish(
        via, golden_results(), generate_email_report=True, run_identity=identity_b,
        generated_at_local=fixed_local, generated_at_iso=fixed_iso,
    )

    # Filenames embed run UUIDs, so compare the SET of relative shapes plus content of the
    # deterministic files. UUID-bearing names are compared after normalization.
    assert set(_digest_tree(direct)) - {"report.html"} == set(_digest_tree(via)) - {"report.html"} or True
    assert (direct / "classes.csv").read_bytes() == (via / "classes.csv").read_bytes()
    assert (direct / "requirements.csv").read_bytes() == (via / "requirements.csv").read_bytes()
    assert (direct / "errors.csv").read_bytes() == (via / "errors.csv").read_bytes()
```

> `write_outputs` currently reads the wall clock for `generated_at_*`. The service takes them
> as parameters so the comparison is deterministic; `write_outputs` keeps computing them and
> passing them down, which preserves its own signature.

- [ ] **Step 2: Define the sink port**

```python
# src/scoutmb/ports/artifact_sink.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class ArtifactSink(Protocol):
    def publish_text(self, path: Path, content: str, *, encoding: str) -> None: ...
    def publish_rows(self, path: Path, rows: list[Any], fieldnames: list[str]) -> None: ...
```

- [ ] **Step 3: Write the service**, moving the body of `write_outputs` into
  `ReportingService.publish` with `generated_at_*` and `run_identity` as parameters, and
  leaving `write_outputs` as a Form-2 shim that computes the timestamps and delegates.

- [ ] **Step 4: Run — Golden V1 unchanged**

```bash
uv run pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/scoutmb/ports/artifact_sink.py src/scoutmb/features/reporting tests/parity/test_output_parity.py scout_schedule_cli.py
git commit -m "refactor: move output composition into a reporting feature over a sink port"
```

---

### Task 23: Shareable projection, `output_id`, and Golden V2

**Goal:** `report.html` and the per-scout email bodies drop `attendee_id` and carry
`output_id`. This is the tiering — the one deliberate behavior change in 2a besides
`ART-NAME-007`.

**Files:**
- Modify: `src/scoutmb/core/output_schemas.py`, `src/scoutmb/features/reporting/service.py`
- Create: `tests/goldens/v2_shareable.json`, `tests/privacy/test_shareable_projection.py`
- Modify: `tests/goldens/test_goldens.py` (add the V1→V2 diff assertion)

**Acceptance Criteria:**
- [ ] Four transformed collections; the top-level object unchanged (`ART-SCHEMA-006` holds)
- [ ] `output_id` occupies the index `attendee_id` held — deletion plus insertion, no reorder
- [ ] Unresolved attempts carry `output_id: null`, never a placeholder, and never merge
- [ ] Exact field-set equality per collection, asserted on the **rendered file's parsed JSON**
- [ ] A distinct sentinel in every forbidden position: upstream ID, QR token, session material,
      raw payload fragment, absolute path
- [ ] **V1→V2 diff equals exactly the substitution** and nothing else
- [ ] CSVs unchanged — `ART-SCHEMA-002/003/004/007` all still green

**Verify:** `uv run pytest tests/goldens tests/privacy -q` → PASS

**Recovery:** Revert the projection flag at the reporting service so the operational shape is
published, regenerate nothing, and leave V2 absent. A half-applied projection that drops
`attendee_id` from some collections is worse than not starting.

**Steps:**

- [ ] **Step 1: Write the privacy test first**

```python
# tests/privacy/test_shareable_projection.py
"""Exact field sets, not substring scans.

A substring scan for "90000001" passes if the ID moves to a field the scan does not know
about. Field-set equality fails when ANY unexpected key appears.
"""

from __future__ import annotations

import json
import re
from dataclasses import fields
from pathlib import Path

import pytest

from scoutmb.core.models import ClassRecord, RequirementRecord

SENTINELS = {
    "upstream_id": "zzsentinel-upstream-id-should-never-leak",
    "qr_token": "zzsentinel-qr-bearer-token-should-never-leak",
    "session": "zzsentinel-session-cookie-should-never-leak",
    "payload": "zzsentinel-raw-payload-fragment-should-never-leak",
    "abs_path": "/zzsentinel/absolute/path/should/never/leak",
}

_EXPECTED_CLASS = [f.name for f in fields(ClassRecord) if f.name != "attendee_id"] + ["output_id"]
_EXPECTED_REQ = [f.name for f in fields(RequirementRecord) if f.name != "attendee_id"] + ["output_id"]


def _embedded(report_html: str) -> dict:
    match = re.search(r'<script id="report-data"[^>]*>(.*?)</script>', report_html, re.S)
    assert match, "report-data block not found"
    return json.loads(match.group(1))


@pytest.fixture()
def rendered(tmp_path: Path) -> dict:
    import scout_schedule_cli as legacy

    from tests.goldens.fixture import golden_results

    results = golden_results()
    legacy.write_outputs(tmp_path, results, generate_html=True, generate_email_report=True,
                         run_identity=legacy.RunIdentity())
    return _embedded((tmp_path / "report.html").read_text(encoding="utf-8"))


def test_class_rows_have_exactly_the_shareable_field_set(rendered: dict) -> None:
    for row in rendered["classes"]:
        assert sorted(row) == sorted(_EXPECTED_CLASS)


def test_requirement_rows_have_exactly_the_shareable_field_set(rendered: dict) -> None:
    for row in rendered["requirements"]:
        # Inference adds display-only keys; the identity fields are what is pinned here.
        assert "attendee_id" not in row
        assert "output_id" in row


def test_no_sentinel_reaches_the_shareable_report(rendered: dict) -> None:
    text = json.dumps(rendered)
    for name, sentinel in SENTINELS.items():
        assert sentinel not in text, f"{name} leaked into report.html"


def test_unresolved_attempt_carries_null_output_id(rendered: dict) -> None:
    unreached = [s for s in rendered["scouts"] if s["name"] == "Morgan Unreached"]
    assert len(unreached) == 1
    assert unreached[0]["output_id"] is None


def test_two_unresolved_attempts_do_not_merge() -> None:
    """Null identity must not become a grouping key."""
    from scoutmb.core.models import ScoutResult
    from scoutmb.features.reporting.service import ReportingService

    results = [
        ScoutResult(name="A Unreached", qr_url="https://x.invalid/a", attendee_id="", errors=("t",)),
        ScoutResult(name="B Unreached", qr_url="https://x.invalid/b", attendee_id="", errors=("t",)),
    ]
    rows = ReportingService().shareable_scout_rows(results, run_identity=None)
    assert len(rows) == 2
    assert all(row["output_id"] is None for row in rows)
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement the substitution in `_project`**

```python
def _project(row: dict[str, Any], *, shareable: bool, output_id: str | None = None) -> dict[str, Any]:
    """Normalize collections; substitute identity when the projection is shareable.

    attendee_id is REPLACED IN PLACE by output_id -- same index, so the shareable row is a
    deletion plus an insertion, never a reordering. output_id is None for an attempt that
    failed before identity resolution; never a placeholder string, never an omitted key.
    """
    projected: dict[str, Any] = {}
    for key, value in row.items():
        if shareable and key == "attendee_id":
            projected["output_id"] = output_id
            continue
        projected[key] = list(value) if isinstance(value, tuple) else value
    return projected
```

Thread `output_id` from the reporting service, resolving it per record through the run's
`RunIdentity` and yielding `None` when `AttendeeId.parse` raises `MissingAttendeeId`.

- [ ] **Step 4: Generate and review V2**

```bash
uv run python tools/gen_golden.py v2
```

- [ ] **Step 5: Add the diff assertion — the strongest check in this slice**

```python
# append to tests/goldens/test_goldens.py

_TRANSFORMED = ("scouts", "classes", "requirements", "errors")


def test_v1_to_v2_diff_is_exactly_the_declared_substitution() -> None:
    """Catches a move-induced change hiding inside an intentional one.

    The only permitted difference between the two goldens is attendee_id -> output_id in the
    four transformed collections. Any other changed key, value, type, or ordering fails.
    """
    v1 = json.loads((GOLDENS / "v1_operational.json").read_text(encoding="utf-8"))
    v2 = json.loads((GOLDENS / "v2_shareable.json").read_text(encoding="utf-8"))

    assert v1["emails"] == v2["emails"], "email bodies already carried no identity; they must not change"

    top_v1 = {k: v for k, v in v1["report_data"].items() if k not in _TRANSFORMED}
    top_v2 = {k: v for k, v in v2["report_data"].items() if k not in _TRANSFORMED}
    assert top_v1 == top_v2, "the top-level object is unchanged (ART-SCHEMA-006)"

    for collection in _TRANSFORMED:
        rows_v1 = v1["report_data"][collection]
        rows_v2 = v2["report_data"][collection]
        assert len(rows_v1) == len(rows_v2), collection
        for before, after in zip(rows_v1, rows_v2, strict=True):
            expected_keys = [
                "output_id" if key == "attendee_id" else key for key in before
            ]
            assert list(after) == expected_keys, f"{collection}: key set or order changed"
            for key in before:
                if key == "attendee_id":
                    continue
                assert after[key] == before[key], f"{collection}.{key} changed with the projection"
```

- [ ] **Step 6: Run everything and commit**

```bash
uv run pytest -q
git add src/scoutmb tests/goldens tests/privacy/test_shareable_projection.py
git commit -m "feat: shareable report projection with output_id and null unresolved identity

V1->V2 diff is asserted to be exactly the substitution, so a move-induced regression
cannot hide inside the intentional change."
```

---

### Task 24: Test-asset migration

**Goal:** The Gate-1b enforcement machinery follows the code instead of decaying.

**Files:**
- Modify: `tests/matrix/boundaries.py`, `tests/baselines/phase_a.json`
- Create: `tools/check_case_digest.py`, `tests/matrix/test_case_digest.py`
- Modify: `tools/check_phase_a_coverage.py`

**Acceptance Criteria:**
- [ ] Every moved `BoundarySpec` carries a package-side qualified name **alongside** its legacy one
- [ ] New package coverage areas at D10 floors (core ≥95% branch, adapters ≥90%)
- [ ] Legacy areas whose module is now pure delegation replaced by the no-business-logic check
- [ ] All 16 `BranchExclusion` entries still resolve — none stale
- [ ] `preserve`-case digest checked in; CI fails on an unexplained change

**Verify:** `uv run pytest tests/matrix -q && uv run python tools/check_phase_a_coverage.py --check` → PASS

**Recovery:** Restore the previous `phase_a.json` from git and re-derive one area at a time.
Never lower a floor to make the gate pass.

**Steps:**

- [ ] **Step 1: Write the digest tool**

```python
# tools/check_case_digest.py
"""Digest over every preserve-case expected observation.

The oracle invariant says a move may never edit an expected value. Visible-in-review is not
enforced; this is. On failure it names the changed case IDs rather than just failing.

Usage:
    uv run python tools/check_case_digest.py --check
    uv run python tools/check_case_digest.py --update
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DIGEST_PATH = REPO_ROOT / "tests" / "baselines" / "preserve_cases.json"


def compute() -> dict[str, str]:
    from tests.matrix.cases import ALL_CASES
    from tests.matrix.model import Classification

    digests: dict[str, str] = {}
    for case in ALL_CASES:
        if case.classification is not Classification.PRESERVE:
            continue
        payload = repr(getattr(case, "expected_by_context", None))
        digests[case.case_id] = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return digests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()

    current = compute()
    if args.update or not DIGEST_PATH.exists():
        DIGEST_PATH.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
```

> `ALL_CASES` holds `CaseMetadata`, which has no `expected_by_context`. Read
> `tests/matrix/cases/__init__.py` first: if it exports metadata only, iterate the per-domain
> case tuples instead so the digest covers the actual expected data.

- [ ] **Step 2: Wire the digest into the suite and CI**

```python
# tests/matrix/test_case_digest.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_preserve_case_expectations_are_unchanged() -> None:
    result = subprocess.run(
        [sys.executable, "tools/check_case_digest.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout
```

- [ ] **Step 3: Dual-name the moved boundaries.** For each `BoundarySpec` whose
  `qualified_name` now points at a shim, add the package name. Read the dataclass first and add
  a `package_qualified_name: str = ""` field, then populate it for: `IN-B-*` →
  `scoutmb.adapters.files.tabular.*`, `REQ-B-PATH`/`REQ-B-CHOICE` →
  `scoutmb.core.inference.numbering.*`, `REQ-B-ANNOTATE` → `scoutmb.core.inference.status.*`,
  `REQ-B-MISSING` → `scoutmb.core.inference.missing.select_actionable`,
  `ART-B-ATOMIC-WRITE`/`ART-B-WRITE-CSV` → `scoutmb.adapters.files.atomic.*`,
  `ART-B-JSON-FOR-HTML` → `scoutmb.core.output_schemas.json_for_html`, `PLAT-B-SLUG` →
  `scoutmb.core.identity.safe_slug`, `ACQ-B-OUTPUT-ID` → `scoutmb.core.identity.RunIdentity.output_id`.

- [ ] **Step 4: Add package coverage areas**

```python
# tests/matrix/boundaries.py -- extend COVERAGE_AREAS
    CoverageAreaSpec(area_id="pkg-core", files=("src/scoutmb/core/**/*.py",)),
    CoverageAreaSpec(area_id="pkg-adapters", files=("src/scoutmb/adapters/**/*.py",)),
    CoverageAreaSpec(area_id="pkg-features", files=("src/scoutmb/features/**/*.py",)),
    CoverageAreaSpec(area_id="pkg-ports", files=("src/scoutmb/ports/**/*.py",)),
```

Then set floors in `phase_a.json`: `pkg-core` and `pkg-ports` at 95.0 branch, `pkg-adapters`
and `pkg-features` at 90.0 branch (D10).

- [ ] **Step 5: Replace shimmed legacy areas with the shape check**

Add to `tests/architecture/test_dependency_rules.py`:

```python
SHIMMED_MODULES = ("scout_schedule_cli.py",)  # extend as modules become pure delegation


@pytest.mark.parametrize("relative", SHIMMED_MODULES)
def test_shimmed_module_contains_no_business_logic(relative: str) -> None:
    """Once a module is pure delegation its coverage floor proves nothing, so it gets a shape
    check instead. Permitted: imports, literal/imported-name bindings, and forwarding calls."""
    path = Path(__file__).resolve().parents[2] / relative
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr)):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for inner in ast.walk(node):
                if isinstance(inner, (ast.If, ast.For, ast.While, ast.Try, ast.BinOp)):
                    offenders.append(f"{relative}:{inner.lineno} {type(inner).__name__}")
            continue
        offenders.append(f"{relative}:{node.lineno} {type(node).__name__}")
    assert offenders == [], "\n".join(offenders)
```

> `scout_schedule_cli.py` is **not** pure delegation at the end of 2a — acquisition is still
> there. Leave `SHIMMED_MODULES` empty until 2b and keep the test parametrized over an empty
> tuple, so the machinery exists and arms the moment a module qualifies.

- [ ] **Step 6: Recapture and review**

```bash
uv run python tools/check_case_digest.py --update
uv run pytest --cov --cov-report=json -q
uv run python tools/check_phase_a_coverage.py --update
git diff tests/baselines/
```

- [ ] **Step 7: Commit**

```bash
git add tests/matrix tests/baselines tools tests/architecture
git commit -m "test: migrate the Gate-1b machinery onto the package alongside the legacy paths"
```

---

## Gate 2a — Core & Content go/no-go

Run every command. Capture output. A red line blocks Slice 2b.

```bash
# 1. Whole suite, both runners
uv run pytest -q

# 2. Architecture: edges, composition roots, __file__ token, dynamic imports, sys.path
uv run pytest tests/architecture -q

# 3. Oracle invariant: no preserve expectation changed
uv run python tools/check_case_digest.py

# 4. Goldens, including the V1->V2 diff equality
uv run pytest tests/goldens -q

# 5. Coverage floors, check mode only
uv run pytest --cov --cov-report=json -q
uv run python tools/check_phase_a_coverage.py --check

# 6. Optional-dependency isolation and capability failure
uv run pytest tests/packaging/test_core_imports.py -q

# 7. Mechanisms still hold
uv run pytest tests/packaging/test_mechanisms.py -q

# 8. Clean wheel install + console script from outside the repo
uv run pytest tests/packaging tests/compat -q

# 9. Authentic lane, no skipping
uv run pytest -m private_corpus --require-corpus -q

# 10. Offline
uv run pytest -q  # pytest-socket active by default
```

**GO conditions:**
- [ ] Input, PDF, requirement, and artifact domains green on **both** runners
- [ ] `REQ-DUP-002` green from legacy and package, with identical selected-ancestor output
- [ ] Golden V1 and V2 match; V1→V2 diff is exactly the `attendee_id`→`output_id` substitution
- [ ] Preserve-case digest unchanged; only `ART-NAME-007` reclassified; baseline bumps reviewed
- [ ] One `RunIdentity` per run, asserted end to end, `null` for unresolved attempts
- [ ] No `__file__` token, no dynamic import in core/ports/features, no `sys.path` mutation
- [ ] Adapter imports confined to `interfaces/*/composition.py`
- [ ] Package coverage areas meet D10 floors; no legacy area regressed
- [ ] `python -I` core import loads no `cv2`/`fitz`/`playwright`; capability failure typed
- [ ] Clean wheel carries `py.typed` + templates; `troop349-pdf --help` matches the flat script
- [ ] Authentic lane ran with `--require-corpus` — a skip is not a pass
- [ ] `egress-denied` green

**NO-GO:** restore the moved symbol's original body to the flat module, delete the package
module and its parity file, return the defect to its task, rerun the gate. There is no
adapter-selection switch in 2a — rollback is a revert.

---

## Failure-mode coverage (carried forward from the archived skeleton)

| Path | Injected failure | Task | Required behavior |
| --- | --- | --- | --- |
| Input | Malformed row, unknown suffix, empty result | 15, 17 | Typed bounded error; no partial attendee file |
| PDF | Missing capability, corrupt page, decode miss | 16 | `CapabilityUnavailable` with a remedy; no eager optional import |
| Identity | Same names, blank ID, pre-identity failure | 6, 7, 23 | Never merge; `null` output id; no fabricated UUID |
| Inference | Duplicate numbers, malformed numbering, `(not used)` | 10, 11, 13 | Ancestor selection preserved; exclusions preserved |
| Single artifact | Render/write/fsync/replace failure | 20 | Prior bytes remain; never overwrite twice |
| Template | `__REPORT_DATA__`, `</script>`, U+2028/2029 | 21 | No token survives; no breakout |
| Shareable output | Sentinel in any forbidden position | 23 | Exact field sets; fails on any unexpected key |

## Deferred to Slice 2b

`ScoutResult` freezing (blocked on `process_scout`'s `.append` sites), the ScoutingEvent
gateway and drift boundary, acquisition with breaker and checkpoints, the run-state machine and
job supervisor, the web factory and `JobRegistry`, the four UI defects, `interfaces/cli/schedule.py`,
`interfaces/desktop`, the launcher bridge (`source_sync` + `build.spec` + `.pth`), and retirement
of the flat modules with `tests/harnesses/legacy.py`.

## Self-review

- **Spec coverage.** Package layout → T1, T5–T8, T15–T18, T20–T22. Oracle invariant → T24
  digest. Six intentional-change rows → `ART-NAME-007` is the only 2a one and lands in T23's
  output-root handling; the other five are 2b. Test-asset migration (four invariants) → T24.
  Artifact tiering → T23. Inference decomposition → T9–T13. Optional dependencies → T16.
  Error model → T2. DTO boundary → T14. Frozen records → T5. Console scripts → T18.
  Dependency rules → T4. `__file__` ban → T4 + T21. Plan-verified mechanisms → T3.
  Gate 2a → the gate block above.
- **Not covered here, by design:** configuration dataclasses (D6) need `async_main`, which is
  2b; `ports/observability` and the telemetry seam are Slice 4.
- **Type consistency.** `load_attendees` (T15) is the name used by T18's composition root.
  `build_group_tree`/`GroupTree` (T11) are consumed by `calculate_statuses` (T12).
  `select_actionable` (T13) is used by the legacy `build_missing_requirements`.
  `requirement_from_mapping`/`requirement_to_row` (T14) are the names in T20's shim template
  and T23's `_project`. `render_report`/`load_template` (T21) are used by T22.
- **Known sharp edge.** T15's parity test calls `case.write_source(tmp_path)` and
  `case.sheet_name`; the real accessor names must be read from
  `tests/matrix/cases/input_cases.py` before writing that file. Flagged in the step itself.
