# ScoutMB Software Foundation Design (Descoped)

**Date:** 2026-07-21 (descoped 2026-07-22)
**Status:** Authoritative design. Scope trimmed by explicit owner decisions on 2026-07-22.
**Reviewed by:** Claude (self-review), OpenAI Codex (independent, against the codebase)
**North star:** A structure that makes future features easy to add and change, following
best practices. Every scope decision below was judged against that goal.

## How this document was descoped

The prior revision specified a production-grade, enterprise-scale foundation (36 locked
decisions). The owner reviewed each area and chose keep / trim / postpone. This document
reflects those choices. The Decision Appendix records every D-number with its current
status, so nothing is silently dropped — postponed work is labelled **POSTPONED (vNext)**
and can be reopened without re-deriving it.

## Problem

The repository began as a quick script and accreted into a real application: two CLI
pipelines, a FastAPI web UI, a desktop launcher, and a 14-module self-bootstrapping
Windows installer.

| Component | Lines (`wc -l`) | Role |
| --- | --- | --- |
| `scout_schedule_cli.py` | 1,889 | Stage 2: scrape, infer, report |
| `pdf_to_scouts.py` | 600 | Stage 1: PDF to CSV |
| `ui/server.py` | 391 | Local FastAPI app |
| `ui/static/app.js` | 328 | Frontend |
| `run_app.py` | 89 | Native-window entry point |
| `bootstrap/` | 14 modules | Windows self-installing launcher |

Slice 1a established the Python project foundation: `pyproject.toml`, `uv.lock`, CI,
ruff, mypy, pytest, offline enforcement, privacy scanning, synthetic factories, and the
first focused characterization tests now exist. It also fixed stable attendee identity,
atomic single-file publication, data-root resolution, and copy-only migration in place.
The legacy application is still primarily implemented by the flat modules above; Slice 1b
must complete their behavior contract before Slice 2 moves them into the package.

Source references in this specification are symbol based. Plans may include a line number
only as a navigation aid and must pair it with the owning symbol because Slice 1a and later
slices legitimately move lines.

### Remaining correctness and behavior risks in the legacy code

1. **`build_missing_requirements` keys bookkeeping on `id(item)`.** This is not a live
   failure while the dictionaries remain referenced by `annotated`, but it cannot survive
   the move to frozen dataclasses. The inference decomposition must re-express the ancestor
   walk over explicit node indices.
2. **Unreferenced background tasks.** `ui.server.start_pdf_extract` and
   `ui.server.start_schedule_download` create worker tasks without retaining the result;
   CPython holds only weak references, so a long job can be collected mid-execution.
3. **Four UI defects.** The PDF-upload cleanup unlinks every directory entry without an
   `is_file()` guard; `open_emails_folder` calls Windows-only `os.startfile`;
   `open_report` launches a browser from the server process; and persisted JSON reads in
   the run/report/email routes are not consistently guarded.
4. **Sensitive adapter fields cross outward-facing surfaces.** Current JSON/CSV/HTML/email,
   stdout, and progress/SSE observations can contain upstream attendee IDs or QR material.
   Slice 1b characterizes each surface with synthetic sentinels; Slice 2 owns the assigned
   privacy changes.

`pdf_to_scouts --quiet` intentionally suppresses progress and aggregate summaries while
still printing errors and the final output path. That matches the CLI help contract and is
not a defect.

### Structural defects

1. `scout_schedule_cli.py` has no internal boundaries: argparse, four input loaders,
   Playwright control, AJAX scraping, inference, email rendering, a 658-line embedded
   HTML string, and six output writers in one module.
2. `process_scout` fuses browser control, retry, dedup, JSON→record mapping,
   and filesystem writes.
3. `argparse.Namespace` is threaded into the scraping layer; `ui.server` hand-builds one
   while `async_main` and collaborators defend with `getattr`.
4. `ui.server` and `bootstrap.python_env` still contain import-path manipulation.
5. Heavyweight optional dependencies are imported at legacy module scope.
6. `scout_schedule_cli.parse_args` takes no explicit `argv`.
7. `print()` remains the logging system and broad exception handling remains in adapter
   paths.
8. Wall-clock time, random attendee pacing, and UUID creation remain embedded in business
   and interface flows.
9. Untyped external payloads flow through as `dict[str, Any]`.
10. `DEFAULT_ADULT_TYPES` and header aliases remain duplicated.

### Claims that must not be reintroduced

