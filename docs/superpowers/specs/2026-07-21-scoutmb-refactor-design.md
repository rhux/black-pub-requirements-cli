# scoutmb: Restructure Design

**Date:** 2026-07-21
**Status:** Approved design, pending implementation plan
**Supersedes:** `docs/refactor-plan.md` (merged into this document)

## Problem

The repository began as a quick script and accreted into a real application: two CLI
pipelines, a FastAPI web UI, a desktop launcher, and a 14-module self-bootstrapping
Windows installer.

| Component | Size | Role |
| --- | --- | --- |
| `scout_schedule_cli.py` | 1,798 lines | Stage 2: scrape, infer, report |
| `pdf_to_scouts.py` | 580 lines | Stage 1: PDF to CSV |
| `ui/` | 340 lines Python + 329 JS | Local FastAPI app |
| `bootstrap/` | 14 modules | Windows self-installing launcher |
| `run_app.py` | 90 lines | Native-window entry point |

There is no package, no `pyproject.toml`, no tests, no linter, no type checker, and no
CI. Nothing pins current behavior. The structural defects are concrete, not stylistic —
all line references below were verified against the current tree:

1. **`scout_schedule_cli.py` has no internal boundaries.** One module holds argument
   parsing, four input loaders, Playwright control, AJAX scraping, requirement-status
   inference, email rendering, a 658-line embedded HTML string, and six output writers.
2. **`process_scout` (141 lines) fuses browser control, retry policy, deduplication,
   JSON-to-record mapping, and filesystem writes.** None of it is testable without a
   live Chromium.
3. **`argparse.Namespace` is threaded into the scraping layer.** `ui/server.py:188-201`
   hand-builds a fake Namespace with 12 fields, and the core defends itself with
   `getattr(args, "channel", None)` (`:1726`) and `getattr(args, "email_report", False)`
   (`:1779`) — proof that options already silently default on the UI path.
4. **Requirement inference is invoked twice per run** — `:783` inside
   `build_missing_requirements` and `:980` inside `write_html_report` — through two
   different entry paths receiving differently-shaped input, and it mutates dicts in
   place (`:683`, `:709`, `:735-737`, `:765-766`).
5. **Two `sys.path` hacks.** `ui/server.py:25` inserts the repo root; `python_env.py:62`
   patches the app directory into the embeddable Python's `._pth`.
6. **Heavyweight imports block testing.** `scout_schedule_cli.py:27` imports `openpyxl`
   at module scope, so importing even `requirement_path` requires every dependency.
7. **`parse_args()` takes no `argv`** (`:88`). Adding it is a prerequisite for testing
   anything CLI-shaped.
8. **Unreferenced background tasks.** `ui/server.py:162,223` call
   `asyncio.create_task(worker())` without retaining the result; CPython holds only weak
   references, so a long job can be collected mid-execution.
9. **`print()` is the logging system** — 19 calls, with nine `except Exception` sites,
   three swallowing silently (`:363`, `:400`, `:468`). The UI receives progress through
   a separate, unrelated channel.
10. **Pervasive nondeterminism.** Timestamps, `random.uniform`, and `uuid4` are called
    directly from business logic, making output unreproducible and untestable.
11. **Untyped, unvalidated external payloads.** `scoutingevent.com` responses flow
    through as `dict[str, Any]`; an upstream field rename produces silently wrong
    completion status rather than a visible failure.
12. **Duplication.** `DEFAULT_ADULT_TYPES` (`pdf_to_scouts.py:23`) is re-declared as a
    literal set at `scout_schedule_cli.py:212`; header-alias lists are duplicated three
    times across the loaders.
13. **User data commingled with replaceable source.** `scouts.csv`, `pdf-uploads/`, and
    `runs/` live in the directory the launcher overwrites on each start.

## Goals

- A `src/`-layout package with typed boundaries, an injectable transport seam, a real
  test suite, and standard Python tooling.
- Reproducible output, so behavior can be pinned by golden tests.
- Resilience to upstream schema drift, with drift made visible rather than silent.
- A launcher that is portable to macOS and can update itself.
- Preserve current behavior; treat behavior changes as separate, individually tested
  decisions.

## Non-goals

- Rewriting the inference algorithm. It is characterized and preserved.
- Shipping a signed macOS build. Notarization is a purchasing decision (Apple Developer
  Program, USD 99/yr) tracked separately.
- Replacing the frontend with a framework. The report and UI stay vanilla.

## Constraints

- **Runtime target is Python 3.12.** `requires-python = ">=3.12"`, ruff
  `target-version = "py312"`, mypy `--python-version 3.12`, 3.12 primary in CI. The dev
  venv is 3.14; a 3.13/3.14-only API would ship broken with no diagnostic path.
- **No real Scout data in the repository, ever.** QR URLs and attendee IDs are bearer
  tokens for real minors' records. `/raw_data/` is gitignored (`.gitignore:13`).
- **The launcher's audience is non-technical.** Double-click to run; never touch or
  require a system Python.
