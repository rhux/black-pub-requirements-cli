# scoutmb: Restructure Design

**Date:** 2026-07-21
**Status:** Approved design, pending implementation plan

## Problem

The repository began as two standalone scripts and has grown into five subsystems
without a corresponding change in structure:

| Component | Size | Role |
| --- | --- | --- |
| `scout_schedule_cli.py` | 1,798 lines | Stage 2: scrape, infer, report |
| `pdf_to_scouts.py` | 580 lines | Stage 1: PDF to CSV |
| `ui/` | 340 lines Python + 329 JS | Local FastAPI app |
| `bootstrap/` | 13 modules | Windows self-installing launcher |
| `run_app.py` | 90 lines | Native-window entry point |

There is no package, no `pyproject.toml`, no tests, no linter, and no CI. The
concrete defects this causes:

1. **`scout_schedule_cli.py` has no internal boundaries.** One module holds argument
   parsing, four input-format loaders, Playwright browser control, AJAX scraping,
   requirement-status inference, email rendering, a 658-line embedded HTML template,
   and six output writers.
2. **The web UI impersonates argparse.** `ui/server.py:188` hand-constructs an
   `argparse.Namespace` to call `async_main`. The reusable seam is in the wrong place.
3. **Two `sys.path` hacks.** `ui/server.py:25` inserts the repo root; `python_env.py:62`
   patches the app directory into the embeddable Python's `._pth`. Both exist because
   the app is loose files rather than an installed package.
4. **Heavyweight imports block testing.** `scout_schedule_cli.py:27` imports `openpyxl`
   at module scope, so importing even a pure function such as `requirement_path`
   requires every dependency to be installed.
5. **Playwright is fused into orchestration.** `process_scout` (141 lines) interleaves
   browser calls with business logic, which is the direct reason this code has no tests.
6. **Unreferenced background tasks.** `ui/server.py:162` and `:223` call
   `asyncio.create_task(worker())` without retaining the result. CPython holds only weak
   references to tasks, so a long-running job can be garbage collected mid-execution.
7. **No logging.** 19 `print()` calls and nine `except Exception` sites, three of which
   (`scout_schedule_cli.py:363,400,468`) swallow silently with no record.
8. **User data commingled with replaceable source.** `scouts.csv`, `pdf-uploads/`, and
   `runs/` live in the same app directory the launcher overwrites on each start.

## Goals

- A conventional, installable Python package with tests, linting, typing, and CI.
- Testable seams — in particular, business logic exercisable without a browser.
- A launcher that is portable to macOS and can update itself.
- Preserve current behavior through the restructure; treat behavior changes as
  separate, deliberate, individually tested decisions.

## Non-goals

- Rewriting the requirement-inference algorithm. It is characterized and preserved.
- Shipping a signed macOS build. Phase 5 produces a working launcher; notarization is
  a purchasing decision (Apple Developer Program, USD 99/yr), tracked separately.
- Replacing the frontend with a framework. `ui/static/` stays vanilla.

## Constraints

- **Runtime target is Python 3.12.** `requires-python = ">=3.12"`, CI runs 3.12, even
  though the development machine runs 3.14.
- **No real Scout data in the repository, ever.** QR URLs and attendee IDs are bearer
  tokens for real minors' records. `/raw_data/` is gitignored (`.gitignore:13`) and
  fixtures are only committed after automated verification (see Testing).
- **The launcher's audience is non-technical.** Double-click to run; never touch or
  require a system Python. This constraint is preserved, not relaxed.
- **The app is not currently deployed to users.** This removes the need for data
  migration code and permits breaking changes to the app-local layout.

## Architecture

### Package layout

