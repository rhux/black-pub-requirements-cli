# Restructure `black-pub-requirements-cli` into the `scoutmb` package

> **SUPERSEDED (2026-07-21).** This plan has been merged into
> [`docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`](superpowers/specs/2026-07-21-scoutmb-refactor-design.md),
> which is the authoritative spec. Retained as a record — its hazard analysis, coverage
> calibration, and phase structure were carried over largely intact. Do not implement
> from this document.

> Status: **proposed** — awaiting review. Nothing in this document has been implemented.

## Context

This repo started as a quick script and accreted into a real application: two CLI pipelines
(`pdf_to_scouts.py` 579 lines, `scout_schedule_cli.py` 1798 lines), a FastAPI web UI (`ui/`),
a desktop launcher (`run_app.py`), and a 14-module self-bootstrapping Windows installer
(`bootstrap/`). It has **no package, no tests, no CI, no linter, no type checker, and no
`pyproject.toml`** — nothing pins current behavior.

The structural problems are concrete, not stylistic:

- `write_html_report` is 659 lines, 618 of which are an embedded HTML/CSS/JS string.
- `process_scout` (142 lines) mixes browser control, retry policy, dedup, JSON→record mapping,
  and filesystem writes — so none of it is testable without a live Chromium.
- `argparse.Namespace` is threaded into the scraping layer, forcing `ui/server.py:188-201` to
  hand-build a fake Namespace with 12 fields and `async_main` to use defensive
  `getattr(args, "email_report", False)`.
- The requirement-inference logic — the most intricate code here — mutates dicts in place and
  keys bookkeeping on `id(item)`, and is invoked twice per run through two different entry paths.
- `print()` is the logging system; the UI receives progress through a separate unrelated channel.

Goal: a `src/`-layout package with typed boundaries, an injectable transport seam, a real test
suite, and standard Python tooling — without breaking the Windows installer that non-technical
users depend on.

## Decisions (settled with the user)

| | |
|---|---|
| Package name | `scoutmb` (matches existing `SCOUTMB_*` env vars, `ScoutingMeritBadges` install dir) |
| Console command | `troop349` — `[project.scripts] troop349 = "scoutmb.cli.app:main"` |
| CLI shape | Unified subcommands (`extract-pdf`, `download`, `ui`) + back-compat root shims |
| Scope | Everything: CLI core, `ui/`, and `bootstrap/` |
| Tooling | pyproject (hatchling), ruff, mypy, pytest+coverage, pre-commit, GitHub Actions |
| Depth | Full internal refactor, not just file relocation |
| Python | `requires-python = ">=3.12"` — 3.12 is what ships to Windows; dev venv is 3.14 |

---

## ⚠️ Two coupled hazards — read before Phase 2

These are verified, not hypothetical, and together they can destroy user data.

**1. `ui/server.py:24` — `REPO_ROOT = Path(__file__).resolve().parent.parent`**

Today `__file__` is `app_dir/ui/server.py`, so `REPO_ROOT` resolves to `app_dir`, and
`SCOUTS_CSV`/`PDF_UPLOADS_DIR`/`RUNS_DIR` (lines 35-37) land correctly beside the app.
After the move, `__file__` becomes `app_dir/scoutmb/ui/app.py` and `.parent.parent` silently
becomes `app_dir/scoutmb` — **user data would relocate inside the package directory.**

Fix: `UiSettings` takes an explicit `data_root`, defaulting to
`Path(os.environ.get("SCOUTMB_DATA_DIR") or Path.cwd())`. `bootstrap/main.py:55` already sets
`cwd=app_dir`. Never derive data paths from `__file__` again.

**2. `bootstrap/source_sync.py` gains an `rmtree`**

Its docstring promises *"never a directory wipe — scouts.csv, pdf-uploads/, and runs/ live in the
same app\ folder as user data and must survive untouched."* Switching from a file allowlist to
`copytree` requires `rmtree(app_dir/"scoutmb")` first, so modules deleted upstream don't linger
forever (today they do). That is safe **only because the package dir holds no user data** — which
is exactly what hazard #1 would break.

**Fix #1 and #2 in the same phase, and add the regression test described in Phase 8.**

---

## Target layout

