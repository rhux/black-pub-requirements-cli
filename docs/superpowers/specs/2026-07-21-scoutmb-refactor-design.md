# scoutmb: Restructure Design

**Date:** 2026-07-21
**Status:** Approved design, pending implementation plan
**Supersedes:** `docs/refactor-plan.md` (merged into this document)
**Reviewed by:** Claude (self-review), OpenAI Codex (independent, against the codebase)

## Problem

The repository began as a quick script and accreted into a real application: two CLI
pipelines, a FastAPI web UI, a desktop launcher, and a 14-module self-bootstrapping
Windows installer.

| Component | Lines (`wc -l`) | Role |
| --- | --- | --- |
| `scout_schedule_cli.py` | 1,798 | Stage 2: scrape, infer, report |
| `pdf_to_scouts.py` | 579 | Stage 1: PDF to CSV |
| `ui/server.py` | 339 | Local FastAPI app |
| `ui/static/app.js` | 328 | Frontend |
| `run_app.py` | 89 | Native-window entry point |
| `bootstrap/` | 14 modules | Windows self-installing launcher |

There is no package, no `pyproject.toml`, no tests, no linter, no type checker, and no
CI. Nothing pins current behavior. All line references below were verified against the
current tree.

### Correctness defects in shipped code

1. **Attendee identity is the display name, not a stable ID.** Inference groups on
   `(scout_name, class_p4_id)` (`:675`); `build_missing_requirements` builds `by_key` on
   `(scout_name, class_p4_id, requirement_number)` (`:786`) and buckets output by
   `scout_name` (`:838-840`); email lookup is `missing.get(scout_name)` (`:920`); email
   filenames are `safe_slug(scout_name)` (`:935`); raw audit payloads are
   `safe_slug(result.name)` (`:490`). **Two attendees with the same name have their
   requirements merged and their output files overwritten.** `attendee_id` is read at
   `:919` and then never used. At troop scale this is unlikely; at council-camp scale it
   is probable, and the failure mode is a child being told they completed requirements
   they did not.
2. **Unreferenced background tasks.** `ui/server.py:162,223` call
   `asyncio.create_task(worker())` without retaining the result; CPython holds only weak
   references, so a long job can be collected mid-execution.
3. **Four UI defects.** `stale.unlink()` without an `is_file()` guard (`:114-116`,
   `IsADirectoryError` on a subdirectory); `os.startfile` (`:334`) is Windows-only;
   `webbrowser.open` server-side (`:301`); unguarded `json.loads` at `:205`, `:296`,
   `:311`.
4. **`--quiet` is not honored** at `pdf_to_scouts.py:571`, despite guards at `:515`
   and `:557`.

### Structural defects

5. **`scout_schedule_cli.py` has no internal boundaries.** One module holds argument
   parsing, four input loaders, Playwright control, AJAX scraping, requirement-status
   inference, email rendering, a 658-line embedded HTML string, and six output writers.
6. **`process_scout` (141 lines) fuses browser control, retry policy, deduplication,
   JSON-to-record mapping, and filesystem writes.**
7. **`argparse.Namespace` is threaded into the scraping layer.** `ui/server.py:188-201`
   hand-builds a fake Namespace with 12 fields, and the core defends itself with
   `getattr(args, "channel", None)` (`:1726`) and `getattr(args, "email_report", False)`
   (`:1779`) — options already silently default on the UI path.
8. **Inference is untyped and closure-nested.** `annotate_requirement_statuses` takes and
   returns `list[dict[str, Any]]` with a nested recursive `calculate`. It is invoked from
   two consumers — HTML (`:981`) and email via `build_missing_requirements` (`:783`) —
   *conditionally*, at `:1687` and `:1692` respectively. Under default configuration it
   runs once.
9. **`build_missing_requirements` keys bookkeeping on `id(item)`** (`:801`, `:807`,
   `:808`, `:825`, `:835`). It is not a live defect — the dicts stay referenced by
   `annotated` for the call's duration, so identities are stable — but it is fragile by
   construction, invisible to a type checker, and **breaks the moment inference moves to
   dataclasses**, which is exactly what the `inference/` decomposition does. The
   ancestor-walk selection it implements must be re-expressed over explicit node indices
   or an identity field before that move.
10. **Two `sys.path` hacks.** `ui/server.py:25` inserts the repo root; `python_env.py:62`
   patches the app directory into the embeddable Python's `._pth`.
11. **Heavyweight imports block testing.** `scout_schedule_cli.py:27` imports `openpyxl`
    at module scope, so importing even `requirement_path` requires every dependency.
12. **`parse_args()` takes no `argv`** (`:88`), a hard prerequisite for CLI testing.
13. **`print()` is the logging system** — 19 calls, nine `except Exception` sites, three
    swallowing silently (`:363`, `:400`, `:468`).
14. **Nondeterminism in business logic.** `time.strftime`/`datetime.now()` (`:1644-1645`),
    `random.uniform` (`:1765`), `uuid4` (`ui/server.py:110,174`).
15. **Untyped external payloads.** `scoutingevent.com` responses flow through as
    `dict[str, Any]`; an upstream rename produces silently wrong completion status.
16. **Duplication.** `DEFAULT_ADULT_TYPES` (`pdf_to_scouts.py:23`) is re-declared as a
    literal set at `scout_schedule_cli.py:212`; header-alias lists appear three times.
17. **User data commingled with replaceable source.** `scouts.csv`, `pdf-uploads/`, and
    `runs/` live in the directory the launcher overwrites on each start.

### Claims explicitly retracted