- **The app is not currently deployed.** No data-migration code is needed, and breaking
  changes to the app-local layout are permitted.
- **The upstream API is not ours.** `scoutingevent.com` may change payload shape without
  notice. The design must tolerate this rather than assume stability.

---

## ⚠️ Coupled hazards — read before any code moves

These are verified, not hypothetical, and together they destroy user data.

### Hazard 1 — `__file__`-derived data paths

```python
REPO_ROOT = Path(__file__).resolve().parent.parent   # ui/server.py:24
SCOUTS_CSV = REPO_ROOT / "scouts.csv"                # :35
PDF_UPLOADS_DIR = REPO_ROOT / "pdf-uploads"          # :36
RUNS_DIR = REPO_ROOT / "runs"                        # :37
```

Today `__file__` is `app_dir/ui/server.py`, so `REPO_ROOT` resolves to `app_dir` and
user data lands correctly beside the app. After the move to `scoutmb/ui/app.py`,
`.parent.parent` silently becomes `app_dir/scoutmb` — **user data relocates inside the
package directory.**

This is *worse* under the wheel deployment than under loose-file sync: the installed
package lives at `venv/lib/site-packages/scoutmb/`, so data would land inside a
directory that `pip install --force-reinstall` replaces wholesale.

**Fix:** `UiSettings` takes an explicit `data_root`, defaulting to
`Path(os.environ.get("SCOUTMB_DATA_DIR") or Path.cwd())`. The launcher sets
`SCOUTMB_DATA_DIR` to `<app root>/data`. **Never derive data paths from `__file__`
again** — enforced by a lint rule and a regression test.

### Hazard 2 — destructive install replacing a permissive sync

`source_sync.py`'s docstring promises *"never a directory wipe — scouts.csv,
pdf-uploads/, and runs/ live in the same app\ folder as user data and must survive
untouched."* That comment is load-bearing. Both the wheel install and any `rmtree`-based
sync violate it — safely **only if** the package directory holds no user data, which is
exactly what Hazard 1 would break.

**Fix 1 and 2 in the same phase**, with the regression test in Phase 7: create a
pre-existing `data/scouts.csv`, run a full reinstall, assert the file survives.

---

## Architecture

### Package layout

```
pyproject.toml   uv.lock   requirements.txt (generated, pinned — installer input)
src/scoutmb/
  __init__.py  __main__.py  errors.py  config.py  runtime.py  progress.py  logging_setup.py

  domain/      models.py      ScoutInput / ClassRecord / RequirementRecord / ScoutResult
               enums.py       RequirementStatus StrEnum; SECTION_HEADER_TYPE_ID
               text.py        clean_html_description (3 callers, crosses layers)
               registrants.py ADULT_REGISTRANT_TYPES (kills the pdf:23 / cli:212 duplicate)

  inference/   PURE — no I/O; takes and returns dataclasses, never dicts
               numbering.py   CHOICE_COUNT_WORDS, requirement_path, choice_requirement_count
               tree.py        grouping, parent linking, header-stack fallback
               status.py      the de-nested `calculate` closure
               missing.py     build_missing_requirements, keyed on node index

  inputs/      headers.py     norm_header, first_matching_key, alias lists (kills 3 duplicates)
               loaders.py     xlsx / csv / json / text        pipeline.py  load_inputs

  scrape/      payloads.py       PURE mapping + anti-corruption layer + drift detection
               ports.py          SchedulePort Protocol, ScheduleFetch
               playwright_port.py  the only module that imports playwright
               retry.py  raw_store.py  runner.py

  reporting/   view_model.py  html.py  writers.py  summary.py
               templates/report.{html,css,js}     ← the 658-line string, split three ways

  emails/      render.py  export.py  templates/email.html   (NOT `email/` — stdlib collision)
  pdf/         discovery.py  identity.py  qr.py  extract.py  pipeline.py  export.py
  storage/     csvio.py  jsonio.py  naming.py                (NOT `io/` — stdlib collision)
  cli/         app.py  args_scrape.py  args_extract.py  args_ui.py  console.py
  ui/          settings.py  app.py (create_app factory)  jobs.py  routes/  static/  desktop.py

tests/{unit,contract,integration,fixtures,factories}/
tools/scrub_fixtures.py
bootstrap/     platforms/  manifest.py  …      (repo root, outside the package)
```

**No junk drawers.** Every module is named for a *subject* ("requirement numbering",
"CSV writer"), never a *role*. A pre-commit hook rejects `utils.py`, `helpers.py`, and
`common.py` under `src/`. Placement follows consumers: `clean_html_description` has three
callers across layers → `domain/text.py`; `truthy` has one, the payload mapper →
`scrape/payloads.py`; `safe_slug` makes filenames → `storage/naming.py`.

`bootstrap/` **stays at the repo root**, outside the package. It runs before the
application's dependencies exist, may import only the standard library, is frozen
separately, and deliberately imports no app code. Add
`[tool.hatch.build] exclude = ["bootstrap"]`.