Inspection disproved three earlier assertions. Recorded so they do not return:

- Inference does **not** mutate caller-owned dictionaries —
  `annotate_requirement_statuses` copies every input.
- The two inference consumers do **not** receive differently-shaped input — both pass
  `asdict(RequirementRecord)` and acquisition coerces `requirement_type_id` to `str`.
- `write_html_report` does **not** read the wall clock — it takes both timestamps as
  parameters.

## What already exists

| Area | Source anchors | Behavior preserved or isolated |
| --- | --- | --- |
| Schedule acquisition + reports | `scout_schedule_cli.py`: `process_scout`, `annotate_requirement_statuses`, `build_missing_requirements`, `write_outputs`, `async_main` | Input formats, retries, inference, CSV/JSON/HTML/email outputs, CLI defaults |
| PDF extraction | `pdf_to_scouts.py`: `expand_pdf_inputs`, `decode_embedded_qr`, `extract_pdf`, `write_attendees_csv` | PDF discovery, QR decode, 7-column attendee CSV contract, errors |
| Local web app | `ui/server.py`: `start_pdf_extract`, `start_schedule_download`, `operation_events`, `open_report` | Background ops, status/SSE APIs, report launch, pause/resume |
| Desktop entry | `run_app.py`: `free_port`, `start_server`, `wait_until_ready`, `main` | Local server startup, desktop window |
| Windows bootstrap | `bootstrap/main.py`, `bootstrap/paths.py`, `bootstrap/source_sync.py` | Install ownership, source copy, Python/browser setup, launch |
| Download + env setup | `bootstrap/downloader.py`, `bootstrap/python_env.py`, `bootstrap/browser_setup.py`, `bootstrap/marker.py` | Downloads, extraction, dependency install, browser selection, readiness marker |

The installer downloads Python, Playwright browsers, and OpenCV **during bootstrap** —
it does not bundle them. That download-on-bootstrap model is intentional and retained;
this design formalizes those downloads as explicit hash-bound capability payloads.

`ui/server.py` mutates `sys.path`; that is removed once the package exists. No
first-party module may add or rewrite import search paths.

## Goals

- A `src/` package with typed boundaries and clean seams, so new features slot in without
  touching unrelated code — the primary goal.
- Correct attendee identity, so two same-named Scouts cannot corrupt each other's data.
- A real test suite that keeps future changes safe: characterization + parity + offline
  enforcement + privacy tripwires.
- Reproducible, installable distribution (wheel/sdist, `uv.lock`).
- Safe migration and transactional install/rollback that protect the one live install.

## NOT in scope

- Rebuilding or modifying `scoutingevent.com`.
- A cloud backend, multi-user server, or remote telemetry collector.
- Automatic telemetry upload (Phase D ships only an offline no-op seam + future protocol).
- Coupling to a specific release-hosting vendor.
- Code signing / notarization (deferred; internal-only trust model documented).

## POSTPONED to a later version (vNext)

Explicitly deferred by owner decision. Each is reopenable from its D-number.

- **Auto-update discovery** — the controlled-HTTPS release channel and daily update check
  (D17 remainder). Transactional install/rollback is kept; discovery is manual.
- **OS-backed single-instance ownership** — authenticated rendezvous, focus activation,
  PID-reuse/antivirus matrices (D29). The existing mtime lock is retained.
- **Scraper deadline budgets + URL allowlist** (D22 remainder). Circuit breaker and
  resumable checkpoints are kept.
- **Per-payload CycloneDX SBOMs + exception-expiry policy** (D36 remainder). `uv audit`
  and a license gate are kept.
- **Full loopback web hardening** — CSRF, CSP, per-launch auth, Host/Origin (D30
  remainder). Structural web work (factory, job registry, loopback bind, UI-bug fixes)
  is kept.
- **Per-launch split-brain monitoring** (D26 remainder). A one-time migration warning +
  old-root marker is kept.
- **Timed data retention + backup/staged-restore** (D31 remainder). Current-user
  permissions + explicit deletion are kept.
- **Multi-file atomic report *generations*** (B8/D11 multi-file layer). Atomic
  single-file writes are kept.

## Constraints and invariants

- **Python 3.12 target.** `requires-python = ">=3.12"`, ruff `target-version = "py312"`,
  mypy `--python-version 3.12`, 3.12 primary in CI. Dev venv is 3.14.
- **No real Scout data in the repository, ever.** `/raw_data/` is gitignored. Committed
  fixtures are fully synthetic.