Earlier drafts of this spec asserted three things that inspection disproves. Recorded so
they are not reintroduced:

- **Inference does *not* mutate caller-owned dictionaries.** `:672` does
  `annotated = [dict(item) for item in requirements]`; every later mutation targets a
  copy. It is non-mutating at its public boundary.
- **The two consumers do *not* receive differently-shaped input.** Both pass
  `asdict(RequirementRecord)` rows — `:981` directly, `:1655` nested. `requirement_type_id`
  is already coerced with `str(...)` at `:574`. There is no shape divergence to reconcile.
- **`write_html_report` does *not* read the wall clock.** It accepts
  `generated_at_local` and `generated_at_iso` as parameters (`:975`). The nondeterminism
  lives in its caller.

## Goals

- A `src/`-layout package with typed boundaries, an injectable transport seam, a real
  test suite, and standard Python tooling.
- Correct attendee identity, so two same-named Scouts cannot corrupt each other's data.
- Reproducible output, so behavior can be pinned by golden tests.
- Resilience to upstream schema drift, with drift made visible rather than silent.
- A launcher portable to macOS that can update the application safely.
- Preserve the one existing installation's user data.

## Non-goals

- Rewriting the inference algorithm. It is characterized and preserved.
- Shipping a signed macOS build. Notarization is a purchasing decision (Apple Developer
  Program, USD 99/yr) tracked separately.
- Replacing the frontend with a framework.
- **Self-updating the launcher itself** — see "Update scope honesty" below.

## Constraints

- **Runtime target is Python 3.12.** `requires-python = ">=3.12"`, ruff
  `target-version = "py312"`, mypy `--python-version 3.12`, 3.12 primary in CI. The dev
  venv is 3.14; a 3.13/3.14-only API would ship broken with no diagnostic path.
- **No real Scout data in the repository, ever.** QR URLs and attendee IDs are bearer
  tokens for real minors' records. `/raw_data/` is gitignored (`.gitignore:13`).
- **The launcher's audience is non-technical.** Double-click to run; never touch or
  require a system Python.
- **One installation exists in the wild, holding real user data.** Breaking the install
  (requiring a re-run of setup) is acceptable. **Destroying its data is not.**
- **The upstream API is not ours.** `scoutingevent.com` may change payload shape without
  notice.

---

## ⚠️ Coupled hazards — read before any code moves

### Hazard 1 — `__file__`-derived data paths

```python
REPO_ROOT = Path(__file__).resolve().parent.parent   # ui/server.py:24
SCOUTS_CSV = REPO_ROOT / "scouts.csv"                # :35
PDF_UPLOADS_DIR = REPO_ROOT / "pdf-uploads"          # :36
RUNS_DIR = REPO_ROOT / "runs"                        # :37
```

Today `__file__` is `app_dir/ui/server.py`, so `REPO_ROOT` resolves to `app_dir` and data
lands beside the app. After a move to `scoutmb/ui/app.py`, `.parent.parent` silently
becomes `app_dir/scoutmb` — **user data relocates inside the package directory.** Under
wheel deployment this is worse still: the package lives at
`venv/lib/site-packages/scoutmb/`, a directory `pip install --force-reinstall` replaces
wholesale.

**Fix:** `UiSettings` takes an explicit `data_root`, resolved in this order:

1. Explicit constructor argument (tests, embedding)
2. `SCOUTMB_DATA_DIR` environment variable (set by the launcher)
3. Platform user-data directory
4. `Path.cwd()` **only** in an explicit development mode

`Path.cwd()` is not an acceptable production default — it depends on how a shortcut,
terminal, or `.app` bundle launched the process. **Never derive data paths from
`__file__`**, enforced by a lint rule and a regression test.

### Hazard 2 — destructive install replacing a permissive sync

`source_sync.py`'s docstring promises *"never a directory wipe — scouts.csv,
pdf-uploads/, and runs/ live in the same app\ folder as user data and must survive
untouched."* That comment is load-bearing. Wheel installation violates it — safely
**only if** the package directory holds no user data, which is exactly what Hazard 1
would break.

### Hazard 3 — ordering

The UI move (originally Phase 7) triggers Hazard 1, but the launcher does not export
`SCOUTMB_DATA_DIR` until the bootstrap phase. In between, `bootstrap/main.py:55` starts
the process with `cwd=paths.app_dir`, so `Path.cwd()` still commingles data with
replaceable files. **Data-root resolution and legacy migration must land before the UI
module moves**, not after. This reordering is reflected in the phase table.

---

## Legacy migration

One installation exists with real data at `app/{scouts.csv,pdf-uploads,runs}`. The
migration is **copy-only, never move or delete**:

1. If `data/` already contains a marker (`data/.migrated`), do nothing. Idempotent.
2. Copy `app/scouts.csv`, `app/pdf-uploads/`, `app/runs/` into `data/`.
3. Verify each copy (size and hash for files; recursive count for directories).
4. Write `data/.migrated` recording source paths, timestamp, and file count.
5. **Leave the originals in place.** `app/` is abandoned, not cleaned. If migration is
   wrong, the data is still there.

With a single known install, disk cost is irrelevant and deletion buys nothing. Manual
cleanup is a later, optional step. Collision handling: if a destination already exists
and differs, write alongside as `<name>.legacy` and record it in the marker rather than
overwriting.

---

## Architecture

### Package layout

