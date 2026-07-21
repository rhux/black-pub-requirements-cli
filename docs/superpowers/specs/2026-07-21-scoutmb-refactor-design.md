# scoutmb: Restructure Design

**Date:** 2026-07-21
**Status:** Approved design, pending implementation plan
**Supersedes:** `docs/refactor-plan.md`

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
9. **Untyped, unvalidated external payloads.** Responses from `scoutingevent.com` flow
   through the pipeline as `dict[str, Any]`. A field rename upstream produces silently
   wrong completion status rather than a visible failure.
10. **Pervasive nondeterminism.** Timestamps, `random.uniform`, and `uuid4` are called
    directly from business logic, making output unreproducible and untestable.

## Goals

- A conventional, installable Python package with tests, linting, typing, and CI.
- Testable seams — in particular, business logic exercisable without a browser.
- Reproducible output, so behavior can be pinned by golden tests.
- Resilience to upstream schema drift, with drift made visible rather than silent.
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
- **The upstream API is not ours.** `scoutingevent.com` may change its payload shape
  without notice. The design must tolerate this rather than assume stability.

## Architecture

### Package layout

```
pyproject.toml                 # PEP 621 metadata; single source of dependency truth
uv.lock                        # locked resolution shipped with the wheel
src/scoutmb/
  config.py                    # frozen dataclasses; replaces argparse.Namespace passing
  models.py                    # ScoutInput, ClassRecord, RequirementRecord, ScoutResult
  runtime.py                   # Clock, IdFactory, RunContext — injected nondeterminism
  progress.py                  # ProgressReporter protocol + null/console/queue impls
  errors.py                    # ScoutmbError hierarchy
  pdf/
    identity.py                # attendee name / registrant type from page text
    qr.py                      # embedded + rendered decode tiers, candidate selection
    extract.py                 # per-PDF orchestration
    discovery.py               # expand_pdf_inputs (files, dirs, globs)
  schedule/
    inputs.py                  # loaders + shared header aliasing; openpyxl imported lazily
    payloads.py                # anti-corruption layer: wire dicts -> owned models
    session.py                 # ALL Playwright contact, behind ScheduleSession
    scrape.py                  # process_scout, browser-free
    tree.py                    # requirement_path, build_requirement_tree
    statuses.py                # choice_requirement_count, calculate_statuses
  reports/
    csv.py  json.py  email.py
    html.py
    assets/report.html         # was a 658-line f-string
  cli/
    pdf_to_scouts.py           # argv -> config -> core
    scout_schedule.py
  webapp/
    server.py  jobs.py  routes/  static/
tests/{unit,integration,contract,fixtures}/
tools/scrub_fixtures.py
bootstrap/                     # stays top-level; see below
```

`bootstrap/` deliberately remains outside `src/scoutmb/`. It runs *before* the
application's dependencies exist and may import only the standard library. Folding it
into the app package would blur a constraint that is currently load-bearing.

Note that `annotate_requirement_statuses` is **decomposed, not relocated** — see
"Requirement inference" below.

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

The return type is deliberately `dict[str, Any]` — this is the wire boundary, and
claiming more structure than the upstream API guarantees would be dishonest typing.
Structure is imposed one layer in, by `payloads.py`.

*Known interface-segregation tension:* `discover_name` is page-scraping while the other
two are data retrieval. Accepted as one interface for now because both implementations
need all three; revisit if a third implementation wants only part of it.

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

### Determinism

All nondeterminism moves behind injected collaborators, gathered in a `RunContext`:

```python
@dataclass(frozen=True, slots=True)
class RunContext:
    clock: Clock          # now() -> datetime; report timestamps
    ids: IdFactory        # new_id() -> str; operation and run IDs
    rng: random.Random    # seeded; inter-scout pacing jitter
```

This replaces five direct calls that currently make output unreproducible:

| Source | Location | Replaced by |
| --- | --- | --- |
| `time.strftime` → `generated_at_local` | `scout_schedule_cli.py:1644` | `ctx.clock` |
| `datetime.now()` → `generated_at_iso` | `:1645` | `ctx.clock` |
| `random.uniform(0.5, 2.0)` pacing | `:1765` | `ctx.rng` |
| `uuid4()` operation IDs | `ui/server.py:110,174` | `ctx.ids` |
| `time.strftime` run IDs | `ui/server.py:65` | `ctx.clock` |