### Console entry point

`[project.scripts] troop349 = "scoutmb.cli.app:main"`, with unified subcommands
`extract-pdf`, `download`, and `ui`. Root shims (`pdf_to_scouts.py`,
`scout_schedule_cli.py`) re-export during migration and **emit a `DeprecationWarning`
naming `troop349`** — without that, the flat layout lives forever in muscle memory and
in every doc a future agent reads. Shims are deleted in the cleanup phase.

### Typed config replaces `Namespace` threading

Frozen slotted dataclasses in `config.py`: `BrowserOptions`, `PacingOptions`,
`InputOptions`, `ReportOptions`, composed into `ScrapeConfig` and `ExtractConfig`.
`argparse` populates them in `cli/args_*.py`; **the `Namespace` never leaves that
module.** `ui/server.py:188-201` collapses to a `ScrapeConfig(...)` construction, which
is the point — a new option can no longer silently default to `False` on the UI path, so
both `getattr(args, …)` calls are deleted.

Magic numbers become named fields: retry attempts (`range(1, 4)` at `:538`), backoff
(`500 * attempt` at `:546`), jitter (`(0.5, 2.0)` at `:1765`).

`--quiet` leaves the config entirely and becomes global `-q`/`-v` verbosity, which fixes
`pdf_to_scouts.py:571` (prints unconditionally despite guards at `:515` and `:557`) by
construction.

### Determinism

All nondeterminism moves behind injected collaborators in a `RunContext`:

```python
@dataclass(frozen=True, slots=True)
class RunContext:
    clock: Clock          # now() -> datetime
    ids: IdFactory        # new_id() -> str
    rng: random.Random    # seeded
    progress: ProgressSink
```

| Source | Location | Replaced by |
| --- | --- | --- |
| `time.strftime` → `generated_at_local` | `scout_schedule_cli.py:1644` | `ctx.clock` |
| `datetime.now()` → `generated_at_iso` | `:1645` | `ctx.clock` |
| `random.uniform(0.5, 2.0)` pacing | `:1765` | `ctx.rng` |
| `uuid4()` operation IDs | `ui/server.py:110,174` | `ctx.ids` |
| `time.strftime` run IDs | `ui/server.py:65` | `ctx.clock` |

Retry additionally needs an **injected sleep**: today `page.wait_for_timeout` both sleeps
*and* is bound to the page, so retry tests would take real seconds and require a browser.

Without this section, golden comparison is impossible — every report embeds a wall clock.

### Requirement inference

Decomposed, **not relocated**. Moving the 105-line function intact would preserve the
fusion that makes it untestable:

- `inference/numbering.py` — `requirement_path`, `choice_requirement_count`
- `inference/tree.py` — grouping, parent linking, header-stack fallback
- `inference/status.py` — the `calculate` closure, de-nested
- `inference/missing.py` — `build_missing_requirements`

The boundary is **pure dataclasses in, pure dataclasses out** — no dicts cross it, and
no in-place mutation. This is what lets the `Note.` question (see Testing) be settled by
a direct test of tree construction rather than by inspecting whole-report output.

**The double-invocation trap.** Inference runs at `:783` (nested `scouts.json` dicts) and
`:980` (`asdict(RequirementRecord)`). Unifying onto one typed function could change
results if the shapes diverge — for example `requirement_type_id` as `int` vs `str`.
**Both call sites are pinned separately in Phase 1, before unification.**

### External payload handling

Because the upstream schema is not ours, `scrape/payloads.py` is an anti-corruption
layer, not a type declaration:

```python
def parse_requirement_rows(
    payload: Mapping[str, Any],
) -> tuple[list[RequirementRecord], list[SchemaDrift]]: ...
```

- **Unknown fields are ignored.** New upstream fields never break a run.
- **Missing expected fields are recorded, not raised** — each yields a `SchemaDrift`
  naming the field and context.
- **Drift is surfaced** in `errors.csv` and a `schema_drift` count in `summary.json`, so
  an upstream rename appears as a visible warning instead of a merit badge quietly
  reading "incomplete".
- **Coercion is explicit and total.** Flag parsing tolerates `"1"`, `"0"`, `""`, and
  `None` — the corpus contains 309 rows with `(None, None)` flags — and never raises.

`dict[str, Any]` appears only in `ports.py` and `payloads.py`. Everything downstream is
an owned, strictly typed model. Declaring the upstream shape as a `TypedDict` was
rejected: it would encode an assumption we cannot enforce and turn upstream renames into
silent `None`s.

### `process_scout` splits at a `SchedulePort`

```python
class SchedulePort(Protocol):
    async def open_scout(self, qr_url: str, fallback_name: str) -> ScheduleFetch: ...
    async def fetch_requirements(self, attendee_id: str, class_p4_id: str) -> Mapping[str, Any]: ...
    async def aclose(self) -> None: ...
```