```
pyproject.toml                 # PEP 621 metadata; single source of dependency truth
src/scoutmb/
  config.py                    # frozen dataclasses; replaces argparse.Namespace passing
  models.py                    # ScoutInput, ClassRecord, RequirementRecord, ScoutResult
  progress.py                  # ProgressReporter protocol + null/console/queue impls
  errors.py                    # ScoutmbError hierarchy
  pdf/
    identity.py                # attendee name / registrant type from page text
    qr.py                      # embedded + rendered decode tiers, candidate selection
    extract.py                 # per-PDF orchestration
    discovery.py               # expand_pdf_inputs (files, dirs, globs)
  schedule/
    inputs.py                  # 4 loaders + header aliasing; openpyxl imported lazily
    session.py                 # ALL Playwright contact, behind ScheduleSession
    scrape.py                  # process_scout, browser-free
    requirements.py            # requirement_path, choice_requirement_count, inference
  reports/
    csv.py  json.py  email.py
    html.py
    assets/report.html         # was a 658-line f-string
  cli/
    pdf_to_scouts.py           # argv -> config -> core
    scout_schedule.py
  webapp/
    server.py  jobs.py  routes/  static/
tests/{unit,integration,fixtures}/
tools/scrub_fixtures.py
bootstrap/                     # stays top-level; see below
```

`bootstrap/` deliberately remains outside `src/scoutmb/`. It runs *before* the
application's dependencies exist and may import only the standard library. Folding it
into the app package would blur a constraint that is currently load-bearing.

### Seams

**Configuration objects.** A frozen `ScrapeConfig` becomes the real interface between
callers and the core:

```python
@dataclass(frozen=True, slots=True)
class ScrapeConfig:
    input_path: Path
    output_dir: Path
    sheet_name: str = "Scouts Only"
    include_adults: bool = False
    browser: BrowserOptions = field(default_factory=BrowserOptions)
    pacing: PacingOptions = field(default_factory=PacingOptions)
    html_report: str | None = "report.html"   # None disables
```

`parse_args` builds one; `webapp` builds one directly. The `no_html` / `html_name` pair
collapses into `html_report: str | None`, removing a negative boolean flag.

**`ScheduleSession` protocol.** The highest-value change in the refactor:

```python
class ScheduleSession(Protocol):
    async def discover_name(self, fallback: str) -> str: ...
    async def fetch_schedule(self, qr_url: str) -> dict[str, Any]: ...
    async def fetch_requirements(self, attendee_id: str, class_p4_id: str) -> dict[str, Any]: ...
```

`PlaywrightSession` is the production implementation. `RecordedSession` replays captured
payloads. `process_scout` becomes pure orchestration over the protocol.

The fixture format already exists: `write_outputs` dumps untouched payloads to `raw/`
for auditing, and those files are exactly what `RecordedSession` replays.

**`ProgressReporter` protocol.** Today two different callback shapes exist — a
positional `(index, total, path)` for stage 1 and an async `dict` event for stage 2.
These unify into one protocol emitting typed events, with `NullReporter`,
`ConsoleReporter`, and `QueueReporter` (SSE) implementations.

**`JobRegistry`.** The module globals `operations`, `busy`, and `current_download`
(`ui/server.py:45-47`) become one object on `app.state`, injected as a FastAPI
dependency. The registry retains task references, fixing defect 6.

**Packaged assets.** `reports/assets/report.html` carries a `__REPORT_DATA__`
placeholder inside a `<script type="application/json">` block, loaded via
`importlib.resources.files()` — not `Path(__file__).parent`, which breaks in a wheel.
Same treatment for `webapp/static/`.

### Deployment

`app/` is eliminated. The application is an installed wheel, so `source_sync.py` and its
allowlist are deleted outright.

```
<app root>/           # %LOCALAPPDATA%\ScoutingMeritBadges          (Windows)
                      # ~/Library/Application Support/ScoutingMeritBadges  (macOS)
  runtime/            # python-build-standalone — disposable
  venv/               # created from runtime/, holds the wheel + deps — disposable
  data/               # scouts.csv, pdf-uploads/, runs/ — never touched by provisioning
  state/              # marker, browser channel, wheel cache, update throttle
  logs/
```