Production wires real implementations; tests wire a frozen clock, a counting ID factory,
and a seeded RNG. Without this, golden comparison is impossible — every report embeds a
wall-clock timestamp.

### Requirement inference

`annotate_requirement_statuses` (105 lines, containing a nested recursive closure) is
**decomposed rather than moved**. Relocating it intact would preserve the exact fusion
that makes it untestable:

- `tree.py` — `requirement_path()`, `build_requirement_tree()`. Pure structure: given
  rows, produce a parent/child tree, including the header-stack fallback.
- `statuses.py` — `choice_requirement_count()`, `calculate_statuses()`. Pure evaluation:
  given a tree plus completion flags, derive `complete` / `complete_check` /
  `incomplete`.

Splitting these is what allows the `Note.` question (see Testing) to be settled by a
direct test of tree construction rather than by inspecting whole-report output.

### External payload handling

Because the upstream schema is not ours and may change without notice, `payloads.py` is
an anti-corruption layer, not a type declaration:

```python
def parse_requirement_rows(
    payload: dict[str, Any],
) -> tuple[list[RequirementRecord], list[SchemaDrift]]: ...
```

Rules:

- **Unknown fields are ignored.** New upstream fields never break a run.
- **Missing expected fields are recorded, not raised.** Each produces a `SchemaDrift`
  entry naming the field and the context.
- **Drift is surfaced**, in `errors.csv` and a `schema_drift` count in `summary.json`,
  so a silent upstream rename shows up as a visible warning instead of an entire
  merit badge quietly reading "incomplete".
- **Type coercion is explicit and total.** `truthy()`-style flag parsing tolerates
  `"1"`, `"0"`, `""`, and `None` — the corpus contains 309 rows with `(None, None)`
  flags — and never raises on unexpected values.

Downstream of this boundary, everything is an owned, strictly typed model. `dict[str,
Any]` appears only in `session.py` and `payloads.py`.

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

**Dependency locking.** `pyproject.toml` declares ranges; `uv.lock` pins an exact
resolution and ships alongside the wheel. Installation uses the lock, so two users
installing weeks apart get identical dependency versions. Without this, an upstream
breaking release silently breaks new installs while existing machines keep working —
the hardest class of bug to diagnose remotely.

**Self-update.** The launcher queries GitHub Releases for a newer wheel version, at most
**once per 24 hours** (timestamp recorded in `state/`) and bounded by a **3 second**
connect-and-read timeout. Any failure — no network, timeout, malformed response — is
logged and the installed version launches anyway. **Startup never blocks on an update
check**; the deployment environment is a Scout camp with unreliable connectivity.

Two safety requirements:

- **Playwright browser revalidation.** The `playwright` Python package is version-coupled
  to its browser binaries. After any update that changes the resolved `playwright`
  version, the launcher must re-run browser installation before launching. Skipping this
  produces an app that starts and then fails mid-scrape, offline, at camp.
- **Rollback.** The previously working wheel is retained in `state/`. If a freshly
  updated version fails to launch twice consecutively, the launcher reinstalls the
  retained wheel and logs the downgrade. An auto-updater without a rollback path can
  brick every installation simultaneously.

`requirements.txt` ceases to be an installer input, since the wheel plus lock file
declare dependencies. `marker.py`'s `requirements_hash` becomes `wheel_version` +
`wheel_hash`.

`PLAYWRIGHT_BROWSERS_PATH` is set under `state/` so browser downloads land in the app
root rather than the user's global cache, making uninstall a single directory removal.

## Testing

### TDD discipline

The Iron Law — no production code without a failing test — applies differently to the
three kinds of work in this plan. All three are in scope; none is exempt.

**New code: strict red-green-refactor.** `ScheduleSession`, `RecordedSession`,
`JobRegistry`, `ProgressReporter`, `RunContext`, `payloads.py`, `errors.py`, all platform
dispatch, self-update, rollback, and the scrubber. Test first, observe the failure, write
minimal code to pass.