```
pyproject.toml   uv.lock   requirements.txt (generated, pinned — installer input)
src/scoutmb/
  __init__.py  __main__.py  errors.py  config.py  clock.py  progress.py  logging_setup.py

  domain/      models.py      ScoutInput / ClassRecord / RequirementRecord / ScoutResult
               identity.py    AttendeeKey — stable attendee identity (see below)
               enums.py       RequirementStatus, SECTION_HEADER_TYPE_ID, ADULT_REGISTRANT_TYPES
               text.py        clean_html_description

  inference/   PURE — no I/O; takes and returns dataclasses, never dicts
               numbering.py   CHOICE_COUNT_WORDS, requirement_path, choice_requirement_count
               tree.py        grouping, parent linking, header-stack fallback
               status.py      the de-nested `calculate` closure
               missing.py     build_missing_requirements

  inputs/      headers.py     norm_header, first_matching_key, alias lists
               loaders.py     xlsx / csv / json / text        pipeline.py  load_inputs

  scrape/      payloads.py       PURE mapping + anti-corruption layer + drift policy
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
tools/scrub_fixtures.py  tools/verify_corpus.py
bootstrap/     platforms/  manifest.py  migrate.py  update/  …    (repo root, outside the package)
```

**No junk drawers.** Every module is named for a *subject*, never a *role*. A pre-commit
hook rejects `utils.py`, `helpers.py`, and `common.py` under `src/`.

*Acknowledged tension:* this is roughly 35 modules for ~3,100 lines of application code,
which is fine-grained. The split is justified where it creates a testable seam
(`inference/`, `scrape/`) and is thinner justification elsewhere. Modules that stay under
~40 lines after Phase 3 should be merged into their nearest subject sibling rather than
kept for symmetry.

`bootstrap/` **stays at the repo root**, outside the package: it runs before the
application's dependencies exist, may import only the standard library, and is frozen
separately. Add `[tool.hatch.build] exclude = ["bootstrap"]`.

### Attendee identity

The root correctness fix. A stable `AttendeeKey` derived from `attendee_id` becomes the
internal identity for grouping, lookup, and filenames; **`scout_name` is display data
only.**

- Inference groups on `(attendee_key, class_p4_id)`.
- `build_missing_requirements` keys on `attendee_key`.
- Email and raw-payload filenames are `f"{safe_slug(name)}-{attendee_key.short}"`, so
  they stay human-scannable while being collision-free.
- `attendee_id` is a bearer token, so `AttendeeKey.short` is a **non-reversible digest
  prefix**, never the raw ID — filenames must remain safe to share.

This is a **behavior change**, not a refactor: output filenames change. It therefore gets
its own failing tests first and its own phase, and it lands **before** any code moves, so
every characterization golden is captured against corrected identity rather than needing
regeneration later.

### Console entry point

`[project.scripts] troop349 = "scoutmb.cli.app:main"`, with subcommands `extract-pdf`,
`download`, and `ui`. Root shims re-export during migration and emit a **`FutureWarning`**
naming `troop349` — `DeprecationWarning` is hidden by default and would be invisible to
the one person who needs to see it. Shims are retained for **at least one released
version**, not deleted in the same cycle they are introduced.

### Typed config replaces `Namespace` threading

Frozen slotted dataclasses in `config.py`: `BrowserOptions`, `PacingOptions`,
`InputOptions`, `ReportOptions`, composed into `ScrapeConfig` and `ExtractConfig`.
`argparse` populates them in `cli/args_*.py`; **the `Namespace` never leaves that
module.** `ui/server.py:188-201` collapses to a `ScrapeConfig(...)` construction, so a new
option can no longer silently default on the UI path and both `getattr(args, …)` calls are
deleted.

Magic numbers become named fields: retry attempts (`range(1, 4)` at `:538`), backoff
(`500 * attempt` at `:546`), jitter (`(0.5, 2.0)` at `:1765`).

`--quiet` leaves the config entirely and becomes global `-q`/`-v` verbosity, fixing
`:571` by construction.

### Determinism

Nondeterminism is injected **per-collaborator**, not bundled. An earlier draft proposed a
single `RunContext` carrying clock, IDs, RNG, progress, and sleep; that is a service bag
mixing unrelated concerns — progress reporting is not nondeterminism. Instead:

| Source | Location | Injected as |
| --- | --- | --- |
| `time.strftime` → `generated_at_local` | `:1644` | `Clock` |
| `datetime.now()` → `generated_at_iso` | `:1645` | `Clock` |
| `time.strftime` run IDs | `ui/server.py:65` | `Clock` |
| `uuid4()` operation IDs | `ui/server.py:110,174` | `IdFactory` |
| `random.uniform(0.5, 2.0)` pacing | `:1765` | `Jitter` |
| `page.wait_for_timeout` in retry | `:546` | `Sleeper` |

Each operation takes only what it needs. Retry needs `Sleeper`, not a clock; report
writing needs `Clock`, not an RNG. Production pacing does not need to be seeded merely to
make goldens deterministic — goldens use a fixed `Jitter` stub.

`write_html_report` already accepts its timestamps as parameters (`:975`) and needs no
change on this axis.

### Requirement inference

Decomposed rather than relocated, into `inference/{numbering,tree,status,missing}.py`.
The boundary is **dataclasses in, dataclasses out** — no dicts cross it.

Both consumers (HTML at `:981`, email at `:783`) receive the same `asdict(RequirementRecord)`
shape today and are pinned separately before unification — not because their shapes
diverge (they do not), but because they are independently reachable code paths with
different enclosing conditions (`:1687` vs `:1692`).

**The `id()` dependency is the blocking prerequisite for `missing.py`.** Today
`build_missing_requirements` selects actionable leaves and walks their still-incomplete
ancestors using `dict[int, bool]` keyed on `id(item)` (`:801`, `:807`, `:808`, `:825`,
`:835`). That works only because the dicts remain referenced by `annotated` for the
call's duration — and it stops working the instant those dicts become frozen dataclasses,
which are neither guaranteed-distinct by identity nor safe to key on that way.