- **Default tests never contact `scoutingevent.com`.** Enforced across Python sockets,
  application network policy, and browser subprocess egress. Only an explicit two-part
  opt-in live smoke may reach the real service.
- **Upstream attendee ID is required at the boundary and fails closed when absent.**
  Names, digests, HMACs, and shortened IDs are not identity. Output identity is a full
  per-run UUIDv4.
- **Shareable artifacts never contain the upstream attendee ID, QR token, or session
  material.**
- **Migration is copy-only, hash-verified, resumable, collision-safe, and never deletes
  the legacy source.**
- **The launcher's audience is non-technical.** Double-click to run; never touch or
  require a system Python.
- **One installation exists in the wild with real data.** Breaking the install (re-run
  setup) is acceptable; destroying its data is not.

## Architecture

### Architectural style

Hexagonal (ports and adapters) with a functional core and vertical feature slices.
Protocols appear **only at real seams** — merge any module that stays trivially small.
The point is extensibility, not ceremony.

```text
CLI / local web / desktop / launcher      (interfaces)
                 |
          feature services                (features)
                 |
       ports + pure core policies         (core, ports)
        /                    \
input/PDF adapters     ScoutingEvent adapter
storage/artifacts      browser/session adapter   (adapters)
                 |
       explicit composition roots         (runtime, interfaces)
```

Architecture-test-enforced rules:

- Core and ports import no adapters, UI, bootstrap, Playwright, OpenCV, or PDF library.
- Feature services depend on ports and typed DTOs, never global filesystem/network state.
- Runtime owns job supervision but no concrete adapters; interfaces select adapters at
  explicit composition roots.
- Compatibility modules delegate into `scoutmb` and hold no business logic.
- Imports work from installed packages without `sys.path` mutation.

### Target package layout

```text
src/scoutmb/
  __init__.py  __main__.py  errors.py  config.py  logging_setup.py
  core/        models, identity, run_state, output_schemas, inference/ (numbering, tree, status, missing)
  ports/       time, storage, scoutevent, observability, releases
  features/    ingest, acquisition, reporting
  adapters/    files/ (atomic, generations), pdf/, scoutevent/, telemetry/ (noop)
  interfaces/  cli/, web/ (app factory, security-structural, jobs), desktop
  runtime/     job supervisor
  resources/   templates/report.{html,css,js}, email.html, static/
bootstrap/     platforms/, migrate.py, downloader, python_env, browser_setup, marker  (repo root, stdlib-only)
tests/         unit, contract, integration, parity, characterization, security, packaging, migration, launcher, performance, privacy, factories, fakes, gates
tools/         verify_corpus, scrub_fixtures, check_private_data, measure_baseline, build/inspect distributions, release tooling
```

`bootstrap/` stays outside the package: it runs before the app's dependencies exist and
may import only the standard library.

### Application data flow

PDF/CSV/XLSX/JSON inputs → ingest adapters → typed `ScoutInput` → acquisition service
(ScoutingEvent gateway behind a port) → typed `ClassRecord`/`RequirementRecord` →
inference (pure core) → report/email writers (atomic) → local data root. The web/desktop
interfaces drive the same feature services the CLI does.

### Trust model

`scoutingevent.com` is unowned and may change without notice; its payloads are validated
at the gateway and fail closed on drift. The loopback web server is a local boundary
(structural hardening now; CSRF/CSP/auth are vNext). QR URLs and attendee IDs are bearer
tokens for minors' records and never appear in shareable artifacts or logs.

## Core contracts

### Attendee identity and privacy (D3, D25 — KEEP)

The upstream attendee ID is required typed identity; blank/malformed fails the attendee
closed before work. Internal grouping, lookup, and dedup key on that ID. **Output
identity is a full UUIDv4 generated per attendee per run**, persisted in the private run
checkpoint for resume and unrelated across independent runs. Raw upstream ID and QR
tokens stay at the adapter boundary and never enter shareable artifacts, filenames, or
logs. Output filenames combine the display-name slug with the run UUID, never the raw ID.

### Atomic single-file artifact publication (D11, D16 — KEEP; multi-file generation POSTPONED)

CSV, JSON, HTML, and email files have explicit versioned schemas. Each single file is
written render-first → exclusive same-directory temp → flush/fsync/close → `os.replace`
→ parent-dir sync → cleanup, preserving prior bytes on any injected failure or returning
a documented post-replace indeterminate-durability result without a second overwrite.
Output column/field order is pinned by golden tests (guards `__dataclass_fields__` order
for `ClassRecord` and `RequirementRecord`). The multi-file whole-generation pointer is
POSTPONED (vNext).