```
src/scoutmb/
  __init__.py  __main__.py  errors.py  config.py  progress.py  logging_setup.py

  domain/      models.py (ScoutInput/ClassRecord/RequirementRecord/ScoutResult, lines 37-85)
               enums.py  (RequirementStatus StrEnum; SECTION_HEADER_TYPE_ID = "3")
               text.py   (clean_html_description 328)
               registrants.py (ADULT_REGISTRANT_TYPES — kills the pdf:23 / cli:212 duplicate)

  inference/   PURE — no I/O, no dicts crossing the boundary. Takes and returns dataclasses.
               numbering.py (CHOICE_COUNT_WORDS 610, requirement_path 626, choice_count 649)
               tree.py      (grouping + parent linking + header stack, 679-716)
               status.py    (the `calculate` closure 720-763, de-nested)
               missing.py   (build_missing_requirements 771-843, keyed on node index not id())

  inputs/      headers.py (norm_header 181, first_matching_key 185, alias lists — kills the
               three literal duplicates at 237-239 / 258-266 / 294-296)
               loaders.py (load_xlsx/csv/json/text 224-313)   pipeline.py (load_inputs 193)

  scrape/      payloads.py       PURE mapping — truthy 337, days_from_class_name 341,
                                 form_values 316, dedupe 494-506, record mapping 507-522 + 565-582
               ports.py          SchedulePort Protocol + ScheduleFetch
               playwright_port.py  navigate_and_trigger_schedule 368, post_requirement 417,
                                 discover_name 347, context/route lifecycle 456-473
               retry.py  raw_store.py  runner.py (process_scout, run_batch 1709-1782)

  reporting/   view_model.py  html.py  writers.py (write_outputs 1632)  summary.py
               templates/report.{html,css,js}   ← the 618-line string, split three ways

  emails/      render.py  export.py  templates/email.html   (NOT `email/` — stdlib collision)
  pdf/         discovery.py  identity.py  qr.py  extract.py  pipeline.py  export.py
  storage/     csvio.py  jsonio.py  naming.py (safe_slug 595)   (NOT `io/`)
  cli/         app.py  args_scrape.py  args_extract.py  args_ui.py  console.py
  ui/          settings.py  app.py (create_app factory)  jobs.py  routes/  static/  desktop.py
```