The decomposition therefore re-expresses the ancestor walk over **explicit node indices**
into the tree produced by `tree.py`, with `selected: dict[NodeIndex, bool]`. This is a
structural rewrite of `:801-836`, not a copy, and it is the one place in the inference
extraction where the code cannot move mechanically. It gets its own characterization
tests covering leaf selection, ancestor inclusion, the `(not used)` filter, and the
`requirement_type_id == "3"` section-header exclusion **before** the rewrite.

### External payload handling

`scrape/payloads.py` is an anti-corruption layer with an explicit **severity policy**.
"Record drift and continue" is unsafe as a blanket rule: silently continuing past a
missing `classP4ID` or completion flag produces confidently wrong results, which is the
exact failure this design exists to prevent.

| Field class | Examples | On missing / wrong type |
| --- | --- | --- |
| **Critical identity/structure** | `data`, `status`, `classP4ID`, requirement ID | **Fail that scout/class**, record an error |
| **Critical semantics** | `COMPLETED_REQ_FLAG`, `COMPLETED_CLASS_FLAG` | **Fail**, never coerce an unparseable value to false |
| **Optional display** | `MERIT_BADGE_NAME`, `REQ_DESCR`, `PRESENT_DAYS` | Warn, record drift, continue with a placeholder |
| **Unknown / added** | anything not in the known set | Ignore; aggregate as low-severity telemetry only |

This resolves a contradiction in the previous draft, which said unknown fields are ignored
while simultaneously requiring a test that an added field "reports drift."

Each `SchemaDrift` carries: JSON path, severity, source operation, row identity
(attendee key + class), and a redaction flag. Drift is deduplicated by
`(path, severity, operation)` so one upstream rename produces one report line, not 4,858.
Counts surface in `errors.csv` and `summary.json`.

Flag coercion tolerates `"1"`, `"0"`, `""`, and `None` — the corpus contains 309 rows with
`(None, None)` — and treats anything else as critical drift rather than falsy.

`Mapping[str, Any]` appears only in `ports.py` and `payloads.py`. Declaring the upstream
shape as a `TypedDict` was rejected: it encodes an assumption we cannot enforce and turns
renames into silent `None`s.

### `process_scout` splits at a `SchedulePort`

```python
class SchedulePort(Protocol):
    async def open_scout(self, qr_url: str, fallback_name: str) -> ScheduleFetch: ...
    async def fetch_requirements(self, attendee_id: str, class_p4_id: str) -> Mapping[str, Any]: ...
    async def aclose(self) -> None: ...
```

Above it, `payloads.py` is pure and synchronous. A test loads a fixture and asserts a
`list[ClassRecord]` — no browser, no async, no network. **This extraction makes roughly
80% of the scraping logic testable.** Retry moves to `retry.py` with an injected
`Sleeper`; raw writes move to a `RawPayloadStore` with a `NullRawStore` for tests.

### The 658-line template → package data, three files, `str.replace()`

The template uses **exactly one substitution** (`:1627`) — no f-string, no `.format()`.
**No Jinja2.** It would add a runtime dependency that changes
`marker.compute_requirements_hash`, and would require escaping every `{`/`}` across 206
lines of CSS and 278 lines of JS full of `${…}` template literals. The doubled-brace email
template at `:886-893` already demonstrates that corruption mode.

Split into `templates/report.{html,css,js}`, loaded via `importlib.resources.files()` with
an `lru_cache`. **Substitute CSS → JS → DATA, always DATA last** — scout data can contain
the literal string `__REPORT_JS__` and survives JSON escaping, so data-last makes
injection impossible. Assert no `__REPORT_` token remains, and test a scout named
`__REPORT_JS__`.

For `ui/static/`, `importlib.resources.files()` alone is insufficient: a `Traversable` is
not guaranteed to be a real filesystem directory, which `StaticFiles` requires. Use
`as_file()` bound to the app lifespan, and **test it from an installed wheel, not the
source tree**, where the distinction is invisible.

### Deployment

```
<app root>/           # %LOCALAPPDATA%\ScoutingMeritBadges          (Windows)
                      # ~/Library/Application Support/ScoutingMeritBadges  (macOS)
  runtime/            # python-build-standalone — disposable
  envs/               # A/B application environments (see below)
    <version>/        # venv + installed wheel
  current -> envs/<version>
  data/               # scouts.csv, pdf-uploads/, runs/ — SCOUTMB_DATA_DIR points here
  state/              # marker, browser channel, release cache, update throttle
  logs/
```

Standalone Python plus a normal venv is an ordinary Python environment, so the `._pth`
patching at `python_env.py:47-69` disappears, as does `ui/server.py:25`.

**Platform dispatch**, segregated by concern rather than one omnibus protocol:

```
bootstrap/platforms/
  paths.py      app_root, python_exe, gui_python_exe
  runtime.py    standalone runtime URL + extraction
  browser.py    preferred Playwright channel
  webview.py    ensure_webview  (WebView2 on Windows; no-op on macOS)
  windows.py  macos.py   — concrete implementations, lazily imported
```

`webview2.py` has a module-level `import winreg` and evaluates `winreg.HKEY_*` at import;
store hive *names* as strings and move the import into the function. `paths.py:33` does
`os.environ["LOCALAPPDATA"]` — use `.get()` with a diagnosable error. Then `bootstrap`
imports on every platform and only the registry test is skipped.