### Typed configuration and path resolution (D6 — KEEP)

Frozen config dataclasses replace `Namespace` threading. Data-root resolution order:
explicit constructor argument → `SCOUTMB_DATA_DIR` → `platformdirs` user-data location →
`Path.cwd()` only in explicit development mode. **Data paths are never derived from
`__file__`** (lint-rule + regression-test enforced). This closes the coupled hazard where
moving the package silently relocates `scouts.csv`/`runs/` into the package directory.

### Local web trust boundary (D30 — TRIM to structural)

Kept now: a `create_app(settings)` lifespan factory with no import-time side effects; a
`JobRegistry` on `app.state` that retains task references (fixing the `create_task` GC
bug); loopback-only bind; and the four UI-defect fixes. POSTPONED (vNext): CSRF, CSP,
per-launch auth session, and Host/Origin validation.

### Determinism, clocks, and structured concurrency (D32 — KEEP)

Nondeterminism is injected per-collaborator (not one bag): `Clock` (UTC wall time for
persisted timestamps), `IdFactory` (UUIDv4), `Jitter` (seeded RNG for pacing), `Sleeper`
(monotonic-based retry delay). Elapsed time and deadlines use a monotonic source so wall
clock changes cannot affect retry, timeout, or shutdown behavior. The lifespan supervisor
retains and awaits child work; cancellation cleans then propagates.

### Run state machine (D33 — KEEP)

A versioned run-state machine replaces `busy` flags: legal transitions, partial success,
publication eligibility, shutdown, interruption, resume, and recovery are explicit and
testable. Illegal transitions fail closed.

### Requirement inference (KEEP; decomposed)

`annotate_requirement_statuses` decomposes into pure `core/inference/{numbering, tree,
status, missing}.py` — dataclasses in, dataclasses out. The `id(item)` ancestor walk in
`build_missing_requirements` is re-expressed over explicit node indices from the tree.
Both consumers (`write_html_report` and `write_email_reports`) are pinned separately before
the move. The two suspect behaviors (label-row grafting `Note.` → child of the prior
requirement; 31 empty-number requirement rows per canonical snapshot → path `()`) are
characterized as-is; any fix is a separate change. The former 402 count mixed schedule rows
into requirement rows and multiplied across three equivalent private snapshots.

### ScoutingEvent gateway (D22 — KEEP port + drift + breaker + checkpoints; deadline/allowlist POSTPONED)

One adapter owns the attendee session behind a typed port. Payloads are validated against
named schema profiles; unknown/missing fields fail closed with redacted bounded samples,
so an upstream change surfaces loudly instead of producing silently-wrong data. The
acquisition service adds a **circuit breaker** (trips on consecutive-failure count) and
**resumable checkpoints** (resume never repeats completed requests), keeping the existing
retry and schedule-dedup behavior. Deadline/elapsed budgets and the URL allowlist are
POSTPONED (vNext); note the circuit breaker trips on failure count, not elapsed time,
until budgets land.

### External output schemas (D16 — KEEP)

CSV order, JSON/run schema versions, current writer, supported readers, future-version
rejection, and compatibility goldens. Shareable schemas omit sensitive adapter state.

### Local diagnostics and future telemetry (D5, D20 — KEEP full diagnostics; telemetry seam no-op)

Structured rotating logs replace all `print()` calls and never emit names, IDs, tokens,
paths, or payloads. A one-command **redacted support-bundle** generator aids
troubleshooting. Observability is an `ObservabilityPort` with a `NoopObservability`
default and a `TelemetrySpool` protocol reserved as a future contract only — core never
imports OpenTelemetry, and the default creates no telemetry record or network request.

## Installed data and migration

### Migration scope (D5 — KEEP)

One install exists with data at `app/{scouts.csv,pdf-uploads,runs}`. Migration is
copy-only: inventory → copy into staging → SHA-256 verify → activate a versioned marker
written last → leave the originals untouched. Collisions get deterministic preserved
names. Idempotent via a `.migrated` marker. A manual private-backup receipt is required
before the first production migration.

### Cross-process ownership (D29 — POSTPONE; keep mtime lock)

The existing mtime-based bootstrap lock is retained as-is. OS-backed locks, authenticated
rendezvous, and single-instance focus activation are POSTPONED (vNext).