**Deliberate behavior changes: strict red-green-refactor.** The `html_report: str | None`
collapse, the redesigned CLI surface, and schema-drift reporting are new behavior and get
failing tests first.

**Code motion: characterization-first.** Moving existing code must not change behavior,
so red-green-refactor does not apply. Pin current behavior, then move.

**Characterization tests pin current behavior, including bugs.** Where a test documents
behavior we believe is wrong, it is committed as-is with a comment, and the fix becomes
a separate change with its own failing test. Refactoring and bug-fixing never share a
commit.

### Phase 0 / phase 1 test sequencing

Phase 0 must end with a **green** build, and phase 1 must retain a genuine RED step.
These are reconciled by an explicit order, not left to improvisation:

1. **Phase 0.** Characterization tests import the **flat modules**
   (`import scout_schedule_cli`) and pass. This is the real safety net. CI is green.
2. **Phase 1, per module.** Write a one-line import test against the new path:
   `from scoutmb.schedule.tree import requirement_path` → **RED** (`ImportError`).
3. Move the code → **GREEN**.
4. Re-point that module's characterization tests to the new path; delete the temporary
   import test.

The RED step is not ceremony — it catches the specific failure where a characterization
test silently keeps importing the old module and passes while proving nothing.

### The known gap

Phase 0 requires characterization tests against current code, but some current code
cannot be invoked without a browser:

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
   built by mutating completion flags over the real row structure.

Payload shape as observed (not guaranteed — see External payload handling):

```
{"status": {"status": int, "stack": [...]},
 "data": [{"MDM_LKP_BADGE_REQ_ID", "MERIT_BADGE_NAME", "REQ_NBR",
           "REQ_NBR_WEB_DISPLAY", "REQ_DESCR", "COMPLETED_REQ_FLAG",
           "COMPLETED_CLASS_FLAG", "REQ_ON_EVENT", "PRESENT_DAYS", ...}]}
```

### Committed fixtures must be small

The real `report.html` for 22 scouts is **3,092,771 bytes**. Committing multi-megabyte
golden files makes every diff unreviewable and every failure undiagnosable. Therefore:

- Golden fixtures use a **reduced corpus of 2–3 scouts**, derived from the real run.
- HTML is asserted **structurally** — parse the injected `<script type="application/json">`
  payload and assert on that — never by byte-comparing the rendered document.
- CSV and JSON outputs, being small and line-oriented, are compared in full.

### Sanitization

Real data appears in **every** output artifact, not only `raw/`. Measured: `classes.csv`
carries a `scout_name` and an 8-digit `attendee_id` on every data row; `report.html`
contains 4,978 attendee-ID references. One piece of good news — zero
`scoutingevent.com/mobile` URLs appear in generated reports, so QR bearer tokens do not
propagate downstream.

`tools/scrub_fixtures.py` therefore:

- Covers **all** artifacts: `raw/`, `classes.csv`, `requirements.csv`, `errors.csv`,
  `scouts.json`, `summary.json`, `report.html`, and `emails/`.
- Covers **filenames**, not just contents — `raw/` files are named from scout-name slugs,
  a leak vector distinct from file contents.
- **Verifies itself.** After substitution it scans output for every original name,
  attendee ID, and QR token, and fails if any survives.
- **Is security-critical code and gets full TDD treatment**, including tests with
  deliberately leaky inputs: a name embedded in a filename, an ID inside an HTML
  attribute, a name appearing only in an email body, and a name that is a substring of
  another name.

An unverified scrubber is a data leak with extra steps.

### Required coverage

The spec mandates these specifically, rather than leaving adequacy to judgement:

| Area | Requirement |
| --- | --- |
| `requirement_path` | All 18 observed shapes as a `parametrize` table (below) |
| Completion flags | All 5 observed `(REQ, CLASS)` combinations, including 309 `(None, None)` rows |
| Empty rows | The 402 rows with empty number *and* description |
| Label rows | The 375 `Note.`-style rows |
| Choice requirements | Every wording variant in the corpus, plus synthesized threshold crossings |
| Schema drift | Renamed field, missing field, added field, wrong type — each reports drift without crashing |
| Loaders | All four formats plus every header alias |
| Protocol conformance | Shared contract suite (below) |
| Scrubber | Leaky-input suite (above) |