Separating `runtime/` from `venv/` means a dependency change rebuilds only the venv,
while a Python version bump re-downloads the runtime. Because standalone Python plus a
normal venv is an ordinary Python environment, the `._pth` patching in
`python_env.py:47-69` disappears entirely.

**Platform dispatch** replaces scattered `sys.platform` checks:

```
bootstrap/platforms/
  base.py       # Protocol: app_root, python_exe, gui_python_exe,
                #           ensure_webview, preferred_browser_channel, runtime_url
  windows.py    # LOCALAPPDATA, WebView2, Edge, pythonw.exe, winreg
  macos.py      # ~/Library/Application Support, WKWebView (no-op), Chrome
```

`webview2.py` imports `winreg` at module scope, so the factory must lazily import the
platform module rather than importing both and branching.

**Self-update.** The launcher queries GitHub Releases for a newer wheel version, at most
**once per 24 hours** (timestamp recorded in `state/`) and bounded by a **3 second**
connect-and-read timeout. Any failure — no network, timeout, malformed response — is
logged and the installed version launches anyway.
**Startup never blocks on an update check**; the deployment environment is a Scout camp
with unreliable connectivity.

`requirements.txt` ceases to be an installer input, since the wheel declares its own
dependencies. `marker.py`'s `requirements_hash` becomes `wheel_version` + `wheel_hash`.

`PLAYWRIGHT_BROWSERS_PATH` is set under `state/` so browser downloads land in the app
root rather than the user's global cache, making uninstall a single directory removal.

## Testing

### TDD discipline

The Iron Law — no production code without a failing test — applies differently to the
three kinds of work in this plan. All three are in scope; none is exempt.

**New code: strict red-green-refactor.** `ScheduleSession`, `RecordedSession`,
`JobRegistry`, `ProgressReporter`, `errors.py`, all platform dispatch, self-update, and
the scrubber. Test first, observe the failure, write minimal code to pass.

**Deliberate behavior changes: strict red-green-refactor.** The `html_report: str | None`
collapse and the redesigned CLI surface are new behavior and get failing tests first.

**Code motion: characterization-first.** Moving existing code must not change behavior,
so red-green-refactor does not apply. Instead, pin current behavior, then move. A
genuine RED step still exists and is mandatory: **write the characterization test
against the new import path first.**

```python
from scoutmb.schedule.requirements import annotate_requirement_statuses  # ImportError → RED
```

Move the code → GREEN. This is not ceremony; it catches the specific failure mode where
a test silently continues importing the old module and passes while proving nothing.

**Characterization tests pin current behavior, including bugs.** Where a test documents
behavior we believe is wrong, it is committed as-is with a comment, and the fix becomes
a separate change with its own failing test. Refactoring and bug-fixing never share a
commit.

### The known gap

Phase 0 requires characterization tests against current code, but some current code
cannot be invoked without a browser. Auditing what is reachable today:

| Reachable now (pure or file-level) | Not reachable without the seam |
| --- | --- |
| `requirement_path`, `choice_requirement_count` | `process_scout` |
| `annotate_requirement_statuses` (dicts in, dicts out) | `navigate_and_trigger_schedule` |
| `build_missing_requirements`, email renderers | `post_requirement` |
| the four loaders; `write_html_report`, `write_outputs` via golden files | |

The reachable set includes all the inference logic, which is the highest-risk code.
The unreachable set is exactly the Playwright fusion — and introducing the seam is the
change that makes it testable, so no prior characterization test is possible.

Mitigation for that one extraction: a **purely mechanical move with zero logic edits**,
verified by one manual end-to-end run against real data, then immediately covered by
`RecordedSession` tests. This gap is accepted knowingly rather than papered over.

### Fixture corpus

`raw_data/` (local, gitignored) holds three real runs, each containing 22 scouts, 98
classes, **4,858 requirements**, and 120 raw payloads, plus one source PDF.

**The three runs are identical in completion state.** This was measured, not assumed:
across 4,858 shared rows, `2026-07-18_1835` → `2026-07-18_1938` → `2026-07-19_2139`
show **zero** `COMPLETED_REQ_FLAG` or `COMPLETED_CLASS_FLAG` changes. The event
(2026-07-06) had already concluded, so nothing was still moving.