Everything Playwright hides behind it. Above it, `payloads.py` is pure and synchronous:
`dedupe_schedule_rows`, `class_records_from_schedule`, `requirement_records_from_payload`.
A test loads a fixture and asserts a `list[ClassRecord]` — no browser, no async, no
network. **This single extraction makes roughly 80% of the scraping logic testable**, and
covers the field mapping and `None`-coalescing where real bugs live.

Retry moves to `retry.py` with injected sleep; raw-payload writes move to a
`RawPayloadStore` with a `NullRawStore` for tests. A `FakeSchedulePort` over fixture JSON
then exercises the full per-scout flow including error accumulation and exact error
strings.

### The 658-line template → package data, three files, `str.replace()`

The template uses **exactly one substitution** (`template.replace("__REPORT_DATA__", …)`
at `:1627`) — no f-string, no `.format()`. **No Jinja2.** It would add a runtime
dependency that changes `marker.compute_requirements_hash` and forces every install to
reprovision, and it would require escaping every `{`/`}` across 206 lines of CSS and 278
lines of JS full of `${…}` template literals. That mechanical edit is a real corruption
risk — the existing doubled-brace email template at `:886-893` (`body {{ font-family: … }}`)
already demonstrates the failure mode.

Split into `templates/report.{html,css,js}`, loaded via `importlib.resources.files(...)`
with an `lru_cache`. **Substitute in the order CSS → JS → DATA, always DATA last** —
scout data can contain the literal string `__REPORT_JS__` and survives JSON escaping, so
data-last makes injection impossible. Assert no `__REPORT_` token remains in the output,
and **test a scout named `__REPORT_JS__`.** Output stays a single self-contained file.

The email template moves to `emails/templates/email.html` with brace-doubling removed.

Same mechanism for `ui/static/`, but `create_app` must resolve it via
`importlib.resources`, not `Path(__file__).parent` (`server.py:38`), and mount it after
verifying existence rather than at import time (`:338-339` currently raises if absent).

### Deployment

`app/` as a synced source tree is eliminated. The application installs as a wheel.

```
<app root>/           # %LOCALAPPDATA%\ScoutingMeritBadges          (Windows)
                      # ~/Library/Application Support/ScoutingMeritBadges  (macOS)
  runtime/            # python-build-standalone — disposable
  venv/               # created from runtime/, holds the wheel + deps — disposable
  data/               # scouts.csv, pdf-uploads/, runs/ — SCOUTMB_DATA_DIR points here
  state/              # marker, browser channel, wheel cache, update throttle
  logs/
```

Splitting `runtime/` from `venv/` means a dependency change rebuilds only the venv, while
a Python version bump re-downloads the runtime. Because standalone Python plus a normal
venv is an ordinary Python environment, the `._pth` patching at `python_env.py:47-69`
disappears entirely, as does `ui/server.py:25`.

**Platform dispatch** replaces scattered `sys.platform` checks:

```
bootstrap/platforms/
  base.py       Protocol: app_root, python_exe, gui_python_exe,
                          ensure_webview, preferred_browser_channel, runtime_url
  windows.py    LOCALAPPDATA, WebView2, Edge, pythonw.exe, winreg
  macos.py      ~/Library/Application Support, WKWebView (no-op), Chrome
```

Two portability fixes are prerequisites, both currently making `bootstrap` unimportable
on macOS: `webview2.py:12` has a module-level `import winreg` and evaluates
`winreg.HKEY_*` at import — store hive *names* as strings, move the import into the
function, `getattr` there. `paths.py:33` does `os.environ["LOCALAPPDATA"]`, a bare
`KeyError` — use `.get()` with a diagnosable error. Then the module imports everywhere
and only the registry test is skipped.

**`bootstrap/manifest.py` is the single source of truth** for what the exe bundles,
imported by `build.spec` (spec files execute as Python), killing the duplicated manifest.
`hiddenimports` becomes `collect_submodules("bootstrap")`.

**Dependency pinning.** `pyproject.toml` declares ranges; `uv.lock` pins an exact
resolution; `requirements.txt` is **generated from the lock with exact pins** and remains
the installer's pip input. Ranges resolve to different PyMuPDF/opencv builds per Python
version, so a bug can be dependency-shaped and irreproducible locally. `requirements.txt`
gates `compute_requirements_hash`, so it must be reproducible. CI fails if it drifts from
the lock.

**Self-update.** The launcher queries GitHub Releases for a newer wheel, at most **once
per 24 hours** (recorded in `state/`), bounded by a **3 second** timeout. Any failure —
no network, timeout, malformed response — is logged and the installed version launches
anyway. **Startup never blocks on an update check**; the deployment environment is a
Scout camp with unreliable connectivity. Two safety requirements:

- **Playwright browser revalidation.** The `playwright` package is version-coupled to its
  browser binaries. After any update changing the resolved version, re-run browser
  installation before launching. Skipping this yields an app that starts and then fails
  mid-scrape, offline, at camp.