### Protocol conformance testing

`RecordedSession` is only useful if it is genuinely substitutable for
`PlaywrightSession`; otherwise every test using it proves nothing about production. A
single contract suite is therefore parametrized over both implementations, with the
live one marked `@pytest.mark.live` and excluded from default runs. This is Liskov
substitutability enforced mechanically rather than assumed.

### Test layers

1. **Pure unit** — `tree.py`, `statuses.py`, `payloads.py`, `inputs.py`, QR selection,
   formatters. The bulk of the suite.
2. **Contract** — protocol conformance, run against every implementation.
3. **Golden / characterization** — reduced sanitized corpus through the full pipeline.
4. **Integration with fakes** — `process_scout` against `RecordedSession`; routes under
   `TestClient`.
5. **PDF** — synthetic PDFs built at test time. PyMuPDF draws pages and
   `cv2.QRCodeEncoder` generates codes, so **no new dependency** — OpenCV is already
   present for decoding. Layout is derived from the real PDF, which is never committed.
6. **Property-based** (`hypothesis`) — `requirement_path` never raises on arbitrary
   strings; `payloads.parse_requirement_rows` never raises on arbitrary JSON.

### Enforced rules

- **`pytest-socket` blocks all network access** in the default suite. Otherwise "no live
  tests" is aspirational and erodes.
- **Coverage:** hard gates of **95% line coverage on `schedule/tree.py`,
  `schedule/statuses.py`, `schedule/payloads.py`, and `schedule/inputs.py`**, enforced
  per-module in CI; **no global percentage target.** A global gate on a codebase
  containing a browser driver produces tests written to move a number.

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

Two open questions, to be settled by direct tests of `build_requirement_tree` once
inference is decomposed:

1. **Label rows are grafted onto the preceding requirement.** `Note.` has no top-level
   number, so `requirement_path` prepends the last-seen one, making a note a *child* of
   requirement 7. If requirement 7 is a "Do TWO of the following" choice, the note
   enters the satisfied-child arithmetic. Whether this changes a reported completion
   status depends on `calculate_statuses`. **Hypothesis, not a confirmed defect.**
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

## Python conventions

- **Ruff** for lint and format, replacing black, isort, flake8, and pyupgrade, with an
  explicit rule selection rather than defaults.
- **mypy strict** on `src/`, lenient on `tests/`. `dict[str, Any]` is confined to
  `session.py` and `payloads.py`; everywhere else is strictly typed owned models.
- **`logging` replaces all 19 `print()` calls.** Library modules take module-level
  loggers and never configure handlers; the CLI and launcher configure them. The three
  silent `except Exception:` sites become `logger.exception(...)`.
- **`ScoutmbError` hierarchy** replaces the raw `RuntimeError`s (five in `bootstrap/`),
  carrying structured context rather than pre-formatted strings.
- **`[project.scripts]`** for console entry points.
- **pytest** with fixtures and `parametrize`; no `unittest.TestCase`.
- **Lazy heavyweight imports** — `openpyxl` moves inside `load_xlsx` so pure logic is
  importable without it (defect 4).
- **Shared loader helpers** — the four input loaders currently duplicate header-alias
  resolution; `norm_header` / `first_matching_key` become one shared path so a new alias
  is added in one place (DRY).
- Protocols over ABCs, frozen slotted dataclasses, `pathlib`, `importlib.resources`.
  The existing code already uses `@dataclass(frozen=True, slots=True)` and `pathlib`
  correctly; this continues established practice rather than imposing something new.

## Continuous integration

| Job | Runs on | Contents |
| --- | --- | --- |
| `lint` | ubuntu | ruff check, ruff format --check |
| `types` | ubuntu | mypy strict on `src/` |
| `test` | ubuntu, windows | pytest with `pytest-socket`, per-module coverage gates |
| `lock` | ubuntu | verify `uv.lock` matches `pyproject.toml` |
| `build` | ubuntu | build wheel, verify packaged assets are present |
| `launcher` | windows (+ macos from phase 5) | PyInstaller build smoke test |