Two consequences:

1. **One run is the fixture corpus.** The other two add no completion-state coverage.
   They do serve one purpose: byte-identical output across three independent runs is
   evidence the scraper is deterministic, which is worth one golden test.
2. **State-transition coverage must be synthesized.** Since the corpus contains no real
   transitions, tests that exercise inference branching (partial completion, choice
   requirements crossing their threshold, parents flipping as children complete) are
   built by mutating completion flags over the real row structure. This keeps realistic
   requirement trees while producing the state variety the corpus lacks.

Payload shape:

```
{"status": {"status": int, "stack": [...]},
 "data": [{"MDM_LKP_BADGE_REQ_ID", "MERIT_BADGE_NAME", "REQ_NBR",
           "REQ_NBR_WEB_DISPLAY", "REQ_DESCR", "COMPLETED_REQ_FLAG",
           "COMPLETED_CLASS_FLAG", "REQ_ON_EVENT", "PRESENT_DAYS", ...}]}
```

### Edge cases observed in real data

`requirement_path` faces far more variety than the two documented shapes. Measured
across the corpus (18+ distinct shapes), with parse results verified against the current
implementation:

| Real input | Parses to | Assessment |
| --- | --- | --- |
| `#3b`, `#3(b)`, `6.a.1.` | `('3','b')`, `('6','a','1')` | correct |
| `#(c)` | `('7','c')` | correct — documented malformed case |
| `#2.Option.A.(1)` | `('2','option','a','1')` | correct; word becomes a token |
| `#5..Opt.A.(1)` | `('5','opt','a','1')` | correct — punctuation is ignored by construction |
| `Note.` (375 rows) | `('7','note')` | **suspect** — see below |
| `''` (402 rows) | `()` | **suspect** — empty number *and* empty description |

Two open questions to be settled by phase 0's characterization tests:

1. **Label rows are grafted onto the preceding requirement.** `Note.` has no top-level
   number, so `requirement_path` prepends the last-seen one, making a note a *child* of
   requirement 7. If requirement 7 is a "Do TWO of the following" choice, the note
   enters the satisfied-child arithmetic. Whether this changes a reported completion
   status depends on `calculate`, which has not yet been traced. **Hypothesis, not a
   confirmed defect.**
2. **402 fully empty rows** collapse to path `()` and are carried through the pipeline.

One resolved question, recorded to prevent re-investigation: `choice_requirement_count`
was suspected of matching only "Do TWO" and missing "choose/select/complete" variants.
It does not — `scout_schedule_cli.py:654` already handles
`do|complete|choose|select|perform`. Measured against every unique description in the
corpus: **22 matched, 0 missed.** No defect.

Also worth recording: `#2.Option.A.(1)` and `#5..Opt.A.(1)` tokenize to `'option'` and
`'opt'` respectively, so logically-related rows can fail strict prefix matching. This is
almost certainly *why* the header-stack fallback exists — previously folklore, now
documented.

### Test layers

1. **Pure unit** — `requirements.py`, `inputs.py`, QR candidate selection, formatters.
   The bulk of the suite. The shape table above becomes a `parametrize` table.
2. **Golden / characterization** — sanitized payloads through the full pipeline, against
   committed expected CSV/JSON/HTML.
3. **Integration with fakes** — `process_scout` against `RecordedSession`; routes under
   `TestClient`.
4. **PDF** — synthetic PDFs built at test time. PyMuPDF draws pages and
   `cv2.QRCodeEncoder` generates codes, so **no new dependency** — OpenCV is already
   present for decoding. Layout is derived from the real PDF, which is never committed.
5. **Property-based** (optional, `hypothesis`) — `requirement_path` should never raise
   on arbitrary strings.

### Enforced rules

- **`pytest-socket` blocks all network access in the suite.** Otherwise "no live tests"
  is aspirational and erodes.
