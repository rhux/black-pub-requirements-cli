# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Two standalone Python CLI scripts (no package, no build step, no test suite) that form a two-stage pipeline for pulling Scout merit-badge class schedules and requirement completion off `scoutingevent.com`:

1. **`pdf_to_scouts.py`** — extracts attendee name, registrant type, and QR-code contents from printed class-schedule PDFs, producing a `scouts.csv`.
2. **`scout_schedule_cli.py`** — consumes that CSV, drives a real browser to each attendee's QR URL to obtain a session, then pulls schedule/requirement JSON directly from the site's AJAX endpoint and generates CSV/JSON/HTML output.

Run stage 1 only when starting from PDFs; if you already have a CSV/XLSX/JSON of names+QR URLs, go straight to stage 2.

## Setup and running

Originally Windows-only; also runs on macOS (verified on Apple Silicon — every dependency, including PyMuPDF, opencv-python-headless, and pywebview's PyObjC frameworks, has native arm64/universal2 wheels, so nothing needs Rosetta or a source build).

### Windows/PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium   # only needed for scout_schedule_cli.py
```

Run the pipeline:

```powershell
python .\pdf_to_scouts.py ".\Class_Schedule_2026_07_06.pdf" --output .\scouts.csv --strict
python .\scout_schedule_cli.py --input .\scouts.csv --output .\heritage-results
```

### macOS (bash/zsh)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium   # only needed for scout_schedule_cli.py
```

Run the pipeline:

```bash
python pdf_to_scouts.py "Class_Schedule_2026_07_06.pdf" --output scouts.csv --strict
python scout_schedule_cli.py --input scouts.csv --output heritage-results
```

There is no test suite, linter, or CI config in this repo. Verify changes by running the scripts against real or sample input and inspecting the generated CSV/JSON/HTML output.

`--debug-dir` (pdf_to_scouts.py) and `--headed` (scout_schedule_cli.py) are the primary tools for diagnosing extraction/scraping failures.

## Architecture

### `pdf_to_scouts.py` — PDF → CSV

- `expand_pdf_inputs`: resolves CLI args that may be files, directories (optionally `--recursive`), or glob patterns — needed because Windows shells don't expand globs themselves.
- `extract_page_identity`: pulls attendee name/registrant type from page text by locating fixed labels ("Attendee Information", "Registrant").
- QR decoding is tried in two tiers, cheapest first:
  1. `decode_embedded_qr` — scans embedded page images for square, QR-code-shaped candidates and decodes directly (fast path, works for most PDFs).
  2. `decode_rendered_qr` — falls back to rendering the page as a bitmap at multiple DPIs (`--render-dpi`, default 144/200/300/400) and multiple crop regions (`page_regions`), since some PDFs embed the QR as vector content rather than a raster image.
  `decode_variants` additionally tries Otsu thresholding and multiple upscales against each candidate image to squeeze out marginal decodes.
- `choose_qr_value` prefers a decoded value starting with the ScoutingEvent mobile URL prefix over other decoded strings (a page can contain more than one QR-shaped image).
- `normalize_obvious_case` fixes a narrow OCR artifact (`MIles` → `Miles`) via a regex heuristic, while deliberately not touching valid mixed-case names like `McDonald` or `O'Neil` — disable with `--no-normalize-obvious-case` if it ever misfires on a real name.
- Output CSV columns `Attendee Name` / `Registrant Type` / `QR Code Contents` are the exact contract `scout_schedule_cli.py` expects; the remaining columns (source PDF, page, decode method) are for auditing only and are ignored downstream.
- Adults are excluded by default via `DEFAULT_ADULT_TYPES`; `--adult-type` extends the exclusion set, `--include-adults` disables filtering entirely.

### `scout_schedule_cli.py` — CSV → live schedule/requirement data → reports

- **Why Playwright is used at all**: `scoutingevent.com`'s mobile UI runs old jQuery Mobile code that throws before its schedule `listview` finishes initializing, so the rendered page is broken. The CLI uses a real Chromium context only to establish the PHP session cookie and trigger the initial schedule AJAX call (`navigate_and_trigger_schedule`), then reads the raw JSON response directly instead of relying on the DOM. Subsequent per-class requirement requests are issued as in-page `fetch()` calls (`post_requirement`) reusing that same session — no further navigation needed.
- `DEAD_ASSET_HOSTS` are two known JS asset hosts that currently hang; requests to them are aborted by default (`--allow-dead-assets` to stop blocking them) since the JSON endpoints don't depend on them.
- `load_inputs` dispatches on file suffix (`.xlsx` / `.csv` / `.json` / anything else treated as line-delimited) and each loader tolerates several header-name aliases (`norm_header` + `first_matching_key`) so differently-formatted input files still work.
- One `ScoutResult` is built per attendee, holding its `ClassRecord`s and `RequirementRecord`s plus any non-fatal `errors` (a scout with errors doesn't stop the batch — the run's exit code reflects whether any scout had errors, per-scout failures are recorded and processing continues).
- **Requirement completion inference** (`annotate_requirement_statuses`, used only for the HTML report, not the CSV/JSON exports) is the most intricate piece of logic in the codebase:
  - `requirement_path` parses ScoutingEvent's requirement-number strings (e.g. `"3b"`, `"(c)"`) into a comparable path tuple, tracking the last-seen top-level number to handle malformed numbers like `"#(c)"` that omit it.
  - A parent/child tree is reconstructed from these paths per (scout, class) group, with a fallback using a header stack for cases where strict path-prefix matching fails.
  - `calculate` recursively derives a `complete` / `complete_check` / `incomplete` status per requirement: a parent is complete if the API already marked it complete, or if enough children are satisfied — either all of them, or, for "Do TWO of the following"-style choice requirements (`choice_requirement_count` parses the wording), at least the stated count. `complete_check` signals "inferred, should double-check" rather than an authoritative complete from the API.
- `write_html_report` embeds a single self-contained HTML template (inline `<style>`/`<script>`, JSON data injected via `json_for_html` which escapes for safe embedding in a `<script type="application/json">` block) — there is no separate frontend build; edit the template string in place.
- `write_outputs` is the single place that fans results out to all output files: `scouts.json` (full nested payload), `classes.csv`, `requirements.csv`, `errors.csv`, `summary.json`, `raw/` (untouched request payloads for auditing), and the HTML report.

## Data/privacy notes

- QR URLs and attendee IDs act as bearer access tokens for real scouts' data. `.gitignore` already excludes generated output directories (`scouting-output*/`, `heritage-results*/`), input files (`scouts*.csv`, `*.xlsx`), and `.venv/` — keep it that way and don't commit real PDFs, CSVs, or generated reports.

<!-- code-review-graph MCP tools -->
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