- **Rollback.** Retain the previous wheel in `state/`. After two consecutive launch
  failures, reinstall it and log the downgrade. An auto-updater without rollback can
  brick every installation simultaneously.

`marker.py` gains `wheel_version` + `wheel_hash`; `"scoutmb"` is added to
`config.SMOKE_TEST_IMPORTS` so the smoke test genuinely verifies an importable app.
`PLAYWRIGHT_BROWSERS_PATH` is set under `state/` so uninstall is one directory removal.

---

## Testing

### TDD discipline

The Iron Law — no production code without a failing test — applies to three kinds of
work in this plan. None is exempt.

**New code: strict red-green-refactor.** `SchedulePort`, `FakeSchedulePort`,
`JobRegistry`, `ProgressSink`, `RunContext`, `payloads.py` drift handling, `errors.py`,
platform dispatch, self-update, rollback, `manifest.py`, and the scrubber.

**Deliberate behavior changes: strict red-green-refactor.** The `no_html` →
`generate_html` inversion, the `troop349` CLI surface, `-q`/`-v` verbosity, drift
reporting, and returning a URL instead of calling `webbrowser.open` server-side.

**Code motion: characterization-first.** Pin current behavior, then move.
**Characterization tests pin bugs too** — where a test documents behavior we believe is
wrong, it is committed as-is with a comment, and the fix is a separate change with its
own failing test. Refactoring and bug-fixing never share a commit.

### Phase sequencing that keeps CI green and RED real

Phase 1 must end green, and later phases must retain a genuine RED step. Reconciled by
explicit order:

1. **Phase 1.** Characterization tests import the **flat modules** and pass. Real safety
   net, green CI.
2. **Phase 2, per module.** Write a one-line import test against the new path:
   `from scoutmb.inference.numbering import requirement_path` → **RED** (`ImportError`).
3. Move → **GREEN**.
4. Re-point that module's characterization tests; delete the temporary import test.

The RED step catches the specific failure where a characterization test silently keeps
importing the old module and passes while proving nothing.

Pure "characterize first" is only half-achievable here: much high-value logic is
currently *unreachable* from a test (`parse_args` takes no `argv`, `process_scout` takes
a `Browser`, `write_html_report` reads the wall clock). **Phase 1 pins everything already
pinnable; every later phase pins what its own new seam exposes, before relying on it.**

### The known gap

| Reachable in Phase 1 | Needs a seam first |
| --- | --- |
| inference (`:610-843`), both call sites | `process_scout` |
| pure PDF helpers (`:172-200`, `:286-294`) | `navigate_and_trigger_schedule` |
| `clean_html_description`, `safe_slug`, `truthy` | `post_requirement` |
| exact CSV header rows; email goldens | |

The unreachable set is exactly the Playwright fusion, and introducing the seam is the
change that makes it testable. Mitigation: **mechanical move, zero logic edits**, one
manual end-to-end run against real data, then immediate `FakeSchedulePort` coverage.
Accepted knowingly rather than papered over.

### Fixture corpus

`raw_data/` (local, gitignored) holds three real runs, each with 22 scouts, 98 classes,
**4,858 requirements**, 120 raw payloads, plus one source PDF.

**The three runs are identical in completion state** — measured, not assumed: across
4,858 shared rows, `2026-07-18_1835` → `2026-07-18_1938` → `2026-07-19_2139` show
**zero** flag changes. The event (2026-07-06) had concluded.

1. **One run is the fixture corpus.** Byte-identical output across three independent runs
   is worth one determinism golden test; otherwise the other two add nothing.
2. **State transitions must be synthesized** by mutating completion flags over the real
   row structure, since the corpus contains none.

### Fixture safety

Real data appears in **every** artifact, not only `raw/`: `classes.csv` carries
`scout_name` and an 8-digit `attendee_id` per row; `report.html` contains 4,978
attendee-ID references. One relief — zero `scoutingevent.com/mobile` URLs appear in
generated reports, so QR bearer tokens do not propagate downstream.

- `tools/scrub_fixtures.py` covers **all** artifacts and **filenames** (`raw/` files are
  named from scout-name slugs — a leak vector distinct from contents).
- **It verifies itself**: after substitution it scans output for every original name,
  attendee ID, and QR token and fails if any survives, including surname-level partial
  matches.
- **It is security-critical and gets full TDD treatment**, with deliberately leaky
  inputs: a name in a filename, an ID in an HTML attribute, a name only in an email body,
  and a name that is a substring of another name.
- **Session-scoped conftest tripwire**: fail if any file under `tests/fixtures/` contains
  a `scoutingevent.com/mobile/` URL whose token doesn't start with `TESTTOKEN`.
- **Pre-commit hook** rejecting `*.pdf` at the repo root.

### Committed fixtures must be small

The real `report.html` is **3,092,771 bytes**. Multi-megabyte goldens make every diff
unreviewable. Therefore: goldens use a **reduced 2–3 scout corpus**; HTML is asserted
**structurally** by parsing the injected `<script type="application/json">` payload,
never by byte-comparing the document; CSV and JSON are compared in full.