### Split-brain detection (D26 — TRIM)

Migration leaves an explanatory marker in the abandoned old root. Per-launch
hash-comparison monitoring of the old root is POSTPONED (vNext).

### Transactional application releases (D17 partial, D28 — KEEP local mechanics; auto-check POSTPONED)

A release installs into a versioned staging directory in a **fresh environment** (never a
mutation of the live one), validates package and durable-state compatibility, launches
with a one-time **readiness nonce**, then atomically switches `current.json`. Durable
state is **versioned** with an N/N-1 read window; a rollback returns both executable and a
state generation it can read (N→N+1→N proven). The **release-channel + daily auto-update
check are POSTPONED (vNext)** — update discovery is manual/bootstrap-triggered.

### Durable internal-state compatibility (D28 — KEEP)

Runs, checkpoints, settings, and the activation pointer carry schema versions. Unknown or
newer state fails closed before mutation. Upgrades stage and validate before the pointer
switch.

## Packaging, installation, and updates

### Python project and lock contract (D4, D15 — KEEP)

Hatchling `src/` project pinned by `.python-version`, `uv.lock` canonical, launcher's
pinned/hashed `requirements-launcher.txt` derived from the lock (CI fails on drift).
Real sdist + wheel; clean-environment install; wheel rebuilt-from-sdist smoke.

### Dependency and supply-chain maintenance (D36 — TRIM)

Kept: `uv audit` (vulnerabilities) + a CI **license-compliance gate** (fails on a
disallowed/non-redistributable license — the piece that matters for possible "as-is"
distribution). POSTPONED (vNext): per-payload CycloneDX SBOMs and exception-expiry policy.

### Foundation launcher bridge (D2 — KEEP)

Copy/install `src/scoutmb` into the installed app, include it in `build.spec`, and prove a
clean-root launch without the repository present. The source-copy bridge is temporary; the
transactional payload install replaces it.

### Thin installer and capability downloads (D18, D34, D35 — KEEP full)

The emailed installer stays **≤ 18 MB**. Python, Playwright/Chromium, OpenCV, and PDF
support are **separate hash-bound capability downloads** fetched during bootstrap (the
existing model, formalized). Each capability manifest binds app version, Python ABI, OS,
architecture, and lock digest. Downloads are streamed to staging and **hash+size
validated**; archive extraction guards against traversal/symlink/device/expansion
attacks; disk space is preflighted; cache eviction is reference-counted and never evicts
active or rollback payloads. Native builds run on native runners (no cross-build).

### Supported platform matrix (D34 — KEEP)

Supported: **Windows 11 x64** and **macOS 14+ arm64**. Windows 10 x64 is best-effort only
when the Windows 11 payload works unchanged. Unsupported architectures fail before
downloading a payload. The native macOS installer needs a macOS CI runner; notarization is
deferred (D23).

### Health and readiness (KEEP)

An authenticated readiness check confirms the expected release, state generation, and
capability manifest responded. Process-alive or open-port alone cannot activate a release.

### Browser selection (D22 — KEEP)

Windows: system Edge → system Chrome → managed Chromium. macOS: system Chrome → managed
Chromium. Safari is an explicit experimental `safaridriver` option with a truthful
warning, not a supported Playwright path. Selection requires a loopback-fake readiness
transaction; auth/schema failures do not fall back by switching engines.

### Integrity without signing (D23 — KEEP; signing deferred)

Hash/size validation and corruption checks are kept. Signing/notarization is deferred for
internal-only distribution; the authenticity gap is documented and revisited before
distribution broadens.

## Testing strategy

### Gate 1 behavior contract matrix (D8 — KEEP)

Before any code moves, every observable of the legacy app — input formats, field aliases,
dedup, QR variants, the exact 7 attendee columns, inference and both consumers,
non-mutation, output schemas, CLI/UI defaults, errors, request counts, bootstrap/UI/
lifecycle flows — is pinned to a named test and classified `preserve`,
`intentional-change`, or `new-acceptance`.

The authoritative matrix design is
`docs/superpowers/specs/2026-07-22-phase-a-characterization-matrix-design.md`. Cases live in
a central typed catalog reused by legacy characterization and Slice 2 parity. An independent
`AxisSpec`/boundary manifest—not the cases themselves—declares completeness. Domain-specific
frozen case/observation types, strict external-boundary fakes, and typed harness protocols
avoid a universal `Any`-based test framework. Each independent behavior has at least two
focused synthetic cases; finite observed sets receive full coverage; failures receive
immediate-success, recovery, and terminal cases.

