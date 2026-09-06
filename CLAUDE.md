# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A `uv`-managed Python package (`scoutmb`, under `src/scoutmb/`) that pulls Scout merit-badge
class schedules and requirement completion off `scoutingevent.com`, plus a self-bootstrapping
Windows/macOS installer (`bootstrap/`) that ships it as a thin native launcher. Three console
scripts (`pyproject.toml`'s `[project.scripts]`):

- **`troop349-pdf`** — extracts attendee name, registrant type, and QR-code contents from
  printed class-schedule PDFs, producing a `scouts.csv`.
- **`troop349-schedule`** — consumes that CSV, drives a real browser to each attendee's QR URL
  to obtain a session, then pulls schedule/requirement JSON directly from the site's AJAX
  endpoint and generates CSV/JSON/HTML output.
- **`troop349`** — launches both stages behind a local native window (or the system browser
  with `--browser`) instead of the command line.

Run `troop349-pdf` only when starting from PDFs; if you already have a CSV/XLSX/JSON of
names+QR URLs, go straight to `troop349-schedule`. See `README.md` for full usage.

## Setup and running

```bash
uv sync --locked --all-extras
uv run playwright install chromium   # only needed for troop349-schedule / troop349
```

`--all-extras` pulls in the `pdf` (PyMuPDF, opencv-python-headless) and `acquisition`
(Playwright) optional groups. Every dependency, including PyMuPDF, opencv-python-headless, and
pywebview's PyObjC frameworks, publishes native arm64/universal2 wheels on Apple Silicon — no
Rosetta or source build needed.

```bash
uv run troop349-pdf "Class_Schedule_2026_07_06.pdf" --output scouts.csv --strict
uv run troop349-schedule --input scouts.csv --output heritage-results
```

Run the full test suite (default lane — `live_service`/`playwright`/`release` are deselected
unless explicitly requested):

```bash
uv run pytest -q
```

`ruff check .` / `ruff format --check .` / `mypy` all run clean; `.github/workflows/ci.yml`
runs each as its own job (see Testing and CI below). `--debug-dir` (`troop349-pdf`) and
`--headed` (`troop349-schedule`) are the primary tools for diagnosing extraction/scraping
failures.

## Architecture

`src/scoutmb/` follows a layered structure, enforced by `tests/architecture/test_dependency_rules.py`'s
`ALLOWED` import registry (an `interfaces`-layer module may import `features`/`adapters`/etc.;
`core` may only import `errors`):

- **`core/`** — pure domain logic: models, identity, output schemas, and the requirement-tree
  inference engine (`core/inference/`). No I/O, no adapters.
- **`ports/`** — `Protocol`-per-collaborator seams (`clock.py`, `checkpoint_store.py`,
  `observability.py`, ...), one real implementation each in `adapters/`. Never a generic
  catch-all abstraction — each port is scoped to exactly the one thing it stands in for.
- **`adapters/`** — real implementations: `pdf/` (PyMuPDF/OpenCV extraction), `scoutevent/`
  (Playwright and HTTP gateways to the live site), `files/` (atomic CSV/JSON/checkpoint I/O),
  `html/` (the report template), `observability/` (the no-op telemetry seam).
- **`features/`** — orchestration: `ingest/` (PDF → CSV), `acquisition/` (the schedule-download
  pipeline, retry policy, circuit breaker), `reporting/` (HTML/CSV/JSON/email output).
- **`interfaces/`** — the only layer allowed to import `adapters` directly (via a
  `composition.py` in each of `cli/`, `web/`; `tests/architecture` enforces this too):
  `cli/` (the two console-script entry points), `web/` (the local FastAPI UI `troop349` embeds),
  `desktop/` (the pywebview wrapper around `web/`).
- **`config.py`**, **`errors.py`**, **`network_policy.py`**, **`logging_setup.py`**,
  **`runtime/`** — cross-cutting, single-file/single-purpose modules living directly under
  `src/scoutmb/`, not nested under any of the above layers.

`bootstrap/` is a separate, stdlib-only package: it never imports `scoutmb` (see
`bootstrap/python_env.py`'s own docstring) since its entire job is provisioning the isolated
Python environment `scoutmb` actually runs in. It builds into a thin (~12MB) native
Windows/macOS launcher via `bootstrap/build.spec` (PyInstaller) that downloads/verifies a
hash-pinned embeddable Python and the app source at first run — see `bootstrap/README.md`.

### Requirement completion inference

`core/inference/` (used only for the HTML report, not the CSV/JSON exports) is the most
intricate piece of domain logic in the package:

- `numbering.py` parses ScoutingEvent's requirement-number strings (e.g. `"3b"`, `"(c)"`) into a
  comparable path tuple, tracking the last-seen top-level number to handle malformed numbers
  like `"#(c)"` that omit it.
- `tree.py` reconstructs a parent/child tree from these paths per (scout, class) group, with a
  header-stack fallback for cases where strict path-prefix matching fails.
- `status.py` recursively derives a `complete`/`complete_check`/`incomplete` status per
  requirement: a parent is complete if the API already marked it complete, or if enough children
  are satisfied — either all of them, or, for "Do TWO of the following"-style choice
  requirements (`missing.py` parses the wording), at least the stated count.
  `complete_check` signals "inferred, should double-check" rather than an authoritative complete
  from the API.

## Testing and CI

No `raw_data/`-backed private corpus exists in a fresh checkout — `tests/private_corpus/` is
skipped automatically when it's absent; it's a `.gitignore`d local-only symlink, never a CI
requirement.

Pytest markers (`pyproject.toml`'s `[tool.pytest.ini_options]`), all deselected by default:

- `live_service` — the *one* test (`tests/live_service/test_real_scoutingevent_read.py`) allowed
  to touch the real site; read-only, requires `SCOUTMB_ALLOW_LIVE_SERVICE=1`.
- `playwright` — needs a real installed browser.
- `release` — builds a real PyInstaller artifact; slow, native-runner-specific.

`.github/workflows/ci.yml` jobs: `static-quality` (ruff/mypy/lock-check), `architecture`,
`test` (ubuntu + windows), `coverage-baseline` (pinned to macos-latest — several OS-dispatch
branches only execute on one platform per host), `egress-denied` (offline default lane with
non-loopback egress blocked at the OS level), `supply-chain` (`uv audit` + license-compliance
gate against `release/license-policy.toml`), `performance` (pinned to macos-latest, for
reproducible timing).

`.github/workflows/release.yml` (`workflow_dispatch` only) builds and size-budget-checks the
native installer on each platform's own runner — never cross-built.

## Data/privacy notes

QR URLs and attendee IDs act as bearer access tokens for real scouts' data. `.gitignore`
excludes generated output directories (`scouting-output*/`, `heritage-results*/`), input files
(`scouts*.csv`, `*.xlsx`), and the local `raw_data` corpus symlink — keep it that way and don't
commit real PDFs, CSVs, or generated reports. `permissions.deny` in `.claude/settings.json`
blocks Claude from reading these paths directly.

## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