### Fixture PDFs are generated, not committed

Commit the *builder*, not a binary blob. PyMuPDF `insert_image` builds the page with the
label/value layout `value_after_label` (`:176-186`) expects. For honest coverage of the
*rendered* fallback path (`:365-380`), a second variant draws the QR as vector content so
`decode_embedded_qr` returns empty and the fallback actually runs. QR generation uses
`cv2.QRCodeEncoder` (OpenCV is already a runtime dependency) with `segno` as a test-only
fallback if the encoder proves unavailable in the pinned build.

### Playwright, three tiers

1. **`FakeSchedulePort`** covers runner, retry, dedup, and mapping — always runs, no
   browser.
2. **`SimpleNamespace`** suffices for `is_schedule_response` and `form_values`, which
   only read attributes.
3. **`@pytest.mark.playwright`** against a local fake ScoutingEvent — deselected by
   default, **not in CI**. The only way to catch a stale selector in the `:384-397`
   fallback chain.

**Do not mock `Page`/`Response` with `unittest.mock`.** The surface used is deep enough
that the mock becomes the thing under test.

### Protocol conformance

A single contract suite is parametrized over **every** `SchedulePort` implementation,
with the live one marked and excluded by default. `FakeSchedulePort` is only useful if
genuinely substitutable; this is Liskov enforced mechanically rather than assumed.

### Required coverage

| Area | Requirement |
| --- | --- |
| `requirement_path` | All 18 observed shapes as a `parametrize` table |
| Completion flags | All 5 observed `(REQ, CLASS)` combinations, including 309 `(None, None)` |
| Empty rows | The 402 rows with empty number *and* description |
| Label rows | The 375 `Note.`-style rows |
| Choice requirements | Every corpus wording, plus synthesized threshold crossings |
| Inference call sites | `:783` and `:980` pinned **separately**, before unification |
| Schema drift | Renamed / missing / added / wrong-typed field — each reports without crashing |
| Dedup | The "prefer the completed duplicate" rule (`:502-506`), fixture written first |
| Retry | Exactly 3 attempts at 500/1000/1500 ms, asserted |
| CSV headers | Exact header rows, guarding `__dataclass_fields__` ordering (`:1666`, `:1671`) |
| Loaders | All four formats plus every header alias |
| Template | No `__REPORT_` token survives; a scout named `__REPORT_JS__` |
| Data paths | Pre-existing `data/scouts.csv` survives a full reinstall |
| Scrubber | Leaky-input suite |

### Coverage gates

**75% global**, with the weight in per-package floors:

| Package | Floor |
| --- | --- |
| `inference/`, `scrape/payloads.py` | 95% |
| `inputs/`, `emails/`, `storage/`, `cli/` | 90% |
| `pdf/` | 80% |
| `ui/` | 70% |
| `bootstrap/` | 60% |
| `scrape/playwright_port.py` | **omitted entirely** |

`playwright_port.py` is an I/O adapter covered only by tier 3; counting it incentivizes
fake tests. Chasing 90% global means mocking Playwright and PyInstaller — negative value.

### Do not test

`bootstrap/downloader.py` network fetches, `bootstrap/ui.py` (tkinter),
`install_webview2` (runs an .exe), `install_chromium_fallback` (20-minute download),
`desktop.py`'s webview launch, `build.spec`, `os.startfile`, the report's client-side JS,
and the CSS.

### Enforced rules

- **`pytest-socket` blocks all network** in the default suite.
- `markers = ["playwright"]`, `addopts = "-m 'not playwright'"`.

### Edge cases observed in real data

| Real input | Parses to | Assessment |
| --- | --- | --- |
| `#3b`, `#3(b)`, `6.a.1.` | `('3','b')`, `('6','a','1')` | correct |
| `#(c)` | `('7','c')` | correct — documented malformed case |
| `#2.Option.A.(1)` | `('2','option','a','1')` | correct; word becomes a token |
| `#5..Opt.A.(1)` | `('5','opt','a','1')` | correct — punctuation ignored by construction |
| `Note.` (375 rows) | `('7','note')` | **suspect** |
| `''` (402 rows) | `()` | **suspect** — empty number *and* description |

Two open questions, settled by direct tests of tree construction once inference is
decomposed:

1. **Label rows graft onto the preceding requirement.** `Note.` has no top-level number,
   so the last-seen one is prepended, making a note a *child* of requirement 7. If
   requirement 7 is a "Do TWO of the following" choice, the note enters the
   satisfied-child arithmetic. **Hypothesis, not a confirmed defect.**
2. **402 fully empty rows** collapse to path `()` and flow through the pipeline.

Resolved, recorded to prevent re-investigation: `choice_requirement_count` was suspected
of matching only "Do TWO". It does not — `:654` handles
`do|complete|choose|select|perform`. Measured against every unique corpus description:
**22 matched, 0 missed.** No defect.