### Network policy (D9, D27 — KEEP)

Three denial layers in default tests: Python socket blocking (`pytest-socket`),
application network policy, and guarded browser contexts with external-request sentinels
(a Playwright browser subprocess is **not** covered by `pytest-socket`). CI adds a
deny-by-default `egress-denied` job. `scoutingevent.com` requires a `live_service` marker
plus a separate environment opt-in.

### Test layers

Synthetic factories → unit/property tests; local fake service → gateway/browser contract
tests; legacy adapters → characterization/parity tests; private `raw_data` → automatic
redacted read-only local augmentation when present (D12); throwaway installs →
migration/update rehearsals; explicit staging → read-only live smoke only, never a PR gate.
The Gate 1b authentic lane additionally requires `--require-corpus`, and the browser lane
requires `--require-browser`; neither may pass through a skip or empty marker selection.

### Synthetic and private corpora (D7, D12 — KEEP)

Committed fixtures are deterministic and fully synthetic. A typed surface-policy inventory
distinguishes input-private, adapter-private, operational-private, audience-shareable, local
user-interface, and diagnostic egress. Fixture sources and every non-adapter generated
surface fail closed on forbidden sentinels; authorized adapter-private surfaces instead use
narrow field, containment, filename, and no-copy allowlists. The default local pytest run
always executes focused and variable/scale synthetic profiles. When `raw_data/` exists, it
also runs redacted read-only private-corpus checks; `--corpus-dir` selects another location.
CI runs the synthetic suite and skips the absent private corpus.

### Legacy-to-new parity (D13 — KEEP)

Legacy and new code compared through implementation-neutral adapters; deterministic fields
normalized; intentional changes reviewed; legacy removed only after parity.

### Required focused coverage

Identity (same-name isolation, fail-closed missing ID, UUIDv4 survives resume, no raw ID
in shareable outputs); inference (non-mutation, leaf/ancestor selection, `(not used)` and
`type_id==3` exclusions, all 26 number shapes in path and tree contexts, all 4 observed
requirement flag combinations in leaf and parent/consumer contexts, 31 empty-number and
125 `Note.`-shape requirement rows per canonical snapshot, choice thresholds); atomic
single-file failure matrix; schema drift (critical vs
optional vs unknown); loaders (all formats + aliases); PDF (decode tiers, corrupt,
strict, adult filter); scraper (retry ×3 at 500/1000/1500 ms, dedup, circuit breaker,
checkpoint resume); template (`__REPORT_DATA__` sentinel, `</script>`, U+2028/2029); migration
(copy-only, idempotent, collision, reinstall survival); run-state transitions; download
hash/size + hostile-archive matrix; scrubber leaky-input suite. Slice 1b additionally pins
spreadsheet formula/control prefixes; file and non-file privacy egress; stdout/stderr/SSE/API
channels; clean-subprocess dependency profiles; strict-fake self-tests; async disconnect and
pending-resource cleanup; corpus absent/wrong/symlink/mutation states; traversal and
symlinks; Windows reserved/drive/UNC/case paths; macOS NFC/NFD/volume/case paths; and two
real-boundary vertical flows. Native filesystem/installer behavior remains in Slices 3/4.

### Coverage policy (D10 — KEEP)