- **The scrubber verifies itself.** After substitution, `tools/scrub_fixtures.py` scans
  its output for every original name, attendee ID, and QR token and fails if any
  survives. This includes **filenames** — `raw/` files are named from scout-name slugs,
  which is a leak vector distinct from file contents. An unverified scrubber is a data
  leak with extra steps.
- **Coverage:** hard gates of **95% line coverage on `schedule/requirements.py` and
  `schedule/inputs.py`**, enforced per-module in CI; **no global percentage target.** A
  global gate on a codebase containing a browser driver produces tests written to move a
  number.

## Python conventions

- **Ruff** for lint and format, replacing black, isort, flake8, and pyupgrade, with an
  explicit rule selection rather than defaults.
- **mypy strict** on `src/`, lenient on `tests/`.
- **`logging` replaces all 19 `print()` calls.** Library modules take module-level
  loggers and never configure handlers; the CLI and launcher configure them. The three
  silent `except Exception:` sites become `logger.exception(...)`.
- **`ScoutmbError` hierarchy** replaces the raw `RuntimeError`s (five in `bootstrap/`),
  carrying structured context rather than pre-formatted strings.
- **`[project.scripts]`** for console entry points.
- **pytest** with fixtures and `parametrize`; no `unittest.TestCase`.
- **Lazy heavyweight imports** — `openpyxl` moves inside `load_xlsx` so pure logic is
  importable without it (defect 4).
- Protocols over ABCs, frozen slotted dataclasses, `pathlib`, `importlib.resources`.
  The existing code already uses `@dataclass(frozen=True, slots=True)` and `pathlib`
  correctly; this continues established practice rather than imposing something new.

## Phases

| Phase | Work | Exit criterion |
| --- | --- | --- |
| **0** | pyproject, ruff, mypy, pytest, CI on 3.12; scrubber; fixtures; characterization tests against **current** flat code | Green CI; safety net in place; **zero code moved** |
| **1** | Extract `src/scoutmb/`: models, config, progress, errors, requirements, inputs, reports. Flat scripts become shims | Phase 0's characterization tests pass **unchanged** |
| **2** | `ScheduleSession`; `PlaywrightSession` + `RecordedSession`; `process_scout` becomes pure; HTML to asset | `process_scout` tested with no browser |
| **3** | `cli/` console scripts, flat scripts deleted; `webapp/` with `JobRegistry` + routers; both `sys.path` hacks gone | Routes tested under `TestClient` |
| **4** | Bootstrap rebuild: platforms, standalone runtime, venv, wheel install, `data/` split, self-update | Windows launcher verified end to end |
| **5** | macOS: `macos.py`, CI matrix on both runners, notarization | A macOS launcher that runs |

Phase 1's exit criterion is load-bearing. Characterization tests written against the old
flat modules, still passing after the code moves, is the actual proof that behavior did
not change — not code review, not confidence.

## Risks

| Risk | Mitigation |
| --- | --- |
| Playwright extraction has no prior characterization test | Mechanical move only; manual end-to-end verification; `RecordedSession` coverage immediately after |
| Scrubber leaks real data into a commit | Self-verifying scrubber covering contents *and* filenames; `/raw_data/` gitignored; review fixture diffs before commit |
| `python-build-standalone` behaves unlike the embeddable distribution | Phase 4 is Windows-only and verified end to end before phase 5 adds a second platform |
| macOS Gatekeeper blocks unsigned launcher | Known cost; Apple Developer Program is a purchasing decision tracked outside this plan |
| tkinter under PyInstaller on macOS is historically fragile | Phase 5 detour if it manifests; not a blocker |
| Scope creep from discovered bugs | Characterization tests pin current behavior including bugs; fixes are separate changes with their own failing tests |

## Open questions

None blocking. The two suspect behaviors in `requirement_path` (label-row grafting,
empty rows) are resolved by phase 0's characterization tests rather than by advance
decision, and any resulting fix is scheduled separately per the risk table.