Also recorded: `#2.Option.A.(1)` and `#5..Opt.A.(1)` tokenize to `'option'` and `'opt'`,
so logically-related rows can fail strict prefix matching. This is almost certainly *why*
the header-stack fallback exists — previously folklore, now documented.

---

## Python conventions

- **Ruff** for lint and format, with explicit rule selection. Run `ruff format` as a
  **separate formatting-only commit** so it never mixes with logic in a diff.
- **mypy strict** on `domain`, `inference`, `storage`, `inputs`; lenient elsewhere;
  `ignore_missing_imports` for `fitz`, `cv2`, `webview`.
- **`logging` replaces all 19 `print()` calls.** Library modules take module loggers and
  never configure handlers; CLI and launcher configure them. The three silent
  `except Exception:` sites become `logger.exception(...)`.
- **`ScoutmbError` hierarchy** replaces raw `RuntimeError` (five in `bootstrap/`),
  carrying structured context rather than pre-formatted strings.
- **Lazy heavyweight imports** — `openpyxl` moves inside `load_xlsx`.
- **Shared loader helpers** — `norm_header` / `first_matching_key` become one path so a
  new alias is added in one place.
- Protocols over ABCs, frozen slotted dataclasses, `pathlib`, `importlib.resources`.

## Continuous integration

| Job | Runs on | Contents |
| --- | --- | --- |
| `lint` | ubuntu | ruff check, ruff format --check |
| `types` | ubuntu | mypy |
| `test` | ubuntu, **windows** | pytest with `pytest-socket`, global + per-package gates |
| `lock` | ubuntu | `uv.lock` matches `pyproject.toml`; `requirements.txt` matches the lock |
| `build` | ubuntu | build wheel; verify packaged templates and static assets are present |
| `wheel-install` | windows | install the built wheel into a standalone runtime, import `scoutmb` |
| `launcher` | windows (+ macos from Phase 9) | PyInstaller build smoke test |
| `installer` | windows, `workflow_dispatch` | real bootstrap with `SCOUTMB_FORCE_CHROMIUM_FALLBACK=1` (~10 min) |

Playwright browsers are **not** installed in the default job — `@pytest.mark.playwright`
is excluded, so nothing needs a browser.

## Design decisions

| Decision | Rationale |
| --- | --- |
| Keep `errors.py` hierarchy | Designed upfront by explicit choice |
| Keep `ProgressSink` with multiple implementations | Required by planned future work |
| Keep self-update | Accepted complexity; mitigated by rollback and browser revalidation |
| Wire-boundary `Mapping[str, Any]`, not `TypedDict` | The upstream API is not ours; typing it encodes an unenforceable assumption and turns renames into silent `None`s |
| No Jinja2 | One substitution point; brace-escaping 206 CSS + 278 JS lines is a corruption risk, evidenced by `:886-893` |
| Wheel install, not `pip install -e .` | A **pre-built** wheel needs no build backend on the user's machine; verified by the `wheel-install` CI job |
| `requirements.txt` retained, generated and pinned | Still the installer's pip input and gates `compute_requirements_hash` |
| Technical layout (`reporting/`, `cli/`, `ui/`) | Deliberate deviation from CUPID's domain-based principle, appropriate at this size |

## Phases

Each phase leaves the app runnable and the suite green.

| # | Work | Exit criterion |
| --- | --- | --- |
| **0** | Tooling only, no source changes: pyproject, uv.lock, ruff, mypy, pytest, pre-commit, CI. Separate `ruff format` commit. Note the in-flight refactor in `CLAUDE.md` | Green CI on untouched source |
| **1** | Characterize in place against **flat** modules: inference (both call sites separately), pure PDF helpers, CSV headers, email goldens. Build `tests/factories/`. Scrubber via TDD; reduced fixtures | Safety net green; **zero app code moved** |
| **2** | Package skeleton + root shims. Mechanical move, zero edits beyond imports. Order: `domain` → `storage` → `inference` → `inputs` → `scrape` → `reporting` → `emails` → `pdf` → `cli` → `ui`. Delete and rebuild the code-review-graph | Phase 1 tests pass at new import paths |
| **3** | Extract the template. Golden test written **first** against the inline string, then extract byte-identically. Un-double email braces | Golden report byte-identical; `__REPORT_JS__` test passes |
| **4** | Typed config + `RunContext`. *Highest risk of a silently flipped default* | Test asserting `config_from_args(parse([minimal argv]))` equals a hand-written `ScrapeConfig` field by field, including the `scout_delay_ms=None` sentinel and the `no_html` inversion |
| **5** | Split `process_scout` at `SchedulePort`. `payloads.py` first with drift handling, pinned by a dedup fixture written beforehand | Contract suite green on all ports; retry asserted at 500/1000/1500 ms |
| **6** | Logging + unified `ProgressSink`. *Low behavior risk, high user-visible-output risk* | Terminal format signed off; `[i/n] name` line kept verbatim |
| **7** | UI app factory, `JobRegistry`, routers. **Hazards 1 and 2 land here**, plus the four bugs below | Regression test: pre-existing `data/scouts.csv` survives a full reinstall |
| **8** | Bootstrap rebuild: `manifest.py`, platforms, standalone runtime, venv, wheel install, self-update, rollback, browser revalidation | Windows launcher end to end, including a forced-rollback test |
| **9** | macOS: `macos.py`, CI matrix on both runners, notarization | A macOS launcher that runs |
| **10** | Cleanup: dead code, delete shims, raise gates, rewrite `CLAUDE.md` / `README.md` / `AGENTS.md` / `GEMINI.md` (all four document the flat layout), final graph rebuild | Docs match reality |