Playwright browsers are **not** installed in the default CI job — `@pytest.mark.live` is
excluded, so nothing needs a browser. A separate manually-triggered workflow runs the
live contract suite.

## Design decisions

Recorded so the rationale survives, since each was questioned during review:

| Decision | Rationale |
| --- | --- |
| Keep `errors.py` hierarchy | Explicit choice to design it upfront rather than grow it |
| Keep `ProgressReporter` with three implementations | Required by planned future work, not speculative |
| Keep self-update | Accepted complexity; mitigated by rollback and browser revalidation |
| Wire-boundary `dict[str, Any]`, not `TypedDict` | The upstream API is not ours; declaring its shape as a type would encode an assumption we cannot enforce and would turn upstream renames into silent `None`s |
| Technical layout (`reports/`, `cli/`, `webapp/`), not domain-based | A deliberate deviation from CUPID's domain-based principle, appropriate at this size; revisit if the domain grows |
| Wheel + lock, not loose-file sync | Eliminates both `sys.path` hacks and the stale-file problem |

## Phases

| Phase | Work | Exit criterion |
| --- | --- | --- |
| **0** | pyproject, uv.lock, ruff, mypy, pytest, CI; scrubber (TDD); reduced fixtures; characterization tests against **flat** modules | Green CI; safety net in place; **zero app code moved** |
| **1** | Extract `src/scoutmb/`: models, config, runtime, progress, errors, payloads, tree, statuses, inputs, reports. Decompose inference. Flat scripts become shims | Phase 0's characterization tests pass against new import paths |
| **2** | `ScheduleSession`; `PlaywrightSession` + `RecordedSession`; contract suite; `process_scout` pure; HTML to asset | `process_scout` tested with no browser; contract suite green on both implementations |
| **3** | `cli/` console scripts, flat scripts deleted; `webapp/` with `JobRegistry` + routers; both `sys.path` hacks gone | Routes tested under `TestClient` |
| **4** | Bootstrap rebuild: platforms, standalone runtime, venv, wheel install, `data/` split, self-update, rollback, browser revalidation | Windows launcher verified end to end, including a forced-rollback test |
| **5** | macOS: `macos.py`, CI matrix on both runners, notarization | A macOS launcher that runs |

Phase 1's exit criterion is load-bearing. Characterization tests written against the old
flat modules, still passing after the code moves, is the actual proof that behavior did
not change — not code review, not confidence.

Phases 0–3 (application code) and phases 4–5 (launcher) are separable. If the work is
split across efforts, phase 3 is a clean stopping point.

## Risks

| Risk | Mitigation |
| --- | --- |
| Playwright extraction has no prior characterization test | Mechanical move only; manual end-to-end verification; `RecordedSession` coverage immediately after |
| Scrubber leaks real data into a commit | Self-verifying scrubber over all artifacts and filenames; own TDD suite with leaky inputs; `/raw_data/` gitignored; review fixture diffs before commit |
| Upstream API changes shape | Anti-corruption layer with drift reporting; property-based tests assert no crash on arbitrary payloads |
| Bad wheel bricks installations | Retained previous wheel; automatic rollback after two consecutive launch failures |
| Playwright/browser version skew after update | Mandatory browser revalidation when the resolved playwright version changes |
| `python-build-standalone` behaves unlike the embeddable distribution | Phase 4 is Windows-only and verified end to end before phase 5 adds a second platform |
| macOS Gatekeeper blocks unsigned launcher | Known cost; Apple Developer Program is a purchasing decision tracked outside this plan |
| tkinter under PyInstaller on macOS is historically fragile | Phase 5 detour if it manifests; not a blocker |
| Scope creep from discovered bugs | Characterization tests pin current behavior including bugs; fixes are separate changes with their own failing tests |

## Open questions

None blocking. The two suspect behaviors in `requirement_path` (label-row grafting,
empty rows) are resolved by direct tests of `build_requirement_tree` in phase 1 rather
than by advance decision, and any resulting fix is scheduled separately per the risk
table.