`bootstrap/manifest.py` is the single source of truth for what the exe bundles, imported
by `build.spec` (spec files execute as Python). `hiddenimports` becomes
`collect_submodules("bootstrap")`.

### Update scope honesty

**This design updates the application, not the launcher.** `bootstrap/` is excluded from
the wheel and frozen into the exe, so a downloaded wheel can never update the updater,
platform dispatch, rollback logic, or the launcher itself. Launcher changes require the
user to download a new exe. The feature is named **application self-update** throughout,
and the launcher surfaces a "a newer setup is available" notice when the release manifest
advertises a launcher version newer than its own.

### Release bundle and integrity

A release is **not a bare wheel**. It is a versioned bundle with a signed manifest:

```
release-<version>.json     # manifest: versions, asset names, sizes, SHA-256, min-launcher
scoutmb-<version>.whl
constraints-<platform>.txt # exported pinned resolution
```

Update rules, all mandatory:

- **SHA-256 verified** against the manifest before any install; manifest signature
  verified against a key bundled in the exe.
- **Allowed asset names and maximum sizes** enforced; anything else is rejected.
- **Downgrade prevention** — never install a version lower than the installed one unless
  performing an explicit rollback.
- **Atomic download** to a temp path, then rename.
- Dependencies install from `constraints-<platform>.txt`, **not** from wheel metadata
  ranges resolved live — otherwise the lockfile guarantee is discarded at the moment it
  matters most.

Without this, a corrupt or substituted artifact is arbitrary code execution on a
volunteer's laptop.

### A/B environments, health check, and rollback

Retaining "the previous wheel" is insufficient once dependencies, Python, or Playwright
have also moved; reinstalling an old wheel into a mutated venv can leave it broken. Instead:

1. Build the candidate in `envs/<new-version>/` — a **fresh venv**, never a mutation of
   the live one.
2. **Smoke-test the candidate**: `python -c "import scoutmb"`, the existing
   `SMOKE_TEST_IMPORTS` (with `"scoutmb"` added), and a Playwright browser-presence check.
3. Switch `current` atomically only after the smoke test passes.
4. **Health acknowledgement**: the application writes `state/health-ok-<version>` once it
   has served its first request. The launcher treats a version with no acknowledgement
   after two launches as failed, restores `current` to the last acknowledged version, and
   logs the downgrade. The counter resets on acknowledgement.
5. Retain the last known-good environment; prune older ones.

"Launch succeeded" is thus explicitly defined, which it is not today —
`bootstrap/main.py:53` merely `Popen`s and sleeps two seconds.

**Update check** runs at most once per 24 hours (recorded in `state/`), bounded by a
3-second timeout. Any failure is logged and the installed version launches anyway.
**Startup never blocks on an update check** — the deployment environment is a Scout camp
with unreliable connectivity.

`PLAYWRIGHT_BROWSERS_PATH` is set under `state/`, and browsers are revalidated whenever
the resolved `playwright` version changes — the package is version-coupled to its browser
binaries, and skipping this yields an app that starts and then fails mid-scrape, offline.

---

## Testing

### TDD discipline

**New code: strict red-green-refactor.** `AttendeeKey`, `SchedulePort`, `FakeSchedulePort`,
`JobRegistry`, `ProgressSink`, `Clock`/`IdFactory`/`Jitter`/`Sleeper`, `payloads.py` drift
policy, `errors.py`, platform modules, the update/rollback state machine, `manifest.py`,
`migrate.py`, and the scrubber.

**Deliberate behavior changes: strict red-green-refactor.** Attendee identity, the
`no_html` → `generate_html` inversion, the `troop349` CLI surface, `-q`/`-v`, drift
severity, and the report-opening change.

**Code motion: characterization-first.** Pin behavior, then move. **Characterization tests
pin bugs too** — where a test documents behavior believed wrong, it is committed as-is
with a comment, and the fix is a separate change with its own failing test. Refactoring
and bug-fixing never share a commit.

### Sequencing that keeps CI green and RED real

1. **Phase 1.** Characterization tests import the **flat modules** and pass.
2. **Later phases, per module.** Write a one-line import test against the new path:
   `from scoutmb.inference.numbering import requirement_path` → **RED** (`ImportError`).
3. Move → **GREEN**.
4. Re-point that module's characterization tests; delete the temporary import test.

The RED step catches the failure where a characterization test silently keeps importing
the old module and passes while proving nothing.

### The TDD gap is much smaller than previously claimed

An earlier draft accepted that `process_scout` could not be characterized before
extraction. That was wrong. `navigate_and_trigger_schedule` (`:368`), `discover_name`
(`:347`), and `post_requirement` (`:417`) are **module-level functions called by name** at
`:479`, `:486`, and `:540`. Monkeypatching them is standard pytest practice, and
`post_requirement` itself needs only a fake `page.evaluate`. `process_scout` therefore gets
full characterization coverage — orchestration, retry, dedup, error accumulation, exact
error strings — **before** the port extraction, with only a minimal fake for
`browser.new_context`.

The residual gap is the Playwright adapter internals themselves (selector chains, response
matching). Those are covered by the tier-3 fake-site test, which **runs in CI** (below).
A manual run against private data is not a repeatable regression test and is no longer
part of the plan.

### Playwright, three tiers

1. **`FakeSchedulePort`** — runner, retry, dedup, mapping. Always runs.
2. **`SimpleNamespace`** for `is_schedule_response` and `form_values`, which only read
   attributes.