Honest baseline, no regression; new core/payload-validation code ≥ 95% branch, new
feature/file-adapter code ≥ 90%, lower platform/UI results require explicit
uncovered-line justification. Per-area floors are enforced from coverage JSON by a checked-in
area baseline and exact reviewed line/branch exclusion manifest (equivalent to separate
`coverage report --include=<glob> --fail-under=<n>` gates, not pytest's single global gate),
with branch coverage on. Stale exclusions fail, baseline updates are explicit, and Gate runs
use check mode only. Coverage is not the correctness gate — the behavior matrix, failure
injection, parity, and privacy scans are separate gates.

### Performance gate (D21 — KEEP)

Baselines captured before thresholds. Request-count and algorithmic-growth assertions are
hard; controlled wall-time comparisons run on named machine classes with explicit
variance and regression thresholds. Hypothesis covers parsers, state transitions, and
archive paths.

## Continuous integration

Staged across phases (a full workflow cannot pass before the package and tests exist):

| Added in phase | Jobs |
| --- | --- |
| A | `lint-format`, `types`, `lock`, `unit-contract`, capability environments, `local-playwright`, `egress-denied`, `supply-chain` (audit + license) |
| B | + `architecture`, `package`, `local-web-structural` |
| C | + `launcher-windows`, `launcher-macos` migration/update slices |
| D | full platform launcher matrices, `performance`; local-only `private-corpus`; manual-only `live-smoke` |

## Execution phases and go/no-go gates

The specification owns *why* and behavioral contracts; the plans own file-by-file
execution. Work is delivered as **five plan files across four phases**: Slice 1 is split
into 1a and 1b, followed by Slices 2–4. Later plans are refined after the prior gate runs.

- **Slice 1a — Foundation & In-Place Correctness.** Packaging, lock, CI, offline
  enforcement, fixture/privacy foundations, and the surgical in-place fixes that protect
  the live install: attendee identity, atomic single-file writes, `data_root` resolution,
  and copy-only migration. **Gate 1a** closes the in-place work.
- **Slice 1b — Full Phase A Characterization.** The reusable matrix catalog, focused and
  variable/production-scale synthetic data, local browser and vertical flows, read-only
  authentic-corpus augmentation, and pre-refactor baselines. **Gate 1b** unblocks Slice 2.
- **Slice 2 — Package Boundaries & Core (Phase B).** Hexagonal restructure, typed core,
  input/PDF adapters, ScoutingEvent gateway (port + drift + breaker + checkpoints),
  run-state machine + job supervisor, structural web boundary, entrypoint parity, clean
  distributions. **Gate 2.**
- **Slice 3 — Storage, Migration Hardening & Transactional Releases (Phase C).**
  Data-root management (permissions + explicit delete), migration hardening + split-brain
  marker, versioned durable state, transactional A/B install + readiness + rollback.
  **Gate 3.**
- **Slice 4 — Installer, Capabilities & Hardening (Phase D).** Thin installer + capability
  splitting + native builds, browser selection, download/archive safety, full diagnostics
  + telemetry seam, performance gates, supply-chain (audit + license), final acceptance.

Gates are stop points, not summaries. A red gate blocks the next slice; waivers do not
open it.

### Plan task contract

Each task has one observable outcome, symbol-based anchors, the RED test, the
implementation change (with code), the exact verification command and expected result,
privacy/compatibility impact, and a recovery path. Mechanical movement and deliberate
behavior changes are separate tasks.

## Decision appendix

Status key: **KEEP** (full), **TRIM** (reduced this version), **POSTPONE** (vNext).
Locked unless a later review supersedes.

| ID | Decision | Status |
| --- | --- | --- |
| D1 | One execution effort with hard go/no-go gates. | KEEP (delivered as sliced plans) |
| D2 | Preserve the source-copy launcher bridge for the foundation. | KEEP |
| D3 | Upstream attendee ID is sensitive typed identity; fail closed when absent. | KEEP |
| D4 | `uv.lock` canonical; derive the launcher's hashed requirements from it. | KEEP |
| D5 | Copy-only, hash-verified, marker-last migration; never delete originals. | KEEP |
| D6 | Resolve production storage explicitly; never from `__file__`. | KEEP |
| D7 | Commit only deterministic fully synthetic fixtures. | KEEP |
| D8 | Complete legacy behavior matrix before movement. | KEEP |
| D9 | Default tests never call the real service; two-part opt-in live smoke only. | KEEP |
| D10 | Measure coverage honestly; it is not the correctness gate. | KEEP |
| D11 | Atomic single-file artifact publication. | KEEP (multi-file generation POSTPONED) |
| D12 | Verified private corpus augments local tests. | KEEP |
| D13 | Compare legacy/new through implementation-neutral adapters. | KEEP |
| D14 | Keep raw identity and QR tokens out of shareable outputs. | KEEP |
| D15 | Build a real Python distribution (sdist + wheel). | KEEP |
| D16 | Version external output schemas through DTOs. | KEEP |
| D17 | Install releases transactionally. | TRIM — local A/B + rollback + readiness KEEP; release-channel + daily auto-check POSTPONE |
| D18 | Thin ≤18 MB installer; large capabilities as downloads. | KEEP |
| D19 | Hexagonal boundaries, functional core, vertical slices. | KEEP |
| D20 | Local diagnostics + OpenTelemetry-shaped future seam. | KEEP (no-op default) |
| D21 | Performance baselines before thresholds. | KEEP |
| D22 | Isolate the legacy service behind a gateway + drift detector. | TRIM — port + drift + circuit breaker + checkpoints KEEP; deadline budgets + URL allowlist POSTPONE |
| D23 | Defer signing/notarization while internal. | KEEP (deferred) |
| D24 | Spec owns contracts; plans own execution order. | KEEP |
| D25 | Full UUIDv4 per attendee per run for output identity. | KEEP |
| D26 | Detect writes to the abandoned legacy root after cutover. | TRIM — one-time migration marker KEEP; per-launch monitoring POSTPONE |
| D27 | Offline guarantee across Python and browser process boundaries. | KEEP |
| D28 | Version durable state; rollback is data-compatible (N/N-1). | KEEP |
| D29 | OS-backed ownership and single-instance desktop behavior. | POSTPONE — keep existing mtime lock |
| D30 | Treat the loopback server and uploads as security boundaries. | TRIM — factory + job registry + loopback + UI-bug fixes KEEP; CSRF/CSP/auth/Host-Origin POSTPONE |
| D31 | Explicit sensitive-data permissions, retention, deletion. | TRIM — current-user permissions + explicit delete KEEP; timed retention + backup/restore POSTPONE |
| D32 | Separate UTC wall time from monotonic deadlines; owned concurrency. | KEEP |
| D33 | Persist a versioned run-state machine. | KEEP |
| D34 | Release-level platform + capability compatibility matrix. | KEEP |
| D35 | Bound archive/download/disk/parser resources. | KEEP |
| D36 | Supply-chain maintenance. | TRIM — `uv audit` + license gate KEEP; per-payload SBOM + expiry POSTPONE |

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Same-named attendees corrupt records | Typed upstream identity in memory; per-run UUIDv4 in outputs; fail closed on missing identity |
| Legacy and new code diverge during restructure | Implementation-neutral parity suite; hard gates per slice |
| Installed data lost or split across roots | Explicit data root, copy-only hashed migration, originals retained, migration marker, manual backup |
| Upstream schema changes silently | Validated object boundary, fixture profiles, fail-closed drift policy |
| Default tests or browser subprocess leak data | Synthetic-only fixtures, socket guard, network policy, guarded browser contexts, egress-denied CI |
| Output fails halfway | Render-first, same-dir temp, fsync, atomic replace; prior bytes preserved |
| `id()` inference bookkeeping breaks on dataclasses | Re-express ancestor walk over node indices; pin selection behavior first |
| Update corrupts code/state the old release can't read | Immutable code + versioned state generations, N/N-1 window, readiness, atomic pointer, N→N+1→N rollback |
| Circuit breaker without deadline budgets | Trips on consecutive-failure count; deadline budgets are a documented vNext addition |
| macOS installer needs native runner | macOS CI runner in Slice 4; notarization deferred (D23) |
| Architecture becomes ceremonial | Protocols only at real seams; merge unjustified tiny modules |

## Acceptance criteria (this version)

1. Legacy behavior matrix + new contract suite green on synthetic data.
2. Default tests provably cannot call `scoutingevent.com` (sockets, gateway, Playwright,
   browser subprocess, redirects, workers, frames, popups, WebSockets).
3. Two same-named attendees stay separate through acquisition, inference, reports, resume.
4. Every declared file and non-file surface satisfies its typed egress policy; upstream IDs,
   QR/session material, raw payload state, and unredacted exceptions appear only on explicitly
   authorized adapter-private surfaces.
5. Single-file output writers survive injected failures without corrupting prior artifacts.
6. External schemas are versioned and compatibility-tested.
7. A clean sdist and wheel install outside the repository run the CLI and local web app.
8. A copy of the legacy layout migrates without altering the source and handles collisions.
9. A bad release fails readiness and rolls back to a known-good executable + readable
   state generation (N→N+1→N).
10. The emailed installer stays ≤18 MB and downloads hash-bound capability payloads.
11. Windows selects Edge→Chrome→Chromium; macOS selects Chrome→Chromium; Safari explicit.
12. Local logs and support bundles are useful and redacted; telemetry no-op by default.
13. Performance and request-count gates show no unacceptable regression.
14. Architecture tests and documentation match the installed application.
15. Downloads are hash/size validated; hostile archives fail before activation.
16. Wall-clock jumps do not affect retry/timeout/shutdown; durable timestamps are UTC.

## Open questions

None block plan generation. POSTPONED items are deferred, not unresolved. Suspected legacy
inference defects (`Note.` grafting, empty rows) remain characterized behavior until a
separate fix is proposed.