Phases 0–1 and 8 are independently reviewable; phases 2–7 must land in order. Phases 0–7
(application) and 8–9 (launcher) are separable efforts; **phase 7 is a clean stopping
point.**

**Four UI bugs fixed and listed in the Phase 7 PR:** `stale.unlink()` needs an
`is_file()` guard (`:114-116`, currently `IsADirectoryError` on a subdirectory);
`os.startfile` (`:334`) is Windows-only and `AttributeError`s elsewhere;
`webbrowser.open` server-side (`:301`) should return the URL for the client to open
(*behavior change* — equivalent under pywebview, strictly more correct under
`--browser`); unguarded `json.loads` at `:205`, `:296`, `:311`.

## Verification

- `ruff check . && ruff format --check . && mypy src && pytest --cov` green at every phase.
- **One end-to-end run against real data before merging Phase 2.** Removing `write_csv`'s
  `extrasaction="ignore"` (`:601`) is correct but converts a currently-silent field
  mismatch into a crash — the one place a fix surfaces a latent bug loudly.
- Legacy invocations still work via shims; `troop349 extract-pdf` / `troop349 download`
  produce **byte-identical CSV headers**.
- `troop349 ui`, then exercise upload → extract → download → open report → generate emails.
- Diff generated `report.html` against a pre-refactor capture with a frozen clock.
- Installer on macOS: `SCOUTMB_BOOTSTRAP_ROOT=<tmp> python -m bootstrap.main`; assert the
  package is importable *and* a pre-existing `data/scouts.csv` survives.
- **Tag the pre-refactor commit** so it can be bisected from a Windows machine.

## Risks

| Risk | Mitigation |
| --- | --- |
| **Hazards 1 + 2 destroy user data** | Explicit `data_root`; both fixed in Phase 7 with a survival regression test |
| Playwright extraction has no prior characterization test | Mechanical move only; manual end-to-end run; `FakeSchedulePort` coverage immediately after |
| **Stale `.code-review-graph/graph.db`** — `CLAUDE.md` instructs agents to trust it *before* reading files. After Phase 2 every node is stale, so an agent answers confidently about a codebase that no longer exists — worse than no graph | Delete at the start of Phase 2, rebuild after **every** phase; note the in-flight refactor in `CLAUDE.md` during Phase 0. Check `.gemini/`, `.remember/`, `.kiro/`, `.qoder/` for the same staleness |
| Double inference invocation with divergent shapes | Both call sites pinned separately in Phase 1, before unification |
| CSV column order derives from dataclass field order | Exact header rows pinned in Phase 1 |
| Template reassembly shifts bytes | Golden test written before extraction is the whole defense |
| Scrubber leaks real data | Self-verifying over all artifacts and filenames; own TDD suite; conftest tripwire; `/raw_data/` gitignored |
| Upstream API changes shape | Anti-corruption layer with drift reporting; property-based tests assert no crash on arbitrary payloads |
| Bad wheel bricks installations | Retained previous wheel; automatic rollback after two consecutive launch failures |
| Playwright/browser version skew after update | Mandatory revalidation when the resolved version changes |
| Windows installer untestable on macOS | Three-tier verification above; `workflow_dispatch` real-bootstrap job; tagged pre-refactor commit |
| 3.14 dev vs 3.12 shipped | `requires-python`, ruff `target-version`, mypy `--python-version`, 3.12 primary in CI; pinned `requirements.txt`; consider recreating `.venv` on 3.12 |
| Root shims become permanent | `DeprecationWarning` naming `troop349`; deleted in Phase 10 |
| Adult filtering runs twice (`pdf:23`, `cli:212`) | Unify the constant, **keep both call sites** — inputs skipping the PDF stage still need the second |
| macOS Gatekeeper blocks unsigned launcher | Apple Developer Program is a purchasing decision tracked outside this plan |
| tkinter under PyInstaller on macOS | Phase 9 detour if it manifests; not a blocker |
| Scope creep from discovered bugs | Characterization tests pin bugs; fixes are separate changes with their own failing tests |

## Open questions

None blocking. The two suspect `requirement_path` behaviors are settled by direct tests
of tree construction in Phase 2 rather than by advance decision, and any resulting fix is
scheduled separately per the risk table.