3. **`@pytest.mark.playwright` against a local fake ScoutingEvent** — deterministic and
   network-independent, so it **runs in CI** as a separate job, on adapter changes and
   nightly. This is the only test that catches a stale selector in the `:384-397` fallback
   chain; excluding it entirely would make omitting `playwright_port.py` from coverage
   indefensible.

**Do not mock `Page`/`Response` with `unittest.mock`.** The surface used is deep enough
that the mock becomes the thing under test.

### Fixture corpus

`raw_data/` (local, gitignored) holds three real runs. Measured locally: each contains 22
scouts, 98 classes, **4,858 requirements**, 120 raw payloads.

**The three runs are identical in completion state** — across 4,858 shared rows,
`2026-07-18_1835` → `2026-07-18_1938` → `2026-07-19_2139` show **zero** flag changes. The
event (2026-07-06) had concluded.

These counts are **locally measured and not independently verifiable in review**, since
the corpus cannot leave the machine. `tools/verify_corpus.py` reproduces them and prints
only aggregate counts — never names, IDs, or payload content — so the numbers can be
re-checked without exporting anything.

Consequences: **one run is the fixture corpus**; identical output across three runs is
worth one determinism golden; **state transitions must be synthesized** by mutating
completion flags over the real row structure.

### Fixture safety

Real data appears in **every** artifact: `classes.csv` carries `scout_name` and an 8-digit
`attendee_id` per row; `report.html` contains 4,978 attendee-ID references. Zero
`scoutingevent.com/mobile` URLs appear in generated reports, so QR bearer tokens do not
propagate downstream.

- `tools/scrub_fixtures.py` covers **all** artifacts and **filenames**.
- **It verifies itself**: after substitution it scans output for every original name,
  attendee ID, and QR token, including surname-level partial matches.
- **Full TDD treatment** with deliberately leaky inputs: a name in a filename, an ID in an
  HTML attribute, a name only in an email body, and a name that is a substring of another.
- **Conftest tripwire**: fail if any file under `tests/fixtures/` contains a
  `scoutingevent.com/mobile/` URL whose token doesn't start with `TESTTOKEN`.
- **Pre-commit hook** rejecting `*.pdf` at the repo root.

### Committed fixtures must be small

The real `report.html` is **3,092,771 bytes**. Goldens use a **reduced 2–3 scout corpus**;
HTML is asserted **structurally** by parsing the injected JSON payload, never by
byte-comparing the document; CSV and JSON are compared in full.

### Fixture PDFs are generated, not committed

Commit the *builder*. PyMuPDF `insert_image` builds the page with the label/value layout
`value_after_label` (`:176-186`) expects. A second variant draws the QR as vector content
so `decode_embedded_qr` returns empty and the rendered fallback (`:365-380`) actually runs.
QR generation uses `cv2.QRCodeEncoder` (OpenCV is already a runtime dependency), with
`segno` as a test-only fallback if unavailable in the pinned build.

### Required coverage

| Area | Requirement |
| --- | --- |
| **Attendee identity** | Two same-named attendees: requirements stay separate, emails and raw files do not collide; slug-equivalent names; `AttendeeKey.short` is non-reversible |
| `requirement_path` | All 18 observed shapes as a `parametrize` table |
| Inference purity | Input dictionaries are not mutated (guards the copy at `:672`) |
| Tree edge cases | Duplicate requirement numbers, repeated headers, empty paths (402 rows), label rows (375), out-of-order rows, parent-lookup collisions |
| Completion flags | All 5 observed `(REQ, CLASS)` combinations, including 309 `(None, None)` |
| Choice requirements | Every corpus wording, plus synthesized threshold crossings |
| Inference consumers | HTML (`:981`) and email (`:783`) pinned **separately** |
| Schema drift | Critical vs optional vs unknown fields; malformed containers; arbitrary JSON never raises |
| Schedule payloads | Parsing tested, not only requirement payloads |
| Dedup | "Prefer the completed duplicate" (`:510`), fixture written first |
| Retry | Exactly 3 attempts at 500/1000/1500 ms |
| CSV | Exact header rows (guards `__dataclass_fields__` order at `:1666`, `:1671`); `extrasaction` removal (`:602`) surfaces mismatches |
| Loaders | All four formats, every header alias |
| CLI | Defaults, all exit codes, invalid combinations, **CLI/UI config parity** |
| PDF | Directory/glob ordering, corrupt PDFs, embedded and rendered QR paths, adult filtering, duplicate QRs, strict mode, debug output, stale error-file deletion, case normalization |
| Atomicity | A failed extraction preserves the prior `scouts.csv` |
| Template | No `__REPORT_` token survives; a scout named `__REPORT_JS__`; `</script>`, `&`, U+2028/U+2029 |
| UI routes | Isolated app instances, concurrent-job rejection, **task retention**, cancellation, SSE disconnect/reconnect, registry cleanup, malformed summaries, worker exceptions |
| Frontend | Upload, download, pause/resume, errors, report opening, button restoration |
| Packaging | Installed-wheel resource resolution on Windows, macOS, Linux |
| Bootstrap | Platform/arch selection, lock races, corrupt markers, first install, update throttle, offline start, **checksum failure**, interrupted install, health acknowledgement, rollback, rollback failure, dependency change, browser-version change |
| Migration | Legacy `app/` → `data/` copy, idempotency, collision handling, reinstall survival |
| Scrubber | Leaky-input suite |

`bootstrap/downloader.py` is **not** excluded from testing. Real internet calls are
excluded; downloader behavior is tested against a local HTTP server or an injected opener.

### Coverage gates