**No junk drawers.** Rule: every module is named for a *subject* ("requirement numbering", "CSV
writer"), never a *role*. A pre-commit hook rejects `utils.py`/`helpers.py`/`common.py` under `src/`.
Placement follows consumers: `clean_html_description` has three callers across layers → `domain/text.py`;
`truthy` has one, the payload mapper → `scrape/payloads.py`; `safe_slug` makes filenames → `storage/naming.py`.

`bootstrap/` **stays at the repo root**, outside the package — it's Windows-only, stdlib-only,
frozen separately, and deliberately imports no app code. Add `[tool.hatch.build] exclude = ["bootstrap"]`.

---

## Key design decisions

### The 618-line template → package data, three files, `str.replace()`

The template uses **exactly one substitution** (`template.replace("__REPORT_DATA__", ...)` at 1627).
No f-string, no `.format()`. So **no Jinja2** — it would add a runtime dependency that changes
`marker.compute_requirements_hash` and forces every existing Windows install to reprovision, and it
would require escaping every `{`/`}` across 206 lines of CSS and 278 lines of JS full of `${...}`
template literals. That mechanical edit is a real corruption risk; the existing doubled-brace email
template (888-893) already demonstrates the failure mode.

Split into `templates/report.{html,css,js}`, loaded via `importlib.resources.files(...)` with an
`lru_cache`. **Substitute in the order CSS → JS → DATA, always DATA last** — scout data can contain
the literal string `__REPORT_JS__` and survives JSON escaping, so data-last makes injection
impossible. Assert no `__REPORT_` token remains in the output; add a test for a scout named
`__REPORT_JS__`. Output stays a single self-contained HTML file.

The email template moves to `emails/templates/email.html`, brace-doubling removed.

PyInstaller survival is free: `build.spec` freezes **only** `bootstrap/entry.py` — app source rides
as `datas` and is copied to disk, then run by the embeddable Python. The app never executes frozen,
so the usual `importlib.resources`-under-PyInstaller hazard doesn't apply.

Same mechanism for `ui/static/`, but `create_app` must resolve it via `importlib.resources`, not
`Path(__file__).parent` (server.py:38), and mount it after verifying existence rather than at
import time (338-339 currently raises if the dir is absent).

### Typed config replaces `Namespace` threading

Frozen slotted dataclasses in `config.py`: `BrowserOptions`, `PacingOptions`, `InputOptions`,
`ReportOptions`, composed into `ScrapeConfig` (and `ExtractConfig` for the PDF side). Plus a
`RunContext` carrying the injectable seams — `clock` (replaces `time.strftime`/`datetime.now()` at
1644-1645), `rng` (replaces `random.uniform` at 1773), `progress`.

Magic numbers currently inline become named fields: retry attempts (`range(1,4)` @535), backoff
(`500 * attempt` @548), jitter (`(0.5, 2.0)` @1773).

`argparse` populates it in `cli/args_scrape.py`; the `Namespace` never leaves that module.
Note `scout_schedule_cli.parse_args()` (line 88) currently takes **no `argv`** — adding it is a
prerequisite for testing any of this.

`ui/server.py:188-201` collapses to a `ScrapeConfig(...)` construction. **This is the point:** new
options can no longer silently default to `False` on the UI path, so `getattr(args, "email_report",
False)` (1704) and `getattr(args, "channel", None)` (1740) both get deleted.

`--quiet` leaves the config entirely and becomes global `-q`/`-v` verbosity, which fixes the
inconsistency at `pdf_to_scouts.py:571` (prints unconditionally despite `--quiet`) by construction.

### `process_scout` splits at a `SchedulePort` Protocol

```python
class SchedulePort(Protocol):
    async def open_scout(self, qr_url: str, fallback_name: str) -> ScheduleFetch: ...
    async def fetch_requirements(self, attendee_id: str, class_p4_id: str) -> Mapping[str, Any]: ...
    async def aclose(self) -> None: ...
```

Everything Playwright hides behind it. Above it, `scrape/payloads.py` is pure and synchronous:
`dedupe_schedule_rows`, `class_records_from_schedule`, `requirement_records_from_payload`. A test
loads `tests/fixtures/payloads/schedule_ok.json` and asserts a `list[ClassRecord]` — no browser,
no async, no network. **This single extraction makes ~80% of the scraping logic testable**, and
covers the field-name mapping and `None`-coalescing where the real bugs live.

Retry moves to `retry.py` with an injected `sleep` (today `page.wait_for_timeout` both sleeps *and*
is bound to the page, so retry tests would take seconds). Raw-payload writes move to a
`RawPayloadStore` with a `NullRawStore` for tests. A `FakeSchedulePort` over fixture JSON then
exercises the full per-scout flow including error accumulation and the exact error strings.

---

## Phases

Each phase leaves the app runnable and the suite green.

**Phase 0 — Tooling, no source changes.** pyproject, ruff, mypy (`--python-version 3.12`,
`ignore_missing_imports` for `fitz`/`cv2`/`webview`), pytest (`markers = ["playwright"]`,
`addopts = "-m 'not playwright'"`), pre-commit, CI (ubuntu + windows, **3.12 primary**).
Run `ruff format` as a **separate formatting-only commit** so it never mixes with logic in a diff.

**Phase 1 — Characterize the crown jewels in place.** Tests against the *flat* modules before
anything moves. Pure "characterize first" is the textbook answer but is only half-right here: most
high-value logic is currently *unreachable* from a test (`parse_args` takes no `argv`,
`process_scout` takes a `Browser`, `write_html_report` reads the wall clock). So Phase 1 pins
everything already pinnable — the inference logic (610-843), pure PDF helpers (172-200, 286-294),
`clean_html_description`, `safe_slug`, `truthy`, the exact CSV header rows, and email goldens — and
every later phase pins what its own new seam exposes, before relying on it. Build
`tests/factories/` here. Imports get rewritten in Phase 2; the *assertions* are the asset.

**Phase 2 — Package skeleton + root shims.** Mechanical move, zero edits beyond imports. Order:
`domain` → `storage` → `inference` → `inputs` → `scrape` → `reporting` → `emails` → `pdf` → `cli`
→ `ui`. Shims re-export so `ui/server.py`'s bare `import scout_schedule_cli` survives this phase.
*Risk: `write_csv` derives fieldnames from `__dataclass_fields__` order (1670, 1675) — preserved
only if field order is. Pinned by the Phase-1 header test.*

**Phase 3 — Extract the template.** Write the golden-report test *first* against the current inline
string, then extract byte-identically and re-run. Un-double the email braces. *Risk: reassembly
order and trailing newlines can shift bytes; the golden test is the whole defense.*

**Phase 4 — Typed config.** *Highest risk of a silently flipped default.* Mitigation: a test
asserting `config_from_args(parse([minimal argv]))` equals a hand-written expected `ScrapeConfig`
field by field — including the `scout_delay_ms=None` sentinel and the `no_html`→`generate_html`
inversion.

**Phase 5 — Split `process_scout`.** `payloads.py` first, pinned by a `schedule_dupes.json` fixture
written before the extraction (the "prefer the completed duplicate" rule at 502-505 is subtle).
Preserve 3 attempts at 500/1000/1500 ms exactly, and assert it.

**Phase 6 — Logging + unified progress.** One `ProgressSink`: `LoggingProgressSink` for CLI,
`QueueProgressSink` for the UI, collapsing the two unrelated update channels. *Low behavior risk,
high user-visible-output risk — every terminal line changes format. Get sign-off on the format;
keep the `[i/n] name` progress line verbatim.*

**Phase 7 — UI app factory.** `create_app(settings)`, `JobRegistry` replacing the module globals
(45-47), routers. Hazard #1 lands here. Also fix and **list in the PR**: `stale.unlink()` needs an
`is_file()` guard (114-116, currently `IsADirectoryError` on a subdir); `os.startfile` (334) is
Windows-only and `AttributeError`s elsewhere; `webbrowser.open` server-side (301) → return the URL
and let the client open it (*behavior change* — equivalent under pywebview, strictly more correct
under `--browser`); unguarded `json.loads` at 206/296/311.

**Phase 8 — Bootstrap rewiring.** *Highest risk, untestable locally.* New `bootstrap/manifest.py`
as the single source of truth, imported by both `source_sync.py` and `build.spec` (spec files
execute as Python), killing the two duplicated manifests. `hiddenimports` →
`collect_submodules("bootstrap")`. `main.py:54` → `Popen([pythonw, "-m", "scoutmb", "ui"])`.
`python_env._patch_pth_file` needs no change (only its comment). **Keep `requirements.txt` as the
installer's pip input** — do not switch to `pip install -e .`, which needs a build backend on a
machine you cannot debug. Add `"scoutmb"` to `config.SMOKE_TEST_IMPORTS` so the smoke test
genuinely verifies the sync produced an importable app.

**Phase 9 — Cleanup.** Dead code; mypy `strict` on `domain`/`inference`/`storage`/`inputs`; raise
the coverage gate; rewrite `CLAUDE.md`, `README.md`, `AGENTS.md`, `GEMINI.md` (all four document
the flat layout); rebuild the code-review-graph.

Phases 0-1 and 8 are independently reviewable. Phases 2-7 must land in order.

---

## Testing

**No fixture data exists and none can be borrowed** — QR URLs are bearer tokens for real minors'
data, and every input path is gitignored. All fixtures are synthesized. The payload shapes are
fully recoverable from the mapping code at 508-522 and 565-582.

Use invented names/IDs and `https://scoutingevent.com/mobile/?t=TESTTOKEN0001`. Add a
session-scoped conftest tripwire failing if any file under `tests/fixtures/` contains a
`scoutingevent.com/mobile/` URL whose token doesn't start with `TESTTOKEN`, plus a pre-commit hook
rejecting `*.pdf` at the repo root.

**Fixture PDFs are generated, not committed** — commit the *builder*, not a binary blob. `segno`
(pure Python, test-only dependency group, never reaches `requirements.txt`) makes the QR PNG;
PyMuPDF `insert_image` builds the page with the label/value layout `value_after_label` (176-186)
expects. For honest coverage of the *rendered* fallback path (365-380), a second variant draws the
QR as vector content so `decode_embedded_qr` returns empty and the fallback actually runs.

**Playwright, three tiers:** (1) `FakeSchedulePort` covers runner/retry/dedup/mapping — always
runs, no browser; (2) `is_schedule_response` and `form_values` only read attributes, so
`SimpleNamespace` suffices; (3) `@pytest.mark.playwright` against a local fake ScoutingEvent,
deselected by default and **not in CI** — the only way to catch a stale selector in the 384-397
fallback chain. **Do not** mock `Page`/`Response` with `unittest.mock`; the surface used is deep
enough that the mock becomes the thing under test.

`bootstrap/webview2.py:12` has a module-level `import winreg` and evaluates `winreg.HKEY_*` at
import — unimportable on macOS. Store hive *names* as strings, move the import into the function,
`getattr` there; then the module imports everywhere and only the registry test is skipped.
`bootstrap/paths.py:31` does `os.environ["LOCALAPPDATA"]` — a bare `KeyError` on macOS; use `.get()`
with a diagnosable error.

**Coverage gate: 75% global**, with the weight in per-package floors — `inference/` and
`scrape/payloads.py` 95%; `inputs`/`emails`/`storage`/`cli` 90%; `pdf` 80%; `ui` 70%; `bootstrap`
60%. **`scrape/playwright_port.py` is omitted from the gate entirely** — it's an I/O adapter
covered only by tier 3, and counting it just incentivizes fake tests. Chasing 90% global means
mocking Playwright and PyInstaller: negative value.

**Do not test:** `bootstrap/downloader.py` network fetches, `bootstrap/ui.py` (tkinter),
`install_webview2` (runs an .exe), `install_chromium_fallback` (20-minute download), `desktop.py`'s
webview launch, `build.spec`, `os.startfile`, the report's client-side JS, the CSS.

## Verification

- `ruff check . && ruff format --check . && mypy src && pytest --cov` — green at every phase.
- **End-to-end against real data before merging Phase 2**, once. Removing `write_csv`'s
  `extrasaction="ignore"` (599) is correct but converts a currently-silent field mismatch into a
  crash — this is the one place the fix surfaces a latent bug loudly.
- `python pdf_to_scouts.py <pdf> --output scouts.csv --strict` and
  `python scout_schedule_cli.py --input scouts.csv --output out` must still work via the shims;
  `troop349 extract-pdf` / `troop349 download` must produce byte-identical CSV headers.
- `troop349 ui`, then exercise upload → extract → download → open report → generate emails.
- Diff the generated `report.html` against a pre-refactor capture (with a frozen clock) — the
  golden test automates this, but eyeball it once.
- Installer: `SCOUTMB_BOOTSTRAP_ROOT=<tmp> python -m bootstrap.main` runs `sync_app_source` **on
  macOS**. Assert `app_dir/scoutmb/reporting/templates/report.html` exists *and* that a
  pre-existing `app_dir/scouts.csv` survives the new `rmtree`. Add a `windows-latest` CI job that
  builds the exe (fast, catches spec breakage) and a `workflow_dispatch` job running the real
  bootstrap with `SCOUTMB_FORCE_CHROMIUM_FALLBACK=1` (~10 min, the only true installer test).

## Risks

1. **Windows installer** — nothing in Phases 0-7 touches it; Phase 8 rewrites it wholesale and you
   cannot exercise it on macOS. Mitigated by the three checks above. Tag the pre-refactor commit so
   it can be bisected from a Windows machine.
2. **`.code-review-graph/graph.db` indexes current paths**, and `CLAUDE.md` instructs agents to
   trust it *before* reading files. After Phase 2 every node is stale — an agent obeying `CLAUDE.md`
   will answer confidently about a codebase that no longer exists, which is worse than no graph.
   Delete it at the start of Phase 2, rebuild after *every* phase, and note the in-flight refactor
   in `CLAUDE.md` during Phase 0. Check `.kiro/`, `.qoder/`, `.gemini/`, `.remember/` for the same.
3. **3.14 dev vs 3.12 shipped** — `typing.TypeIs`, `warnings.deprecated`, and any 3.13/3.14 stdlib
   addition ship broken to a user with no diagnostic path. `requires-python = ">=3.12"`, ruff
   `target-version = "py312"`, mypy `--python-version 3.12`, 3.12 primary in CI. Subtler: the
   version *ranges* in `requirements.txt` resolve to different PyMuPDF/opencv builds per Python
   version, so a bug can be dependency-shaped and irreproducible locally — **pin exact versions in
   `requirements.txt`** (it's the installer's input and gates `compute_requirements_hash`; it should
   be reproducible) and keep ranges in `pyproject.toml`. Consider recreating `.venv` on 3.12.
4. **The double `annotate_requirement_statuses` call** (784 and 979) feeds differently-shaped input
   — nested `scouts.json` dicts vs `asdict(RequirementRecord)`. Unifying onto one typed function
   could change results if the shapes diverge (e.g. `requirement_type_id` as int vs str). Pin
   **both** call sites separately in Phase 1.
5. **Adult filtering runs twice** (pdf:23 then cli:212). Unify the constant but keep both call
   sites — inputs that skipped the PDF stage still need the second.
6. **Root shims become permanent** unless they emit a `DeprecationWarning` naming `troop349`.
   Otherwise the flat layout lives forever in muscle memory and in every doc a future agent reads.