**Enforcement mechanism matters**: `pytest --cov` provides a single global `fail_under`,
not a per-package table. Per-area floors are enforced by explicit
`coverage report --include=<glob> --fail-under=<n>` invocations in CI, with **branch
coverage enabled**.

| Package | Floor |
| --- | --- |
| `inference/`, `scrape/payloads.py`, `domain/identity.py` | 95% |
| `inputs/`, `emails/`, `storage/`, `cli/` | 90% |
| `pdf/` | 80% |
| `ui/` | 70% |
| `bootstrap/` | 60% |
| `scrape/playwright_port.py` | omitted — covered by the tier-3 CI job |

The **75% global floor is a Phase-3 milestone, not the final target**; it rises to 85%
once the UI and bootstrap suites land.

### Do not test

`bootstrap/ui.py` (tkinter), `install_webview2` (runs an .exe), `install_chromium_fallback`
(20-minute download), `desktop.py`'s webview launch, `build.spec`, `os.startfile`, and the
report's CSS.

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

Resolved, recorded to prevent re-investigation: `choice_requirement_count` handles
`do|complete|choose|select|perform` (`:654`). Measured against every unique corpus
description: **22 matched, 0 missed.** No defect.

Also recorded: `#2.Option.A.(1)` and `#5..Opt.A.(1)` tokenize to `'option'` and `'opt'`,
so logically-related rows can fail strict prefix matching — almost certainly *why* the
header-stack fallback exists.

---

## Python conventions

- **Ruff** for lint and format, explicit rule selection. Run `ruff format` as a **separate
  formatting-only commit**.
- **mypy strict** on `domain`, `inference`, `storage`, `inputs`; lenient elsewhere;
  `ignore_missing_imports` for `fitz`, `cv2`, `webview`.
- **`logging` replaces all 19 `print()` calls.** Library modules take module loggers and
  never configure handlers. The three silent `except Exception:` sites become
  `logger.exception(...)`.
- **`ScoutmbError` hierarchy** replaces raw `RuntimeError` (five in `bootstrap/`).
- **Lazy heavyweight imports** — `openpyxl` inside `load_xlsx`.
- **Shared loader helpers** so a new alias is added in one place.
- Protocols over ABCs, frozen slotted dataclasses, `pathlib`, `importlib.resources`.

## Continuous integration

CI is **staged across phases** — a workflow defined up front cannot pass. `pytest --cov`
exits non-zero with no tests collected, and a wheel-build job cannot build `src/scoutmb`
before it exists.

| Job | Added in | Runs on | Contents |
| --- | --- | --- | --- |
| `lint` | Phase 0 | ubuntu | ruff check, ruff format --check |
| `types` | Phase 0 | ubuntu | mypy on whatever exists |
| `test` | Phase 1 | ubuntu, windows | pytest, `pytest-socket`, branch coverage |
| `coverage-floors` | Phase 3 | ubuntu | per-area `coverage report --fail-under` |
| `lock` | Phase 0 | ubuntu | `uv.lock` matches `pyproject.toml`; `requirements.txt` matches the lock |
| `build` | Phase 2 | ubuntu | build wheel; verify packaged templates and static assets |
| `wheel-install` | Phase 2 | windows, macos | install the wheel into a standalone runtime; resolve package resources |
| `playwright` | Phase 5 | ubuntu | tier-3 tests against the local fake site; adapter changes + nightly |
| `launcher` | Phase 8 | windows (+ macos Phase 9) | PyInstaller build smoke test |
| `installer` | Phase 8 | windows, `workflow_dispatch` | real bootstrap, `SCOUTMB_FORCE_CHROMIUM_FALLBACK=1` (~10 min) |

## Design decisions

| Decision | Rationale |
| --- | --- |
| Keep `errors.py` hierarchy | Designed upfront by explicit choice |
| Keep `ProgressSink` with multiple implementations | Required by planned future work, not speculative |
| Keep application self-update | Explicit product requirement; safety supplied by integrity verification, A/B environments, and health-gated rollback |
| Launcher does **not** self-update | `bootstrap/` is frozen into the exe and excluded from the wheel; claiming otherwise would be false |
| Per-collaborator injection, not one `RunContext` | Clock, IDs, jitter, sleep, and progress are unrelated concerns; bundling them is a service bag |
| Wire-boundary `Mapping[str, Any]`, not `TypedDict` | The upstream API is not ours; typing it encodes an unenforceable assumption |
| Drift severity policy, not blanket continue | Continuing past a missing completion flag produces confidently wrong results |
| No Jinja2 | One substitution point; brace-escaping 206 CSS + 278 JS lines is a corruption risk, evidenced at `:886-893` |
| Pre-built wheel, not `pip install -e .` | Needs no build backend on the user's machine; verified by `wheel-install` CI |
| `requirements.txt` retained, generated and pinned | Still the installer's pip input and gates `compute_requirements_hash` |
| Copy-only legacy migration | One install exists; deletion buys nothing and risks everything |
| Technical layout | Deliberate deviation from CUPID's domain-based principle, appropriate at this size |

## Phases

Each phase leaves the app runnable and the suite green.

| # | Work | Exit criterion |
| --- | --- | --- |
| **0** | Tooling only, no source changes: pyproject, uv.lock, ruff, mypy, pre-commit, `lint`/`types`/`lock` CI. Separate `ruff format` commit. Note the in-flight refactor in `CLAUDE.md` | Green CI on untouched source; **no test or build job yet** |
| **1** | Characterize in place against **flat** modules, including `process_scout` via monkeypatched module functions. Build `tests/factories/`. Scrubber and `verify_corpus.py` via TDD. Add `test` CI job | Safety net green; **zero app code moved** |
| **2** | **Attendee identity fix** (behavior change, TDD, own phase) + atomic output writes. Add `build` / `wheel-install` CI | Same-named attendees provably isolated; goldens regenerated against corrected identity |
| **3** | Data-root resolution (`UiSettings`, `SCOUTMB_DATA_DIR`) + legacy `app/` → `data/` migration, **before** any UI move | Pre-existing `data/scouts.csv` survives a full reinstall; migration idempotent |
| **4** | Package skeleton + root shims. Mechanical move: `domain` → `storage` → `inference` → `inputs` → `scrape` → `reporting` → `emails` → `pdf` → `cli` → `ui`. Delete and rebuild the code-review-graph | Phase 1 tests pass at new import paths |
| **5** | Extract the template (golden written **first**). Split `process_scout` at `SchedulePort` with `payloads.py` drift policy. Add `playwright` CI job | Contract suite green on all ports; tier-3 job green |
| **6** | Typed config + per-collaborator injection. *Highest risk of a silently flipped default* | Test asserting `config_from_args(parse([minimal argv]))` equals a hand-written `ScrapeConfig` field by field, including the `scout_delay_ms=None` sentinel and the `no_html` inversion |
| **7** | Logging + unified `ProgressSink` | Terminal format signed off; `[i/n] name` line kept verbatim |
| **8** | UI app factory, `JobRegistry`, routers, the four UI defects, **and the `app.js` half of the report-opening change** | Routes tested under `TestClient`; frontend opens the report via a real anchor |
| **9** | Bootstrap rebuild: `manifest.py`, platform modules, standalone runtime, A/B environments, release manifest + SHA-256 verification, health-gated rollback, browser revalidation | Windows launcher end to end, including forced-checksum-failure and forced-rollback tests |
| **10** | macOS: platform implementations, CI matrix, notarization | A macOS launcher that runs |
| **11** | Cleanup: dead code, raise the global floor to 85%, rewrite `CLAUDE.md` / `README.md` / `AGENTS.md` / `GEMINI.md`, final graph rebuild. **Shims retained** until the following release | Docs match reality |

Phases 0–1 and 9 are independently reviewable; 2–8 must land in order. Phases 0–8
(application) and 9–10 (launcher) are separable efforts; **phase 8 is a clean stopping
point.**

## Verification

- `ruff check . && ruff format --check . && mypy src && pytest --cov` green at every phase.
- Legacy invocations still work via shims; `troop349 extract-pdf` / `troop349 download`
  produce **byte-identical CSV headers**.
- `troop349 ui`, then exercise upload → extract → download → open report → generate emails.
- Diff generated `report.html` against a pre-refactor capture with a frozen clock.
- Installer on macOS: `SCOUTMB_BOOTSTRAP_ROOT=<tmp> python -m bootstrap.main`; assert the
  package imports *and* a pre-existing `data/scouts.csv` survives.
- **Tag the pre-refactor commit** so it can be bisected from a Windows machine.
- **Before Phase 9 ships, snapshot the one live installation's `app/` directory** to
  external storage. The migration is copy-only and tested, but one irreplaceable dataset
  justifies a manual backup.

## Risks

| Risk | Mitigation |
| --- | --- |
| **Hazards 1–3 destroy the live install's data** | Explicit `data_root`; copy-only migration in Phase 3 **before** the UI move; survival regression test; manual backup before Phase 9 |
| **Same-named attendees corrupt each other's records** | Fixed in Phase 2, before any code moves, with its own failing tests |
| **Stale `.code-review-graph/graph.db`** — `CLAUDE.md` instructs agents to trust it *before* reading files, so after the move an agent answers confidently about a codebase that no longer exists | Delete at the start of Phase 4, rebuild after **every** phase; note the refactor in `CLAUDE.md` in Phase 0. Check `.gemini/`, `.remember/`, `.kiro/`, `.qoder/` |
| Corrupt or substituted update artifact | SHA-256 against a signed manifest, size and name allowlists, atomic download, downgrade prevention |
| Update leaves a broken environment | A/B environments, candidate smoke test, atomic switch, health acknowledgement, retained known-good |
| Playwright/browser version skew | Mandatory revalidation when the resolved version changes |
| CSV column order derives from dataclass field order | Exact header rows pinned in Phase 1 |
| Template reassembly shifts bytes | Golden written before extraction |
| Scrubber leaks real data | Self-verifying over all artifacts and filenames; own TDD suite; conftest tripwire; `/raw_data/` gitignored |
| Upstream API changes shape | Severity-tiered anti-corruption layer; property-based tests assert no crash on arbitrary payloads |
| Windows installer untestable on macOS | `workflow_dispatch` real-bootstrap job; tagged pre-refactor commit |
| 3.14 dev vs 3.12 shipped | `requires-python`, ruff `target-version`, mypy `--python-version`, 3.12 primary in CI; pinned `requirements.txt` |
| Root shims become permanent | `FutureWarning` (visible, unlike `DeprecationWarning`); removed one release after introduction |
| Adult filtering runs twice (`pdf:23`, `cli:212`) | Unify the constant, **keep both call sites** — inputs skipping the PDF stage still need the second |
| macOS Gatekeeper blocks unsigned launcher | Apple Developer Program is a purchasing decision tracked outside this plan |
| Scope creep from discovered bugs | Characterization tests pin bugs; fixes are separate changes with their own failing tests |

## Open questions

None blocking. The two suspect `requirement_path` behaviors are settled by direct tests of
tree construction in Phase 4 rather than by advance decision, and any resulting fix is
scheduled separately per the risk table.
