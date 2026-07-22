<!--
====================================================================================
ARCHIVED — SUPERSEDED. DO NOT EXECUTE. Reference only.
====================================================================================
This is the single-plan, maximalist-scope execution plan (36 tasks, 3 gates, full
production hardening) as committed at 4de855c. It was superseded on 2026-07-22 by:

  * docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md   (descoped spec)
  * docs/superpowers/plans/2026-07-22-slice-1..4-*.md              (four sliced plans)

Retained because its Phase A/B/C/D task decomposition, ~130 named tests, failure-mode
coverage tables, CI-growth notes, and recovery behaviors are a useful reference that
the sliced plans draw from. It has intentionally NO .tasks.json sidecar so that
executing-plans cannot pick it up. The current READY plan is Slice 1.

Original header follows.
====================================================================================
-->

# ScoutMB Foundation Execution Plan (ARCHIVED / SUPERSEDED — reference only)

**Status:** Ready for implementation
**Rewritten:** 2026-07-22
**Specification:** `docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`
**Execution contract:** Four phases, three blocking go/no-go gates, and one final acceptance task

## Outcome

Turn the current script-oriented application into an installable Python 3.12 product without
changing known behavior accidentally, exposing private attendee data, or making normal automated
tests contact `scoutingevent.com`. The target architecture is hexagonal: a functional core, explicit
ports, adapters at the edges, and vertical feature slices at composition boundaries.

This plan is the sole execution source of truth for the foundation work. Its generated sidecar is
valid only when `planDigest.algorithm` is `sha256` and `planDigest.value` matches this file. An
executor must stop before running a task if the hashes differ or the digest schema is unknown.

## Non-negotiable contracts

- Default unit, contract, integration, UI, browser, packaging, and performance tests use synthetic
  data or a local fake service. Only an explicitly opted-in staging/live smoke test may contact the
  real service.
- A private local corpus under `raw_data/` may supplement synthetic tests. It is never committed,
  copied into hosted CI, or printed except as redacted aggregates.
- Upstream attendee ID is required at the boundary. Missing or malformed identity fails closed.
  Each accepted attendee receives a full random UUIDv4 scoped to that run. Names, digests, HMACs,
  shortened identifiers, and unresolved buckets are not identity.
- Shareable artifacts never contain the upstream attendee ID, QR token, session cookies, or bearer
  material.
- Migration is copy-only, hash-verified, resumable, collision-safe, and never deletes the legacy
  source. Split-brain writes are detected and preserved.
- The launcher owns one installed instance through an OS-backed lock and authenticated rendezvous.
  A second launch activates the existing instance and exits.
- The emailed installer remains at or below 18 MB, leaving margin below the 25 MB transport limit.
  Playwright/browser, OpenCV, and PDF support are separate capability downloads.
- Supported release targets are Windows 11 x64 and macOS 14+ arm64. Windows 10 x64 is best effort
  only when the Windows 11 payload works unchanged.
- D23 signing and notarization remain deferred for internal-only distribution. Revisit before any
  broader distribution.

## Scope boundaries

### In scope

- Packaging, lock files, quality tooling, CI, offline enforcement, fixtures, behavior
  characterization, package boundaries, identity, outputs, local runtime, storage, migration,
  updates, thin installers, optional capabilities, diagnostics seams, supply-chain evidence, and
  performance/resource limits.

### Not in scope

- Rebuilding or modifying `scoutingevent.com`.
- A cloud backend, multi-user server deployment, or remote telemetry collector.
- Automatic telemetry upload or a production telemetry spool; Phase D provides only an offline-safe
  OpenTelemetry-shaped seam, a no-op implementation, and the future spool protocol.
- Selection of a release-hosting vendor. The release contract uses a configurable controlled HTTPS
  artifact origin and a local fake; it does not couple the application to GitHub, S3, or another host.
- Code signing/notarization, automatic downgrade migrations, or Windows 10-specific payloads.
- Treating Safari as a supported automated acquisition engine. It is an explicit experimental
  system-browser option on macOS; Chrome then managed Chromium are supported acquisition paths.
- Deleting legacy data or the compatibility shims before final parity and migration acceptance.

## What already exists

The repository graph was refreshed before this rewrite. It currently identifies 169 code symbols,
22 execution flows, no test nodes, and several large orchestration hotspots.

| Existing area | Source anchors | Behavior this plan preserves or isolates |
| --- | --- | --- |
| Schedule acquisition and reports | `scout_schedule_cli.py`: `process_scout`, `annotate_requirement_statuses`, `build_missing_requirements`, `write_outputs`, `async_main` | Input formats, retries, inference, CSV/JSON/HTML/email outputs, CLI defaults |
| PDF extraction | `pdf_to_scouts.py`: `expand_pdf_inputs`, `decode_embedded_qr`, `extract_pdf`, `write_attendees_csv` | PDF discovery, QR extraction, attendee CSV contract, error behavior |
| Local web application | `ui/server.py`: `start_pdf_extract`, `start_schedule_download`, `operation_events`, `open_report` | Background operations, status/SSE APIs, report launch, pause/resume |
| Desktop entry point | `run_app.py`: `free_port`, `start_server`, `wait_until_ready`, `run` | Local server startup and desktop window launch |
| Windows bootstrap | `bootstrap/main.py`: `_acquire_lock`, `_launch_app`, `_run`; `bootstrap/paths.py`: `get_paths`; `bootstrap/source_sync.py`: `sync_app_source` | Installation ownership, source copy, Python/browser setup, application launch |
| Download and environment setup | `bootstrap/downloader.py`: `download`; `bootstrap/python_env.py`: `provision_python`; `bootstrap/browser_setup.py`: `resolve_browser_channel`; `bootstrap/marker.py`: `is_environment_valid` | Downloads, extraction, dependency install, browser selection, readiness marker |

`ui/server.py` currently mutates `sys.path`; Phase B removes that behavior. The new package must be
installed into the development environment and copied/installed into release roots through normal
packaging. No first-party module may add or rewrite import search paths.

## Target dependency direction

```text
CLI / local web / desktop / launcher
                 |
          feature services
                 |
       ports + pure core policies
        /                    \
input/PDF adapters     ScoutingEvent adapter
storage/artifacts      browser/session adapter
                 |
       explicit composition roots
```

Rules enforced by architecture tests:

- Core and ports import no adapters, UI, bootstrap, Playwright, OpenCV, or PDF library.
- Feature services depend on ports and typed DTOs, never global filesystem or network state.
- Runtime owns job supervision but no concrete adapters. Interfaces select adapters and own resource
  lifetimes at explicit composition roots.
- Compatibility modules delegate into `scoutmb` and contain no business logic.
- Imports work from installed packages and clean copied release roots without `sys.path` mutation.

## Test topology

```text
synthetic factories ---> unit and property tests --------------------+
local fake service ---> gateway/browser contract tests --------------+--> gate suites
legacy adapters ------> characterization and parity tests ------------+
private raw_data -----> optional local redacted corpus checks --------+
throwaway install ----> migration/update/platform rehearsals ---------+
explicit staging -----> read-only live smoke only; never a PR gate ---+
```

Every production network path receives three layers of denial in default tests: Python socket
blocking, application network-policy checks, and guarded browser contexts with external-request
sentinels. The `egress-denied` CI job additionally runs browser tests in a deny-by-default network
sandbox.

## Execution rules

1. Execute tasks only when every `blockedBy` task in the sidecar is complete.
2. Write the named RED test before changing production behavior. Characterization tests may start
   green only when they pin existing behavior.
3. Run every command listed by the task in order. A task is complete only when all expected results
   are observed.
4. If recovery says “preserve legacy,” restore the prior adapter as the default and retain the new
   code behind the explicit composition seam; do not weaken a test to make the task green.
5. Gates are stop points, not summaries. Do not begin the next phase with a conditional waiver.
6. Keep commits task-scoped. Never include `raw_data/`, local state, credentials, generated private
   reports, or unrelated working-tree changes.

For every implementation task, **Anchors** name the input/change surfaces, **Observable result** is
the single output, and **Contract** states invariants, failure behavior, and privacy/compatibility
impact. **Named tests**, **Commands**, **Expected**, and **Recovery** are the acceptance and rollback
contract. Gate sections use the same acceptance fields but aggregate completed tasks rather than
introducing another implementation change.

## Parallelization

- After A1, A2-A4 may proceed in parallel. A5 follows A4; then A6-A8 and A10 may proceed in
  parallel. A9 follows A7-A8. Tasks that share fixture or test configuration files remain sequential.
- After Gate 1, the gateway/acquisition lane (B4-B5), identity/output lane (B6-B8), and runtime lane
  (B9-B11) may proceed concurrently once their declared dependencies are satisfied.
- Phase C is intentionally conservative: storage and ownership land before migration and release
  activation. Do not parallelize edits to bootstrap state, locks, or activation metadata.
- After Gate 3, D1 capability work and D5 observability may proceed in parallel. The release lane is
  D1 -> D2 -> D3 -> D4. D6 and D7 consume the completed release/capability evidence, and D8 is final
  acceptance.

## Phase A — Tooling and complete characterization

Production behavior stays in place. This phase creates reproducible Python and capability test
environments, baseline supply-chain/platform evidence, an offline boundary, synthetic/private
fixtures, and a complete legacy contract matrix.

### A1 — Establish Python 3.12 project metadata and the canonical lock

- **Observable result:** A Hatchling `src/` project pinned by `.python-version` syncs reproducibly
  from `uv.lock`, exports the launcher's hashed requirements from that lock, and imports as an
  installed package without path manipulation.
- **Anchors:** `.python-version`; `pyproject.toml`; `uv.lock`; `requirements-launcher.txt`;
  `.gitignore`.
- **Contract:** `requires-python` and `.python-version` select Python 3.12. Core, optional runtime
  capabilities, and development groups are separate; development groups never act as runtime feature
  flags. The launcher export contains runtime dependencies only and is not a second source of truth.
- **Named tests:** `tests/packaging/test_project_metadata.py::test_python_and_build_contract`;
  `tests/packaging/test_project_metadata.py::test_launcher_export_matches_lock`;
  `tests/packaging/test_project_metadata.py::test_optional_dependencies_are_not_dev_groups`.
- **Commands:** `uv python pin 3.12`; `uv lock --check`; `uv sync --locked --all-groups`;
  `uv run python -c "import sys; assert sys.version_info[:2] == (3, 12)"`;
  `uv export --locked --no-dev --no-emit-project --format requirements.txt --output-file requirements-launcher.txt`;
  `uv run pytest tests/packaging/test_project_metadata.py -q`.
- **Expected:** Every command exits 0; `.python-version` is `3.12`; the export has no diff after
  regeneration; Python reports 3.12; `import scoutmb` resolves from the editable installed package.
- **Recovery:** If selection, resolution, or export is not reproducible, correct project markers and
  regenerate `uv.lock`; never hand-edit `.python-version`, the lock, or exported pins to fake parity.

### A2 — Add green quality, lock, and capability-environment CI

- **Observable result:** Every pull request runs green lint, format, type, lock, branch-coverage, and
  explicit core/acquisition/PDF/all-extras environment checks on Python 3.12.
- **Anchors:** `.github/workflows/ci.yml`; Ruff, mypy, pytest, and coverage configuration in
  `pyproject.toml`; `tests/ci/test_workflow_contract.py`.
- **Contract:** CI uses locked sync. Optional-feature jobs install their declared extras explicitly;
  `--all-groups` is never treated as installing extras. Pytest enables `strict_config`,
  `strict_markers`, `xfail_strict`, a reviewed warnings policy, and failure on unexpected capability
  skips. Coverage records the honest baseline and may not regress; new core/payload-validation code
  requires at least 95% branch coverage, new feature/file-adapter code at least 90%, and any lower
  platform/UI result requires explicit uncovered-line justification.
- **Named tests:** `tests/ci/test_workflow_contract.py::test_phase_a_jobs_are_required`;
  `tests/ci/test_workflow_contract.py::test_ci_uses_locked_sync_and_explicit_extras`;
  `tests/ci/test_pytest_contract.py::test_strict_configuration_and_skip_policy`.
- **Commands:** `uv sync --locked --all-groups --all-extras`; `uv run ruff check .`;
  `uv run ruff format --check .`; `uv run mypy src tests`;
  `uv run pytest tests/ci -q`.
- **Expected:** All commands exit 0; the workflow pins Python 3.12; core, acquisition, PDF, and
  all-extras jobs name their sync command; no unexpected skip or live-service smoke passes silently.
- **Recovery:** Narrow documented mypy exceptions only around legacy or untyped third-party adapters.
  Repair an unavailable capability environment rather than skipping it or weakening strict settings.

### A3 — Establish supply-chain and supported-platform evidence

- **Observable result:** Phase A CI produces a reproducible locked-dependency vulnerability result,
  license decision, development SBOM, clean-build metadata, and an explicit supported-platform file.
- **Anchors:** `.github/workflows/ci.yml` job `supply-chain`; `release/platforms.json`;
  `release/license-policy.toml`; `tools/check_licenses.py`; `tools/build_dependency_evidence.py`.
- **Contract:** Baseline evidence is policy-gated before code movement. It records the lock digest,
  source revision, uv/build-tool versions, package hashes/licenses, and Windows 11 x64/macOS 14+
  arm64 assumptions. It does not claim signing or publisher authenticity.
- **Named tests:** `tests/release/test_supply_chain_baseline.py::test_locked_baseline_is_complete`;
  `tests/release/test_platform_contract.py::test_supported_and_best_effort_matrix_is_explicit`;
  `tests/ci/test_workflow_contract.py::test_supply_chain_is_a_phase_a_job`.
- **Commands:** `uv audit`; `uv run python tools/check_licenses.py --policy release/license-policy.toml`;
  `uv run python tools/build_dependency_evidence.py --lock uv.lock --output build/evidence/phase-a`;
  `uv run pytest tests/release/test_supply_chain_baseline.py tests/release/test_platform_contract.py tests/ci/test_workflow_contract.py -q`.
- **Expected:** All commands exit 0; no unexpired unapproved finding remains; the SBOM and metadata
  reference the exact lock; platform metadata distinguishes supported, best-effort, and unsupported.
- **Recovery:** Keep production behavior unmoved, correct the lock/policy/metadata, regenerate all
  evidence together, and do not waive an unknown license, vulnerability, or platform assumption.

### A4 — Enforce offline-by-default tests and application egress policy

- **Observable result:** Any default-test attempt to reach a non-loopback address, including from
  Playwright redirects, frames, popups, workers, service workers, WebSockets, alternate ports, direct
  IPs, or browser subprocesses, fails before private data leaves the process.
- **Anchors:** `tests/conftest.py`; `src/scoutmb/network_policy.py`; `.github/workflows/ci.yml` jobs
  `local-playwright` and `egress-denied`.
- **Contract:** Loopback fake services are permitted. `scoutingevent.com` requires a `live_service`
  marker plus a separate environment opt-in; ordinary constructors, tests, hooks, builds, and
  verification commands cannot create a live gateway.
- **Named tests:** `tests/network/test_offline_policy.py::test_non_loopback_socket_is_blocked`;
  `tests/network/test_offline_policy.py::test_live_gateway_requires_two_part_opt_in`;
  `tests/integration/test_browser_egress.py::test_all_browser_request_surfaces_are_guarded`.
- **Commands:** `uv run pytest tests/network tests/integration/test_browser_egress.py -q`;
  `uv run pytest -m "not live_service" -q`.
- **Expected:** Both commands exit 0; sentinels record zero non-loopback requests; every hostile
  browser surface fails with `ExternalNetworkBlocked`; the real-service request count remains zero.
- **Recovery:** Disable the new network adapter, retain the local fake path, and repair the missing
  guard. Never recover by allowlisting the real host in default tests.

### A5 — Create synthetic factories and a repository privacy tripwire

- **Observable result:** Deterministic committed factories cover identity, token, requirement,
  payload, UI, installer, migration, and output edge cases and fail closed if likely private data is
  introduced.
- **Anchors:** `tests/factories/`; `tests/fixtures/synthetic/`; `tests/privacy/test_fixture_hygiene.py`.
- **Contract:** Factories are deterministic when seeded, while UUIDv4 tests assert version and
  uniqueness rather than fixed values. No fixture or filename derives from private Scout data.
- **Named tests:** `tests/privacy/test_fixture_hygiene.py::test_committed_fixtures_are_synthetic`;
  `tests/factories/test_record_factories.py::test_identity_edge_cases_are_representable`;
  `tests/factories/test_system_factories.py::test_platform_and_failure_cases_are_representable`.
- **Commands:** `uv run pytest tests/factories tests/privacy/test_fixture_hygiene.py -q`;
  `uv run python tools/check_private_data.py tests`.
- **Expected:** Both commands exit 0; the scanner prints `private-data findings: 0` without echoing
  matched source text; every Gate 1 matrix category can name a synthetic fixture.
- **Recovery:** Quarantine the new fixture outside the repository, improve the factory or scanner,
  and rerun. Do not add real values to an allowlist.

### A6 — Add optional private-corpus verification

- **Observable result:** `pytest --corpus-dir raw_data` always runs the synthetic suite and, when the
  local corpus exists and matches its manifest lock, adds redacted read-only private-corpus checks.
- **Anchors:** `tools/verify_private_corpus.py`; `tests/tools/test_private_corpus.py`; pytest option
  `--corpus-dir`; gitignored private-corpus manifest.
- **Contract:** The verifier checks every source path, category, schema version, aggregate count, and
  tree hash; rejects paths outside the supplied root; never modifies the source; never sends network
  traffic; and requires an explicit manifest-update command after legitimate local change.
- **Named tests:** `tests/tools/test_private_corpus.py::test_absent_corpus_runs_synthetic_then_skips_private`;
  `tests/tools/test_private_corpus.py::test_manifest_drift_fails_closed`;
  `tests/tools/test_private_corpus.py::test_output_is_aggregate_redacted_and_offline`.
- **Commands:** `uv run pytest tests/tools/test_private_corpus.py -q`;
  `uv run pytest --corpus-dir raw_data -m "not live_service" -q`.
- **Expected:** Commands exit 0 with synthetic tests always executed and either `private corpus: PASS`
  or `private corpus: SKIPPED (not present)`; output contains no names, IDs, tokens, paths, or URLs.
- **Recovery:** Stop at manifest or redaction failure, remove only tool-owned derived staging,
  preserve `raw_data/` untouched, and require explicit manifest review before rerunning.

### A7 — Characterize every input and PDF extraction contract

- **Observable result:** A table-driven suite pins XLSX, CSV, JSON, text, directory/glob expansion,
  field aliases, deduplication, QR variants, the exact seven attendee columns, ordering, strict mode,
  corrupt/stale-error behavior, and optional-capability absence.
- **Anchors:** `scout_schedule_cli.py`: `load_inputs`, `load_xlsx`, `load_csv`, `load_json`,
  `load_text`; `pdf_to_scouts.py`: `expand_pdf_inputs`, `decode_embedded_qr`, `extract_pdf`,
  `write_attendees_csv`.
- **Contract:** Tests describe current observable behavior, including awkward cases, without fixing
  them. PDF/OpenCV imports remain optional, but the PDF CI environment installs and executes them.
- **Named tests:** `tests/characterization/test_input_matrix.py::test_all_supported_input_shapes`;
  `tests/characterization/test_pdf_matrix.py::test_pdf_decode_and_error_matrix`;
  `tests/characterization/test_pdf_matrix.py::test_exact_attendee_csv_schema_is_stable`.
- **Commands:** `uv sync --locked --all-groups --extra pdf`;
  `uv run pytest tests/characterization/test_input_matrix.py tests/characterization/test_pdf_matrix.py -q`.
- **Expected:** Commands exit 0; every locked matrix row names its fixture and observable; the PDF
  environment executes real adapter imports and the core-only path remains separately testable.
- **Recovery:** Correct mistaken expectations from observed legacy output. Do not alter production
  parsing or mark a capability test skipped to make the matrix green.

### A8 — Characterize ScoutingEvent and browser-session behavior against a local fake

- **Observable result:** A loopback fake and real Playwright API surface reproduce session setup,
  payload shapes, redirects, schema drift, retryable/terminal errors, deduplication, and request counts
  without contacting the real service.
- **Anchors:** `scout_schedule_cli.py`: `navigate_and_trigger_schedule`, `post_requirement`,
  `process_scout`; `tests/fakes/scoutingevent_service.py`; guarded Playwright fixtures.
- **Contract:** `FakePage`, response/request objects, payload field names, and callbacks match the
  production call surface; loose accept-anything mocks are forbidden. Current behavior is pinned and
  intentional Phase B changes are recorded separately.
- **Named tests:** `tests/characterization/test_scoutingevent_contract.py::test_observed_payload_matrix`;
  `tests/characterization/test_scoutingevent_contract.py::test_current_retry_and_error_matrix`;
  `tests/characterization/test_browser_session.py::test_real_playwright_surface_uses_loopback_only`.
- **Commands:** `uv sync --locked --all-groups --extra acquisition`;
  `uv run pytest tests/characterization/test_scoutingevent_contract.py tests/characterization/test_browser_session.py -q`.
- **Expected:** Commands exit 0; fake request counts match; external-request sentinels remain zero;
  schema variants are named fixtures; unexpected Playwright API use fails rather than being accepted.
- **Recovery:** Extend the local fake with the missing observed shape. Never capture a new live
  response in an automated test or weaken the egress policy.

### A9 — Characterize inference, artifacts, interfaces, and baseline performance

- **Observable result:** The remaining legacy matrix pins requirement parsing, inference and both
  consumers, non-mutation, output schemas, CLI/UI defaults, errors, request counts, startup, runtime,
  memory, installed footprint, and artifact sizes using repeated samples.
- **Anchors:** `scout_schedule_cli.py`: `requirement_path`, `annotate_requirement_statuses`,
  `build_missing_requirements`, `write_email_reports`, `write_outputs`; `ui/server.py` API routes;
  `run_app.py`: `run`; `tools/measure_baseline.py`.
- **Contract:** Same-name merging is a reviewed known defect to be replaced in B6. Request counts and
  growth are hard assertions; wall time is descriptive until D7 locks controlled thresholds.
- **Named tests:** `tests/characterization/test_inference_matrix.py::test_requirement_and_consumer_matrix`;
  `tests/characterization/test_artifact_matrix.py::test_all_output_schemas_and_failures`;
  `tests/characterization/test_interface_matrix.py::test_cli_web_desktop_defaults`;
  `tests/performance/test_baseline.py::test_request_count_growth_is_bounded`.
- **Commands:** `uv run pytest tests/characterization tests/performance/test_baseline.py -q`;
  `uv run python tools/measure_baseline.py --corpus synthetic --repetitions 5 --output build/baseline.json`.
- **Expected:** Tests exit 0; `build/baseline.json` records machine class, corpus revision, five
  samples, request counts, memory, sizes, installed footprint, variance, and no placeholders.
- **Recovery:** Keep wall time non-blocking, fix missing observables, and rerun on the same machine
  class. Do not move code while a correctness row is absent or red.

### A10 — Characterize bootstrap, local web, run lifecycle, and static UI behavior

- **Observable result:** Every remaining Gate 1 row for installer/bootstrap, local web security,
  lifecycle, and user-visible progress/quiet/error behavior is tied to a legacy test and classified as
  `preserve`, `intentional-change`, or `new-acceptance`.
- **Anchors:** `bootstrap/main.py`, `bootstrap/python_env.py`, `bootstrap/webview2.py`,
  `bootstrap/downloader.py`, `bootstrap/marker.py`; `ui/server.py`; `ui/static/app.js`; `run_app.py`.
- **Contract:** Characterization records insecure or incomplete legacy behavior without treating it
  as the final contract. First/clean/offline launch, contention, interrupted setup, web boundary,
  pause/resume/cancel/shutdown, SSE reconnect, malformed results, double-submit, navigation/close,
  empty/large results, progress, quiet, and recoverable errors are each explicit rows.
- **Named tests:** `tests/characterization/test_bootstrap_matrix.py::test_install_and_launch_matrix`;
  `tests/characterization/test_local_web_matrix.py::test_route_security_and_upload_matrix`;
  `tests/characterization/test_run_lifecycle_matrix.py::test_operation_and_recovery_matrix`;
  `tests/characterization/test_static_ui_matrix.py::test_progress_quiet_cancel_and_error_flows`.
- **Commands:** `uv run pytest tests/characterization/test_bootstrap_matrix.py tests/characterization/test_local_web_matrix.py tests/characterization/test_run_lifecycle_matrix.py tests/characterization/test_static_ui_matrix.py -q`.
- **Expected:** Command exits 0; every Gate 1 category and graph-identified bootstrap/UI flow has an
  observable, fixture, test, and disposition; known deficiencies cannot silently become final parity.
- **Recovery:** Restore a mistaken expectation from observed legacy output, keep unsafe legacy paths
  constrained to loopback/throwaway roots, and block Gate 1 until every row has a reviewed disposition.

## Gate 1 — Characterization go/no-go

- **Observable result:** Phase A produces one reproducible offline characterization, privacy,
  supply-chain, platform, and performance evidence set with a recorded `GO`; any missing row or
  failing command records `NO-GO` and blocks Phase B.
- **Named tests:** `tests/gates/test_gate_1.py::test_characterization_manifest_is_complete`; every
  named test from A1-A10.
- **Commands:** `uv sync --locked --all-groups --all-extras`; `uv run ruff check .`;
  `uv run ruff format --check .`; `uv run mypy src tests`; `uv audit`;
  `uv run python tools/check_licenses.py --policy release/license-policy.toml`;
  `uv run python tools/build_dependency_evidence.py --lock uv.lock --output build/evidence/phase-a`;
  `uv run pytest -m "not live_service" --cov=src/scoutmb --cov-branch -q`;
  `uv run python tools/check_private_data.py tests build/baseline.json build/evidence/phase-a`.
- **Expected GO:** All commands exit 0; every matrix row is classified and tested; no non-loopback
  request, unexpected skip, unapproved supply-chain finding, ambiguous platform assumption, coverage
  regression, or private-data finding occurs; locks, exports, SBOMs, and baselines are reproducible.
- **Recovery / NO-GO:** Stop. Assign the failing evidence to A1-A10, preserve legacy production
  behavior, regenerate related evidence together, and rerun the entire gate. Waivers do not open it.

## Phase B — Package boundaries, identity, outputs, and local runtime

Phase B moves behavior behind ports in small slices. Compatibility entry points remain available
until final acceptance, and parity runs after each move.

### B1 — Introduce package boundaries and compatibility entry points

- **Observable result:** `scoutmb` introduces only the needed `core`, `features`, `ports`, `adapters`,
  `interfaces`, `runtime`, and `resources` modules; legacy top-level scripts delegate to package entry
  points; no first-party code mutates `sys.path`.
- **Anchors:** `src/scoutmb/`; `scout_schedule_cli.py`; `pdf_to_scouts.py`; `ui/server.py`;
  `run_app.py`; console scripts in `pyproject.toml`.
- **Contract:** This is mechanical movement only. Do not create empty destination modules before a
  coherent slice owns them. Compatibility wrappers preserve arguments, exit codes, and output.
  Runtime owns supervision without concrete adapters; interfaces construct dependencies; reverse
  imports and cycles fail architecture tests.
- **Named tests:** `tests/architecture/test_dependency_rules.py::test_hexagonal_import_direction`;
  `tests/architecture/test_dependency_rules.py::test_runtime_and_interface_ownership`;
  `tests/architecture/test_dependency_rules.py::test_no_first_party_sys_path_mutation`;
  `tests/compat/test_legacy_entrypoints.py::test_legacy_entrypoints_delegate_with_parity`.
- **Commands:** `uv run pytest tests/architecture tests/compat/test_legacy_entrypoints.py -q`;
  `uv run python -m scoutmb --help`; `uv run scoutmb --help`.
- **Expected:** All commands exit 0; both help outputs retain the characterized contract; imports
  work from an installed package without repository-root assumptions.
- **Recovery:** Keep the compatibility wrapper as the active path, move one symbol group back, and
  restore parity. Do not add a path mutation or duplicate logic in the wrapper.

### B2 — Establish typed core, clocks, errors, configuration, and DTO versions

- **Observable result:** Pure immutable models represent attendees, classes, requirements, runs,
  artifact generations, typed errors, versioned DTOs, UTC wall time, and monotonic deadlines.
- **Anchors:** `src/scoutmb/core/`; `src/scoutmb/ports/time.py`;
  `src/scoutmb/config.py`; `src/scoutmb/errors.py`.
- **Contract:** Parsing occurs at boundaries; core policies use typed values. Wall time is persisted;
  elapsed time and deadlines use the monotonic clock.
- **Named tests:** `tests/unit/core/test_models.py::test_invalid_states_are_unrepresentable`;
  `tests/unit/test_clocks.py::test_deadlines_ignore_wall_clock_changes`;
  `tests/contracts/test_dto_versions.py::test_unknown_versions_fail_closed`.
- **Commands:** `uv run pytest tests/unit/core tests/unit/test_clocks.py tests/contracts/test_dto_versions.py -q`;
  `uv run mypy --strict src/scoutmb/core src/scoutmb/features src/scoutmb/ports src/scoutmb/runtime`.
- **Expected:** Both commands exit 0; core tests require no filesystem, network, browser, UI, or
  system clock.
- **Recovery:** Remove the incomplete DTO from interface composition, keep boundary dictionaries behind the
  legacy adapter, and repair typed construction without weakening strict checks.

### B3 — Move input and PDF work behind ports with parity

- **Observable result:** Input loading and PDF extraction are adapter implementations selected by
  feature services; core-only installation can load non-PDF inputs without importing PDF/OpenCV
  dependencies.
- **Anchors:** `src/scoutmb/features/ingest/`; `src/scoutmb/adapters/files/`;
  `src/scoutmb/adapters/pdf/`; legacy loader and PDF symbols characterized in A7.
- **Contract:** Adapter DTOs preserve field aliases, ordering, deduplication, and errors. Optional
  dependency absence produces a capability message, not an import crash.
- **Named tests:** `tests/parity/test_input_adapter_parity.py::test_full_input_matrix_matches_legacy`;
  `tests/parity/test_pdf_adapter_parity.py::test_pdf_matrix_matches_legacy`;
  `tests/packaging/test_core_imports.py::test_core_does_not_import_pdf_or_opencv`.
- **Commands:** `uv run pytest tests/parity/test_input_adapter_parity.py tests/parity/test_pdf_adapter_parity.py tests/packaging/test_core_imports.py -q`.
- **Expected:** Command exits 0; legacy and new DTO projections match for every A7 fixture; core-only
  import succeeds with optional libraries absent.
- **Recovery:** Select the legacy adapter at the interface composition root and fix one mismatch at a time. Do
  not make PDF/OpenCV core dependencies.

### B4 — Implement the ScoutingEvent session gateway and schema-drift boundary

- **Observable result:** One adapter owns the attendee session, URL allowlist, payload validation,
  schema profiles, redaction, and drift diagnostics while feature code sees only typed port DTOs.
- **Anchors:** `src/scoutmb/ports/scoutevent.py`;
  `src/scoutmb/adapters/scoutevent/`; `tests/fakes/scoutingevent_service.py`.
- **Contract:** Only HTTPS approved host/path combinations are valid outside tests. Redirects and
  discovered URLs are revalidated. Unknown/missing fields fail closed with redacted bounded samples.
- **Named tests:** `tests/contracts/test_scoutingevent_gateway.py::test_observed_profiles_validate`;
  `tests/contracts/test_scoutingevent_gateway.py::test_schema_drift_fails_closed_and_redacts`;
  `tests/security/test_url_allowlist.py::test_redirect_and_discovered_url_are_revalidated`;
  `tests/parity/test_scoutevent_adapter_parity.py::test_normalized_gateway_results_match_legacy`.
- **Commands:** `uv run pytest tests/contracts/test_scoutingevent_gateway.py tests/security/test_url_allowlist.py tests/parity/test_scoutevent_adapter_parity.py -q`.
- **Expected:** Command exits 0; local fake profiles and normalized legacy/new results match; drift
  cases return typed errors; diagnostics contain no cookies, tokens, upstream IDs, or raw bodies.
- **Recovery:** Keep the legacy local-fake adapter selected, store only redacted drift metadata, and
  add a reviewed schema profile. Never fall back to permissive parsing.

### B5 — Add bounded acquisition retries, deadlines, checkpoints, and a circuit breaker

- **Observable result:** The acquisition service bounds attempts and elapsed time, deduplicates
  requests, checkpoints resumable progress, stops on terminal schema/auth errors, and closes all
  attendee-session resources.
- **Anchors:** `src/scoutmb/features/acquisition/`; gateway and time ports; run checkpoint DTOs.
- **Contract:** Retry delay uses monotonic time and injectable jitter. Cancellation, timeout, and
  circuit-open paths cannot leak browser contexts or HTTP sessions.
- **Named tests:** `tests/unit/acquisition/test_retry_policy.py::test_attempt_and_deadline_budgets`;
  `tests/unit/acquisition/test_checkpointing.py::test_resume_does_not_repeat_completed_requests`;
  `tests/integration/test_acquisition_lifecycle.py::test_all_session_resources_close`;
  `tests/parity/test_acquisition_parity.py::test_results_match_or_are_reviewed_intentional_changes`.
- **Commands:** `uv run pytest tests/unit/acquisition tests/integration/test_acquisition_lifecycle.py tests/parity/test_acquisition_parity.py -q`.
- **Expected:** Command exits 0; fake request ledger proves bounded counts/no duplicates; resource
  tracker ends at zero; every normalized legacy/new difference is in the reviewed change manifest.
- **Recovery:** Disable the new acquisition service at interface composition, retain its checkpoint for
  diagnosis, and restore the characterized adapter. Do not increase budgets to mask leaks.

### B6 — Replace name identity with fail-closed upstream IDs and per-run UUIDv4

- **Observable result:** Two same-named attendees remain distinct through acquisition, inference,
  resume, and reports; blank/malformed upstream IDs stop the attendee before work; shareable IDs are
  full UUIDv4 values unique within each run.
- **Anchors:** `src/scoutmb/core/identity.py`; attendee ingest/acquisition boundaries;
  `annotate_requirement_statuses` and `build_missing_requirements` ports.
- **Contract:** Raw upstream ID remains sensitive adapter state. No unresolved bucket, stable digest,
  HMAC, UUIDv7, name key, shortened UUID, or cross-run linkable ID is permitted.
- **Named tests:** `tests/unit/core/test_identity.py::test_same_name_distinct_upstream_ids_never_merge`;
  `tests/unit/core/test_identity.py::test_missing_upstream_id_fails_closed`;
  `tests/integration/test_identity_flow.py::test_uuidv4_survives_resume_and_outputs_without_raw_id`;
  `tests/parity/test_intentional_changes.py::test_identity_fix_is_the_only_unmatched_identity_difference`.
- **Commands:** `uv run pytest tests/unit/core/test_identity.py tests/integration/test_identity_flow.py tests/parity/test_intentional_changes.py -q`;
  `uv run python tools/check_private_data.py build/test-artifacts`.
- **Expected:** Both commands exit 0; UUID version is 4; two runs use unlinkable UUIDs; privacy scan
  reports zero upstream IDs/tokens; the A9 known-defect expectation is replaced by one reviewed
  intentional difference and the correct contract.
- **Recovery:** Fail the affected run before publication, preserve redacted diagnostic state, and
  restore the legacy adapter only for local fake comparison. Never synthesize identity from a name.

### B7 — Version schemas/templates and publish each artifact atomically

- **Observable result:** CSV, JSON, HTML, and email templates have explicit contract versions;
  single-artifact writes use same-directory temporary files, flush/fsync where required, atomic
  replace, and cleanup while preserving the prior file on failure.
- **Anchors:** `src/scoutmb/core/output_schemas.py`; `src/scoutmb/adapters/files/atomic.py`;
  templates and static assets under `src/scoutmb/resources/`.
- **Contract:** Output order and intentional version changes are documented. Shareable schemas omit
  sensitive adapter state. Templates contain no business logic.
- **Named tests:** `tests/contracts/test_artifact_schemas.py::test_versioned_golden_artifacts`;
  `tests/unit/files/test_atomic_file.py::test_complete_failure_matrix_preserves_previous_bytes_or_reports_indeterminate_durability`;
  `tests/contracts/test_report_template.py::test_placeholders_and_embedded_json_round_trip`;
  `tests/parity/test_output_parity.py::test_outputs_match_or_are_versioned_intentional_changes`;
  `tests/privacy/test_artifacts.py::test_shareable_artifacts_exclude_sensitive_fields`.
- **Commands:** `uv run pytest tests/contracts/test_artifact_schemas.py tests/contracts/test_report_template.py tests/unit/files/test_atomic_file.py tests/parity/test_output_parity.py tests/privacy/test_artifacts.py -q`.
- **Expected:** Command exits 0; goldens and normalized parity match; template edge cases round-trip;
  injected render/write/flush/file-fsync/close/replace/directory-fsync failures preserve old bytes or
  return the documented post-replace indeterminate-durability result without a second overwrite.
- **Recovery:** Keep the previous schema version active, retain failed output only in private staging,
  and fix the writer. Do not partially overwrite the published artifact.

### B8 — Publish multi-file report generations atomically

- **Observable result:** A complete report/email set is staged under a generation ID, validated,
  then activated by one atomic manifest pointer; readers see the prior or new generation, never a
  mixture.
- **Anchors:** `src/scoutmb/features/reporting/`;
  `src/scoutmb/adapters/files/generations.py`; generation manifest contract.
- **Contract:** Interrupted generations remain unreferenced and recoverable. Cleanup never removes
  the active generation or protected recovery/report generations.
- **Named tests:** `tests/integration/test_generation_publication.py::test_readers_never_observe_mixed_generation`;
  `tests/integration/test_generation_publication.py::test_interruption_preserves_active_generation`;
  `tests/contracts/test_generation_consumer.py::test_missing_malformed_future_escaping_and_hash_mismatch_fail_closed`;
  `tests/unit/files/test_generation_cleanup.py::test_protected_generations_survive`;
  `tests/parity/test_report_parity.py::test_report_generations_match_or_are_reviewed_changes`.
- **Commands:** `uv run pytest tests/integration/test_generation_publication.py tests/contracts/test_generation_consumer.py tests/unit/files/test_generation_cleanup.py tests/parity/test_report_parity.py -q`.
- **Expected:** Command exits 0 across every artifact/manifest/pointer failure; the active pointer names
  one complete generation; every malformed/future/escaping/hash-mismatched consumer input fails closed.
- **Recovery:** Leave the previous manifest active, quarantine the incomplete staging directory, and
  offer explicit retry/inspection. Never repair by merging directories.

### B9 — Introduce durable run state and lifespan-owned job supervision

- **Observable result:** Legal run transitions, checkpoints, pause/resume/cancel, startup recovery,
  bounded workers/queue, and graceful shutdown are owned by one supervisor rather than ad hoc
  threads or module globals.
- **Anchors:** `src/scoutmb/core/run_state.py`; `src/scoutmb/runtime/jobs.py`;
  `ui/server.py` worker and operation routes.
- **Contract:** Illegal transitions fail closed. Supervisor owns child tasks and resources;
  cancellation propagates and persists a resumable state before shutdown deadline.
- **Named tests:** `tests/unit/jobs/test_run_state.py::test_transition_table_rejects_illegal_edges`;
  `tests/integration/test_job_supervisor.py::test_restart_recovers_resumable_jobs`;
  `tests/integration/test_job_supervisor.py::test_shutdown_owns_and_closes_children`;
  `tests/parity/test_operation_parity.py::test_user_visible_operation_outcomes_match_or_are_reviewed`.
- **Commands:** `uv run pytest tests/unit/jobs/test_run_state.py tests/integration/test_job_supervisor.py tests/parity/test_operation_parity.py -q`.
- **Expected:** Command exits 0; no non-daemon worker or resource survives each test; restart produces
  the documented terminal/resumable outcome.
- **Recovery:** Stop accepting new jobs, persist current checkpoint, cancel owned children within the
  grace period, and keep the legacy operation adapter selectable until lifecycle tests pass.

### B10 — Secure the loopback web boundary and stream uploads safely

- **Observable result:** A lifespan-created application uses a random session secret, loopback-only
  binding, Host/Origin validation, authentication, CSRF protection, CSP, containment-safe paths,
  streaming upload limits, parser budgets, and redacted errors.
- **Anchors:** `src/scoutmb/interfaces/web/app.py`; `src/scoutmb/interfaces/web/security.py`;
  migrated `ui/server.py` routes; static report response headers.
- **Contract:** No import-time filesystem/network/job side effects. Uploaded names never become
  trusted paths. Security checks apply to API, SSE, report, and state-changing routes.
- **Named tests:** `tests/security/test_local_web.py::test_auth_host_origin_and_csrf_matrix`;
  `tests/security/test_uploads.py::test_streaming_limits_and_path_containment`;
  `tests/security/test_report_csp.py::test_reports_have_restrictive_csp`;
  `tests/integration/test_app_lifespan.py::test_import_has_no_side_effects`;
  `tests/parity/test_local_web_parity.py::test_preserved_routes_match_and_security_changes_are_reviewed`.
- **Commands:** `uv run pytest tests/security tests/integration/test_app_lifespan.py tests/parity/test_local_web_parity.py -q`.
- **Expected:** Command exits 0; unauthorized/cross-origin/oversized/traversal cases are rejected;
  memory remains within the upload budget; valid loopback flows retain characterized responses.
- **Recovery:** Keep the prior UI disabled outside loopback, preserve completed runs, and repair the
  security boundary. Do not bypass authentication for desktop convenience.

### B11 — Compose CLI, web, and desktop entry points with port-zero rendezvous

- **Observable result:** CLI, local web, and desktop launch the same feature services; the server
  binds port 0 and reports the actual authenticated rendezvous, eliminating bind-close-rebind races.
- **Anchors:** `src/scoutmb/interfaces/cli/`; `src/scoutmb/interfaces/web/`;
  `src/scoutmb/interfaces/desktop.py`; console scripts; `run_app.py`: `free_port`, `start_server`,
  `wait_until_ready`, `run`; local web status APIs.
- **Contract:** Entry points differ only in interaction adapter. Configuration resolution and exit
  semantics are shared and parity-tested.
- **Named tests:** `tests/parity/test_entrypoint_parity.py::test_legacy_cli_web_desktop_observables_match`;
  `tests/integration/test_entrypoint_parity.py::test_cli_web_desktop_share_services`;
  `tests/integration/test_rendezvous.py::test_port_zero_has_no_rebind_race`;
  `tests/integration/test_rendezvous.py::test_readiness_requires_session_nonce`.
- **Commands:** `uv run pytest tests/parity/test_entrypoint_parity.py tests/integration/test_entrypoint_parity.py tests/integration/test_rendezvous.py -q`;
  `uv run scoutmb doctor --offline`.
- **Expected:** Both commands exit 0; parallel launches receive distinct OS-assigned ports; doctor
  reports no live network use and no path/import mutation.
- **Recovery:** Abort the attempted launch without killing an unrelated process, keep the existing
  instance/rendezvous intact, and restore the prior entry adapter while fixing composition.

### B12 — Prove clean package and copied-release startup

- **Observable result:** Wheel and sdist install in clean environments; the launcher copies or
  installs `src/scoutmb`, package data, and compatibility entry points into a clean release root that
  starts without the repository present.
- **Anchors:** Hatchling build configuration; `bootstrap/source_sync.py`: `sync_app_source`;
  `bootstrap/build.spec`; package-data declarations.
- **Contract:** Source copy is a temporary bridge to packaged release payloads and cannot omit
  templates/static data. No release depends on repository layout.
- **Named tests:** `tests/packaging/test_distributions.py::test_wheel_installs_in_clean_environment`;
  `tests/packaging/test_distributions.py::test_archives_exclude_private_tests_logs_and_secrets`;
  `tests/packaging/test_distributions.py::test_wheel_rebuilt_from_sdist_passes_smoke`;
  `tests/packaging/test_release_root.py::test_copied_release_starts_without_repo`;
  `tests/packaging/test_distributions.py::test_expected_package_data_is_present`.
- **Commands:** `uv build`; `uv run python tools/inspect_distributions.py dist`;
  `uv run python tools/rebuild_wheel_from_sdist.py --dist dist --output build/from-sdist`;
  `uv run pytest tests/packaging/test_distributions.py tests/packaging/test_release_root.py -q`.
- **Expected:** All commands exit 0; both archives contain required package data and exclude
  `raw_data/`, private fixtures, tests, logs, tokens, and secrets; the original wheel and wheel rebuilt
  from sdist pass clean smoke tests with repository paths hidden/unmounted.
- **Recovery:** Keep the previously working source-copy manifest, correct package-data/build rules,
  rebuild from clean state, and do not add runtime fallbacks to repository files.

## Gate 2 — Identity, output, and runtime go/no-go

- **Observable result:** Phase B has a complete parity/privacy/failure-injection run and a recorded
  `GO`; any identity ambiguity, mixed output generation, leaked resource, insecure route, or clean
  install failure records `NO-GO` and blocks Phase C.
- **Named tests:** `tests/gates/test_gate_2.py::test_identity_output_runtime_manifest_is_complete`;
  all parity, privacy, lifecycle, security, architecture, and packaging tests from B1-B12.
- **Commands:** `uv run pytest tests/architecture tests/compat tests/parity tests/contracts tests/privacy tests/security tests/integration tests/packaging -m "not live_service" -q`;
  `uv run mypy --strict src/scoutmb`; `uv build`;
  `uv run python tools/check_private_data.py build/test-artifacts dist`.
- **Expected GO:** All commands exit 0; same-name attendees stay separate; missing identity fails
  closed; previous outputs survive injected failures; no sensitive value, leaked resource,
  unauthorized route, path mutation, or repository dependency remains.
- **Recovery / NO-GO:** Stop. Restore the relevant compatibility adapter as default, preserve failed
  generations privately, and return the defect to its B task. Waivers do not open the gate.

## Phase C — Installed data, migration, and transactional releases

This phase operates only on throwaway roots and snapshots until Gate 3. It never rehearses against
the sole live installation in place.

### C1 — Resolve and manage supported installed-data roots

- **Observable result:** The application proves a supported local data root, applies current-user
  permissions, exposes category sizes/retention/deletion, and safely backs up, restores, and prunes
  each locked retention class.
- **Anchors:** `bootstrap/paths.py`: `AppPaths`, `ensure_dirs`, `get_paths`;
  `src/scoutmb/ports/storage.py`; `src/scoutmb/adapters/files/`; retention, deletion, and backup services.
- **Contract:** Code/static paths never determine data paths. An operation-owned probe verifies
  exclusive create, locking, same-filesystem replace, and permission semantics; active network shares
  and removable roots fail with guidance. Terminal private runs retain 120 days, logs 45 days,
  staging 7 days, and resumable/recovery/report data until explicit eligible deletion. Cleanup is
  dry-run capable, never claims secure wipe, and restore never overwrites active state directly.
- **Named tests:** `tests/storage/test_data_roots.py::test_resolution_is_platform_and_code_location_independent`;
  `tests/storage/test_data_roots.py::test_unsupported_filesystem_capabilities_fail_with_guidance`;
  `tests/storage/test_permissions.py::test_current_user_permissions_on_supported_platforms`;
  `tests/storage/test_retention.py::test_retention_classes_and_protected_references`;
  `tests/storage/test_data_management.py::test_sizes_dates_and_explicit_deletion_contract`;
  `tests/integration/test_backup_restore.py::test_restore_is_staged_validated_and_private`.
- **Commands:** `uv run pytest tests/storage tests/integration/test_backup_restore.py -q`.
- **Expected:** Command exits 0; supported local roots pass capability and permission probes;
  unsupported active roots fail before mutation; UI/CLI report the same categories; dry-run, deletion,
  backup, and restore preserve every protected reference byte-for-byte.
- **Recovery:** Stop cleanup/activation, retain the backup and active root, quarantine invalid
  restore staging, and require explicit operator retry after diagnostics.

### C2 — Add OS-backed ownership, single-instance rendezvous, and activation

- **Observable result:** Exactly one launcher owns the installation; a second launch authenticates
  to the live rendezvous, requests foreground activation, and exits without starting another app.
- **Anchors:** `bootstrap/main.py`: `_acquire_lock`, `_release_lock`, `_launch_app`, `_run`;
  platform lock/activation adapters; rendezvous metadata.
- **Contract:** OS lock lifetime matches launcher ownership. PID-only evidence is insufficient;
  stale rendezvous data cannot authorize activation. macOS/Windows foreground limitations produce a
  truthful user-visible result.
- **Named tests:** `tests/launcher/test_single_instance.py::test_concurrent_launch_has_one_owner`;
  `tests/launcher/test_single_instance.py::test_second_launch_activates_authenticated_instance`;
  `tests/launcher/test_single_instance.py::test_os_denied_focus_requests_attention_without_duplicate`;
  `tests/launcher/test_single_instance.py::test_unresponsive_instance_fails_without_stealing_or_killing`;
  `tests/launcher/test_single_instance.py::test_read_only_and_mutating_cli_contention_matrix`;
  `tests/launcher/test_single_instance.py::test_crash_pid_reuse_stale_metadata_and_antivirus_delay`.
- **Commands:** `uv run pytest tests/launcher/test_single_instance.py -q`.
- **Expected:** Command exits 0 across repeated multi-process matrices; one owner starts; activation,
  OS-denied focus, and stale rendezvous return their documented outcomes; an unresponsive owner or
  mutating CLI returns stable `busy`/`unresponsive`; no duplicate app starts or unrelated process is signaled.
- **Recovery:** If ownership cannot be proven, do not launch or break the lock automatically. Show
  recovery guidance and preserve the lock/rendezvous evidence for diagnosis.

### C3 — Implement copy-only SHA-256 migration and activation marker

- **Observable result:** A throwaway legacy root is inventoried, copied into staging, collision-safe,
  SHA-256 verified, then activated with a versioned marker; interruption resumes safely and original
  files remain untouched.
- **Anchors:** `bootstrap/migrate.py`; data-root inventory and migration marker contracts;
  launcher startup composition.
- **Contract:** Never move/delete source data. Staging paths are unique siblings of final targets so
  replacement stays on one filesystem. Files are flushed/fsynced before verification and promotion;
  supported directory metadata is synchronized. Equal hashes deduplicate; unequal collisions receive
  deterministic preserved names. The versioned marker records roots, hashes, final/collision paths,
  application version, and time and is written last. The old root receives an explanatory location
  marker. A manual private backup receipt is required before the first production migration.
- **Named tests:** `tests/migration/test_copy_migration.py::test_source_is_never_modified`;
  `tests/migration/test_copy_migration.py::test_collision_and_hash_contract`;
  `tests/migration/test_copy_migration.py::test_sibling_staging_fsync_promotion_and_marker_contents`;
  `tests/migration/test_copy_migration.py::test_old_root_receives_explanatory_marker`;
  `tests/migration/test_copy_migration.py::test_each_interruption_point_resumes_idempotently`;
  `tests/migration/test_copy_migration.py::test_production_mode_requires_manual_backup_receipt`.
- **Commands:** `uv run pytest tests/migration/test_copy_migration.py -q`;
  `uv run scoutmb migrate --source build/legacy-root --destination build/new-root --dry-run`.
- **Expected:** Both commands exit 0; dry-run manifest is deterministic; source hashes are unchanged;
  staging/promotion/marker boundaries survive injection; activation and old-root markers reference the
  complete verified inventory and production mode cannot start without backup evidence.
- **Recovery:** Leave source and current active destination untouched, retain staging/manifest, and
  resume from the last verified item. Never delete a collision or write a success marker early.

### C4 — Detect split-brain writes on every launch and preserve recovery snapshots

- **Observable result:** Every launch while the legacy root exists detects writes before, during, or
  after cutover; changed state is snapshotted with hashes/provenance and mutation pauses for explicit
  operator reconciliation.
- **Anchors:** migration watcher/inventory service; recovery snapshot contract; diagnostics API.
- **Contract:** Detection is content/inventory based, not timestamp-only. The tool never guesses
  which divergent private file wins and never auto-merges generated reports.
- **Named tests:** `tests/migration/test_split_brain.py::test_legacy_write_after_activation_is_detected`;
  `tests/migration/test_split_brain.py::test_writes_before_and_during_cutover_are_detected`;
  `tests/migration/test_split_brain.py::test_every_launch_compares_source_to_cutover_manifest`;
  `tests/migration/test_split_brain.py::test_both_versions_are_preserved`;
  `tests/migration/test_split_brain.py::test_cleanup_stops_while_unresolved`.
- **Commands:** `uv run pytest tests/migration/test_split_brain.py -q`.
- **Expected:** Command exits 0; each divergent write creates a bounded redacted diagnostic and
  content-complete protected snapshots; active data is not silently changed.
- **Recovery:** Freeze cleanup and affected publication, keep both snapshots indefinitely, and
  require explicit reconciliation. Rescan hashes before resuming.

### C5 — Version durable state and enforce the activation compatibility tuple

- **Observable result:** Runs, checkpoints, settings, release metadata, and activation pointer carry
  schema versions; an activation tuple proves executable, state generation, capability set, and
  protocol compatibility before startup.
- **Anchors:** internal state contracts; `bootstrap/marker.py`: `compute_marker`, `read_marker`,
  `write_marker`, `is_environment_valid`; `current.json` contract.
- **Contract:** Current and previous release read the supported N/N-1 state window. Unknown/newer
  state fails closed before mutation. State upgrades stage and validate before pointer switch.
- **Named tests:** `tests/contracts/test_state_compatibility.py::test_n_and_n_minus_one_matrix`;
  `tests/contracts/test_state_compatibility.py::test_unknown_newer_schema_fails_before_write`;
  `tests/integration/test_activation_tuple.py::test_all_components_are_validated_together`.
- **Commands:** `uv run pytest tests/contracts/test_state_compatibility.py tests/integration/test_activation_tuple.py -q`.
- **Expected:** Command exits 0; incompatible tuples never launch; failed conversions preserve the
  old state generation and executable pointer.
- **Recovery:** Reactivate the last-known-good tuple atomically and retain failed staged state as a
  protected recovery snapshot. Do not downgrade state in place.

### C6 — Harden downloads, archives, disk budgets, and capability cache ownership

- **Observable result:** Downloads are streamed to staging, size/hash/content validated, archives
  reject traversal/link/device/expansion attacks, disk reserves are checked before writes, and cache
  eviction respects active/rollback capability references.
- **Anchors:** `bootstrap/downloader.py`: `download`; Python/browser/capability installers;
  safe-extraction and cache services.
- **Contract:** All remote payloads are declared in hash-bound release metadata even while code
  signing is deferred. Redirects revalidate scheme/host. Cleanup cannot evict active or rollback
  payloads.
- **Named tests:** `tests/launcher/test_downloader.py::test_stream_hash_size_and_redirect_policy`;
  `tests/security/test_safe_extract.py::test_hostile_archive_matrix`;
  `tests/launcher/test_disk_budget.py::test_active_and_rollback_reserve_is_enforced`;
  `tests/launcher/test_capability_cache.py::test_referenced_payloads_are_not_evicted`.
- **Commands:** `uv run pytest tests/launcher/test_downloader.py tests/security/test_safe_extract.py tests/launcher/test_disk_budget.py tests/launcher/test_capability_cache.py -q`.
- **Expected:** Command exits 0; hostile/oversized/mismatched inputs fail before activation; injected
  disk exhaustion leaves current install/cache valid and staging recoverable or cleaned.
- **Recovery:** Delete only verified unreferenced staging through the cache service, keep current and
  rollback payloads, and offer retry after sufficient disk/network availability.

### C7 — Install releases transactionally with readiness proof and rollback

- **Observable result:** A release installs into a versioned staging directory, validates package and
  state compatibility, launches with a one-time readiness nonce, then atomically switches
  `current.json`; any failure returns executable and state to the last-known-good tuple.
- **Anchors:** launcher release installer/activator; `bootstrap/main.py`: `_run`;
  `bootstrap/marker.py`; authenticated health/readiness endpoint.
- **Contract:** Readiness means the expected release, state generation, capability manifest, and
  nonce responded. Process-alive or open-port checks alone cannot activate a release.
- **Named tests:** `tests/launcher/test_transactional_update.py::test_each_failure_point_rolls_back_tuple`;
  `tests/launcher/test_transactional_update.py::test_readiness_nonce_and_release_identity`;
  `tests/launcher/test_transactional_update.py::test_offline_restart_uses_last_known_good`.
- **Commands:** `uv run pytest tests/launcher/test_transactional_update.py -q`.
- **Expected:** Command exits 0 for success and injected failures; pointer is always old or new valid
  JSON; after rollback the prior app starts and reads the restored state generation offline.
- **Recovery:** Atomically restore the last-known-good pointer and state generation, retain failed
  release diagnostics/staging within budget, and never mutate the working release in place.

## Gate 3 — Migration and release go/no-go

- **Observable result:** A throwaway copy of the live layout completes migrate, N-to-N+1 update,
  forced rollback, and N restart with a recorded `GO`; any source mutation, ownership ambiguity,
  corruption, split-brain loss, or rollback incompatibility records `NO-GO` and blocks Phase D.
- **Named tests:** `tests/gates/test_gate_3.py::test_migration_release_manifest_is_complete`;
  all storage, launcher, migration, state compatibility, and activation tests from C1-C7.
- **Commands:** `uv run pytest tests/storage tests/migration tests/launcher tests/contracts/test_state_compatibility.py tests/integration/test_backup_restore.py tests/integration/test_activation_tuple.py -q`;
  `uv run python tools/rehearse_upgrade.py --legacy-root build/gate3/legacy --work-root build/gate3/work --sequence N,N+1,N --require-backup-receipt build/gate3/backup.json`;
  `uv run python tools/check_private_data.py build/gate3/reports`.
- **Expected GO:** All commands exit 0; source hashes remain unchanged; simultaneous launchers have
  one owner; collisions and split-brain data are preserved; disk-full/interruption cannot corrupt
  active data; N restarts offline after rollback; reports are redacted.
- **Recovery / NO-GO:** Stop. Preserve the throwaway evidence and recovery snapshots, reactivate N,
  and return the failure to its C task. Do not run migration against the live installation.

## Phase D — Release channel, thin installers, optional capabilities, and operational hardening

Gate 3 permits release engineering to begin. Phase D has no fourth gate: D8 is final acceptance and
may complete only after every Phase D task and all three earlier gates are green.

### D1 — Split core, acquisition, browser, and PDF capability payloads

- **Observable result:** Core, ScoutingEvent acquisition, managed Chromium, and PDF/OpenCV payloads
  have separate manifests, dependency closures, cache identities, compatibility ranges, install
  states, and reference-counted removal rules; core imports with every optional payload absent.
- **Anchors:** optional dependencies in `pyproject.toml`; capability manifests; launcher capability
  installer/cache; interface composition capability registry.
- **Contract:** Playwright Python code and browser binaries are separate payloads. PDF/OpenCV is
  separate. Each test environment installs its declared extra explicitly. Capability activation is
  transactional and compatible with current and retained release/state tuples.
- **Named tests:** `tests/packaging/test_capability_split.py::test_core_has_no_optional_dependency_closure`;
  `tests/packaging/test_capability_split.py::test_each_extra_has_an_executed_test_environment`;
  `tests/launcher/test_capabilities.py::test_install_activate_remove_and_rollback`;
  `tests/contracts/test_capability_compatibility.py::test_release_ranges_fail_closed`.
- **Commands:** `uv sync --locked --all-groups --all-extras`;
  `uv run pytest tests/packaging/test_capability_split.py tests/launcher/test_capabilities.py tests/contracts/test_capability_compatibility.py -q`;
  `uv run python tools/build_capabilities.py --output build/capabilities`.
- **Expected:** Commands exit 0; manifests/hashes are deterministic; core starts offline without
  optional imports; each feature is exercised only in its declared environment and is unavailable
  until a compatible payload is atomically enabled.
- **Recovery:** Keep the prior compatible capability reference, quarantine the failed staging, and
  leave the feature unavailable with actionable diagnostics.

### D2 — Implement platform browser selection and readiness

- **Observable result:** Windows selects system Edge, then system Chrome, then managed Chromium;
  macOS selects system Chrome, then managed Chromium; Safari appears only as an explicit experimental
  `safaridriver` adapter with a truthful warning and no Playwright promise.
- **Anchors:** `bootstrap/browser_setup.py`: `probe_msedge_channel`,
  `install_chromium_fallback`, `resolve_browser_channel`; ScoutingEvent browser adapter and diagnostics.
- **Contract:** Presence is insufficient: the selected engine must complete a loopback-fake readiness
  transaction. Capability failures may follow the documented fallback order; authentication,
  validation, and schema failures may not be hidden by switching engines.
- **Named tests:** `tests/launcher/test_browser_selection.py::test_windows_preference_matrix`;
  `tests/launcher/test_browser_selection.py::test_macos_preference_and_experimental_safari`;
  `tests/integration/test_browser_readiness.py::test_selected_engine_completes_local_fake_flow`;
  `tests/integration/test_browser_readiness.py::test_auth_and_schema_failures_do_not_fallback`.
- **Commands:** `uv run pytest tests/launcher/test_browser_selection.py tests/integration/test_browser_readiness.py -q`.
- **Expected:** Command exits 0 for simulated platform matrices; supported choices pass the local fake;
  experimental/unsupported paths explain limitations; fallback never contacts the real service.
- **Recovery:** Fall back only in documented order, retain the prior compatible managed browser, and
  leave acquisition unavailable when readiness or a non-capability error fails.

### D3 — Assemble and validate the immutable release channel

```text
native Windows/macOS builds + versioned capability payloads
                            |
                            v
             immutable release-channel candidate
                            |
               validate metadata, size, and hashes
                            |
                            v
       local fake: install -> interrupted resume -> update -> offline restart
                            |
                            v
             exact D6 evidence + publication approval
                            |
                            v
                 controlled HTTPS artifact origin
```

- **Observable result:** Native core/capability artifacts become one immutable, hash-bound,
  provider-neutral release channel that supports first install, update, resume, and offline restart
  through a local fake before an approval-gated publication step.
- **Anchors:** `src/scoutmb/ports/releases.py`; `bootstrap/release_channel.py`;
  `tests/fakes/release_server.py`; `release/channel-schema.json`; `.github/workflows/release.yml`;
  release assembly/validation tools.
- **Contract:** A controlled HTTPS origin publishes exact locked platform payloads under immutable
  names. Manifests bind version, ABI, OS, architecture, lock digest, sizes, entry counts, companion
  capabilities, and every hash. Update checks have short deadlines, run at most daily, never block
  offline startup, and never resolve runtime dependencies from PyPI. Vendor selection stays outside
  the application contract.
- **Named tests:** `tests/release/test_release_channel.py::test_immutable_names_and_hash_bound_manifests`;
  `tests/release/test_update_policy.py::test_once_daily_deadline_bounded_nonblocking_check`;
  `tests/integration/test_release_server.py::test_first_install_resume_update_and_offline_restart`;
  `tests/ci/test_release_workflow.py::test_native_matrix_and_approval_gated_publication`.
- **Commands:** `uv run pytest tests/release/test_release_channel.py tests/release/test_update_policy.py tests/integration/test_release_server.py tests/ci/test_release_workflow.py -q`;
  `uv run python tools/assemble_release_channel.py --artifacts build/native-artifacts --capabilities build/capabilities --output build/release-channel`;
  `uv run python tools/validate_release_channel.py build/release-channel`.
- **Expected:** Commands exit 0; local fake flows pass with no external request; channel validation
  rejects mutable names, missing/incompatible metadata, escaping paths, size/hash mismatch, stale
  update state, and undeclared payloads; publication cannot run without the release environment approval.
- **Recovery:** Block publication, retain the last valid immutable channel, quarantine only the failed
  candidate, and rebuild all affected manifests/evidence from the exact lock.

### D4 — Build and verify native sub-18 MB Windows and macOS installers

- **Observable result:** A native Windows 11 x64 runner and native macOS 14+ arm64 runner each produce
  a thin installer at most 18 MB that installs core without system Python, can add capabilities, and
  restarts offline; unchanged Windows 10 x64 results remain best effort.
- **Anchors:** PyInstaller/launcher build definitions; platform bootstrap adapters; release metadata;
  CI jobs `launcher-windows` and `launcher-macos`.
- **Contract:** PyInstaller never cross-builds the other operating system. Installer contents exclude
  Playwright, browser binaries, OpenCV, PDF engines, and a wheelhouse. First install consumes only the
  validated release channel. D23 remains deferred and release notes state the internal-only trust model.
- **Named tests:** `tests/release/test_installer_budget.py::test_each_thin_installer_is_at_most_18_mb`;
  `tests/release/test_clean_machine.py::test_first_install_without_system_python_then_offline_restart`;
  `tests/release/test_platform_contract.py::test_supported_and_best_effort_metadata`;
  `tests/ci/test_release_workflow.py::test_each_installer_uses_a_native_runner`.
- **Commands:** Windows runner: `uv run python tools/build_installers.py --platform windows-x86_64 --output build/native/windows-x86_64`;
  macOS runner: `uv run python tools/build_installers.py --platform macos-arm64 --output build/native/macos-arm64`;
  aggregation runner: `uv run python tools/collect_native_artifacts.py --input build/native --output dist/installers`;
  `uv run pytest tests/release/test_installer_budget.py tests/release/test_platform_contract.py tests/ci/test_release_workflow.py -q`;
  Windows runner: `uv run python tools/rehearse_clean_install.py --artifact-dir build/native/windows-x86_64 --release-channel build/release-channel --without-system-python --offline-restart`;
  macOS runner: `uv run python tools/rehearse_clean_install.py --artifact-dir build/native/macos-arm64 --release-channel build/release-channel --without-system-python --offline-restart`.
- **Expected:** Every native and aggregation command exits 0; each installer is at most 18 MB; clean
  first launch downloads only core from the fake channel; optional payloads remain separate; egress-
  denied restart succeeds; Windows 10 failure is recorded without blocking supported targets.
- **Recovery:** Do not publish an oversized, cross-built, or failed artifact. Remove only operation-
  owned staging, retain last-known-good installers, and reduce launcher closure rather than raising the budget.

### D5 — Add redacted diagnostics and future telemetry protocols

- **Observable result:** Structured rotating logs, sanitized support bundles, versioned allowlisted
  event DTOs, `ObservabilityPort`, `NoopObservability`, and `TelemetrySpool` protocol operate with no
  telemetry dependency, durable spool, or network exporter in the shipped product.
- **Anchors:** `src/scoutmb/ports/observability.py`; `src/scoutmb/adapters/telemetry/` no-op adapter;
  `src/scoutmb/adapters/files/` diagnostics; log/retention configuration.
- **Contract:** Core never imports OpenTelemetry. Default observability is no-op. Event names and
  attributes forbid names, paths, URLs, upstream/run IDs, QR data, cookies, tokens, payloads, and
  report bodies. `TelemetrySpool` reserves bounded durable storage, IDs, at-least-once/deduplication,
  consent, and nonblocking failure semantics as a protocol only; production persistence/sync is future work.
- **Named tests:** `tests/observability/test_observability_port.py::test_default_noop_never_persists_or_uses_network`;
  `tests/observability/test_spool_protocol.py::test_fake_documents_future_sync_contract`;
  `tests/packaging/test_core_imports.py::test_core_does_not_import_opentelemetry`;
  `tests/privacy/test_diagnostics.py::test_support_bundle_and_event_schema_are_redacted`.
- **Commands:** `uv run pytest tests/observability tests/packaging/test_core_imports.py tests/privacy/test_diagnostics.py -q`;
  `uv run python tools/check_private_data.py build/support-bundles`.
- **Expected:** Commands exit 0; the default creates no telemetry record or network request;
  OpenTelemetry packages are absent from core; fake protocol tests pass; support bundles retain only
  allowlisted redacted diagnostics.
- **Recovery:** Keep `NoopObservability` selected, reject invalid event DTOs, and regenerate only the
  user-requested support bundle. Do not introduce a local spool as a repair.

### D6 — Produce exact release supply-chain evidence

- **Observable result:** Vulnerability results, approved licenses, per-payload CycloneDX SBOMs,
  archive/secret scans, artifact hashes, authoritative version, source revision, capability manifests,
  and native clean-build metadata form one reproducible release evidence bundle.
- **Anchors:** CI job `supply-chain`; `uv.lock`; `pyproject.toml`; release tooling, policies, and metadata.
- **Contract:** Evidence covers the exact core, launcher, and platform capability artifacts proposed
  for publication. Exceptions name owner, justification, control, and expiry. Build tools are pinned;
  `project.version` is authoritative. Hashes do not claim publisher authenticity while D23 is deferred.
- **Named tests:** `tests/release/test_evidence_bundle.py::test_bundle_covers_every_exact_payload`;
  `tests/release/test_evidence_bundle.py::test_version_and_build_metadata_have_one_source`;
  `tests/release/test_evidence_bundle.py::test_deferred_signing_is_stated_truthfully`.
- **Commands:** `uv audit`; `uv run python tools/check_licenses.py --policy release/license-policy.toml`;
  `uv run python tools/build_release_evidence.py --channel build/release-channel --installers dist/installers --capabilities build/capabilities --output build/evidence/release`;
  `uv run pytest tests/release/test_evidence_bundle.py -q`.
- **Expected:** Commands exit 0; evidence references every exact artifact hash, lock digest, build-tool
  version, git revision, license, and SBOM; no unreviewed finding remains; signing is `deferred-internal`.
- **Recovery:** Block publication, keep the last clean evidence bundle, update/remove the affected
  dependency or artifact, rebuild natively from the lock, and regenerate the entire bundle.

### D7 — Lock measured resource and performance limits

- **Observable result:** Release configuration contains measured non-placeholder limits for uploads,
  PDF pages/image dimensions, parse time/memory, archives, jobs/workers, queue depth, shutdown grace,
  cache/disk reserve, startup, request counts, runtime, installer size, and installed footprint.
- **Anchors:** typed configuration limits; `tools/measure_baseline.py`; performance CI job; synthetic
  corpus and optional private-corpus runner.
- **Contract:** Request counts and algorithmic growth are hard assertions. Controlled wall-time jobs
  compare repeated samples on named machine classes with explicit variance and regression thresholds.
  Hypothesis covers parsers, state transitions, archive paths, and publication failure boundaries.
- **Named tests:** `tests/performance/test_resource_limits.py::test_every_release_limit_is_bounded`;
  `tests/performance/test_complexity.py::test_request_and_memory_growth`;
  `tests/performance/test_regression_policy.py::test_machine_variance_and_thresholds_are_explicit`;
  `tests/property/test_foundation_properties.py::test_parsers_states_archives_and_publication_invariants`.
- **Commands:** `uv run pytest tests/performance tests/property/test_foundation_properties.py -q`;
  `uv run python tools/measure_baseline.py --corpus synthetic --repetitions 5 --machine-class controlled --compare build/baseline.json --output build/release-baseline.json`.
- **Expected:** Commands exit 0 on the controlled runner; every limit records value, unit, measurement,
  machine class, variance, threshold, headroom rationale, safe range, and failure behavior; no hard or
  tolerant regression exceeds policy.
- **Recovery:** Keep prior measured limits, reject the candidate, profile the regressed path, and
  rerun on the same machine class. Do not widen limits without new evidence and review.

### D8 — Final acceptance, documentation, and legacy retirement

- **Observable result:** All three gate records and D1-D7 are green; current documentation lets an
  operator install, update, recover, migrate, manage/delete retained data, run offline, add/remove
  capabilities, create redacted diagnostics, and invoke the explicit staging smoke; redundant legacy
  implementation is removed while compatibility entry points remain for the transition window.
- **Anchors:** `README.md`; install/update/recovery/migration/privacy/data-management documentation;
  `CLAUDE.md`; `AGENTS.md`; compatibility entry points; release checklist.
- **Contract:** No default command or automated test contacts the real service. The sole live smoke is
  read-only, manual/staging, marked `live_service`, and requires two-part opt-in. D23 is a deferred
  follow-up before distribution expands. The first real migration requires a verified manual backup.
- **Named tests:** `tests/acceptance/test_documented_commands.py::test_all_documented_offline_commands`;
  `tests/acceptance/test_release_contract.py::test_three_gates_and_phase_d_evidence_are_green`;
  `tests/acceptance/test_legacy_retirement.py::test_compatibility_entrypoints_contain_no_business_logic`;
  `tests/acceptance/test_no_live_service.py::test_only_manual_two_part_opt_in_can_reach_real_service`.
- **Commands:** `uv sync --locked --all-groups --all-extras`; `uv run ruff check .`;
  `uv run ruff format --check .`; `uv run mypy --strict src/scoutmb`; `uv audit`;
  `uv run pytest -m "not live_service" --cov=src/scoutmb --cov-branch -q`; `uv build`;
  `uv run python tools/verify_release.py --channel build/release-channel --evidence build/evidence/release --installers dist/installers --capabilities build/capabilities`.
- **Expected:** Every command exits 0; branch/package thresholds meet policy; wheel, sdist, channel,
  native installers, capabilities, and evidence verify; all offline flows work; no stale implementation,
  sensitive artifact, unexpected skip, network escape, placeholder limit, or unresolved decision remains.
- **Recovery:** Do not publish or migrate the live installation. Restore the last-known-good release
  bundle, return the failure to its owning task, and rerun D8 in full after repair.

## Specification-to-plan trace

Every locked decision has one or more owning tasks and becomes gate evidence where applicable.

| Decision | Owning tasks/gates | Execution evidence |
| --- | --- | --- |
| D1 | A1-D8, G1-G3 | One ordered plan, three blocking gates, D8 acceptance |
| D2 | B12, C7 | Source-copy bridge and clean-root startup before transactional payload installation |
| D3 | B6, G2 | Typed upstream identity, fail-closed boundary, UUIDv4 output identity |
| D4 | A1, A2, G1 | Canonical lock, Python pin, hashed launcher export, drift checks |
| D5 | C3, C4, G3 | Copy-only verified migration, marker-last activation, split-brain preservation |
| D6 | C1 | Explicit/platform data-root resolution and filesystem capability probe |
| D7 | A5 | Deterministic synthetic-only committed fixtures and privacy tripwire |
| D8 | A7-A10, G1 | Complete legacy input, acquisition, inference, UI, bootstrap, and lifecycle matrix |
| D9 | A4, D8 | Default-deny tests and explicit two-part live-smoke opt-in |
| D10 | A2, G1, G2, D8 | Honest branch baseline, no regression, package thresholds, correctness gates |
| D11 | B7, B8, G2 | Exact single-file failure matrix and immutable generation publication |
| D12 | A6 | `pytest --corpus-dir raw_data`, manifest lock, redacted additive corpus |
| D13 | B3-B11, G2 | Legacy/new normalized parity and reviewed intentional-change manifest |
| D14 | B6-B8, G2 | Sensitive upstream identity/tokens excluded from shareable artifacts |
| D15 | B12, G2 | Wheel/sdist inspection, clean wheel install, wheel rebuilt from sdist |
| D16 | B2, B7, B8 | Versioned external DTOs, goldens, future-version rejection |
| D17 | C5-C7, D3 | Immutable release/state generations, readiness, atomic tuple rollback |
| D18 | D1, D3, D4 | Sub-18 MB thin installers and separate capability downloads |
| D19 | B1-B11 | Core/features/ports/adapters/interfaces/runtime boundaries and vertical slices |
| D20 | D5 | No-op observability, redacted schema, future spool protocol only |
| D21 | A9, D7 | Repeated baselines before measured controlled thresholds |
| D22 | A8, B4, B5, D2 | ScoutingEvent gateway, schema drift, bounded acquisition, browser readiness |
| D23 | D4, D6, D8 | Signing deferred, integrity claims bounded, broader-distribution revisit documented |
| D24 | Every task and sidecar | One observable, named tests, commands, expected result, recovery, digest check |
| D25 | B6 | Full per-run UUIDv4, resumable within run, unlinkable across runs |
| D26 | C4, G3 | Every-launch legacy hash comparison and protected recovery snapshots |
| D27 | A4, G1 | Python, application, browser-context, and browser-process egress denial |
| D28 | C5, C7, G3 | Versioned durable state, N/N-1 window, N-to-N+1-to-N recovery |
| D29 | C2, G3 | OS lock, authenticated activation, focus/unresponsive/CLI/crash matrices |
| D30 | A10, B10, G2 | Authenticated loopback, Host/Origin/CSRF, streaming uploads, containment, CSP |
| D31 | C1, D8 | Permissions, locked retention periods, visible management and explicit deletion |
| D32 | B2, B5, B9 | UTC/monotonic clocks, structured ownership, cancellation cleanup |
| D33 | B9, C5, G2 | Versioned legal run-state transitions, recovery, publication eligibility |
| D34 | A3, D1-D4 | Supported platform metadata and capability compatibility/native release matrix |
| D35 | A10, C1, C6, D7 | Parser/archive/download/disk/worker budgets and safe exhaustion behavior |
| D36 | A3, D6 | Phase A baseline and exact release vulnerability/license/SBOM/build evidence |

## Failure-mode coverage

| Path | Injected failure | Named coverage | Required behavior |
| --- | --- | --- | --- |
| Input/PDF import | Malformed row, QR miss, missing capability, oversized document | A7, B3, D1, D7 | Typed bounded error; no eager optional import; no partial attendee file |
| ScoutingEvent | Redirect, auth expiry, schema drift, timeout, cancellation | A4, A8, B4, B5 | Revalidate, fail closed, bounded retry, redact, close session |
| Identity/inference | Same names, blank/malformed ID, resume | B6 | Never merge; reject missing identity; keep full run UUIDv4 stable only within run |
| Single artifact | Render/write/flush/fsync/close/replace/directory-fsync failure | B7 | Prior bytes remain or durability is explicitly indeterminate after replace; never overwrite twice |
| Report generation | Artifact, manifest, pointer, or hostile consumer failure | B8 | Readers see one validated generation; malformed/escaping/hash-mismatched input fails closed |
| Local web | Forged Host/Origin/CSRF, traversal, oversized/slow upload | B10 | Reject before state change; bounded memory/time; redacted response |
| Jobs | Illegal transition, crash, timeout, shutdown | B9 | Persist legal state; own/cancel children; leave resumable checkpoint |
| Ownership | Simultaneous/stale/unresponsive owner, focus denial, PID reuse, CLI contention | C2 | One owner; authenticated activation/attention or stable busy error; never steal/kill/duplicate |
| Data root | Unsupported filesystem, permission failure, protected deletion | C1 | Fail before mutation; show active root and eligible actions; preserve protected data |
| Migration | Collision, interruption, race, disk full, legacy write | C3, C4 | Source untouched; same-filesystem verified promotion; preserve both; pause mutation/cleanup |
| Update | Bad hash/archive, readiness failure, incompatible state | C5-C7 | No activation or atomic rollback of executable and state tuple |
| Capabilities | Missing/incompatible/corrupt payload | D1, D2 | Core stays usable; prior capability retained; feature truthfully unavailable |
| Release channel | Mutable/missing/incompatible metadata, timeout, stale update state | D3 | Reject candidate; keep offline startup and last immutable channel usable |
| Native installer | Cross-build, missing system Python, oversized closure, offline restart | D4 | Build only on target runner; reject artifact; keep last-known-good installer |
| Diagnostics | Sensitive value, invalid event DTO, accidental exporter dependency | D5 | Reject/redact; keep no-op; application data and network state unaffected |
| Supply chain | Vulnerability, license, secret, archive, or evidence mismatch | A3, D6 | Block movement/publication and regenerate exact evidence from the lock |
| Resource limits | Queue/cache/disk/memory/time budget exceeded | C6, D7 | Reject or pause safely with actionable bounded diagnostics |

## CI growth by phase

| Phase | Jobs required by phase completion |
| --- | --- |
| A | `lint-format`, `types`, `lock`, `supply-chain`, `unit-contract`, explicit capability environments, `local-playwright`, `egress-denied` |
| B | A jobs plus `local-web-security`, `package`, `architecture` |
| C | B jobs plus `launcher-windows`, `launcher-macos` migration/update slices |
| D | Full platform launcher matrices, `supply-chain`, `performance`; local-only `private-corpus`; manual-only `live-smoke` |

## Implementation task index

| ID | Observable result | Blocked by |
| --- | --- | --- |
| A1 | Reproducible Python 3.12 package and lock | — |
| A2 | Green quality/lock/capability-environment CI | A1 |
| A3 | Supply-chain and platform baseline | A1 |
| A4 | Offline-by-default enforcement | A1 |
| A5 | Synthetic factories and privacy tripwire | A4 |
| A6 | Optional private-corpus verifier | A5 |
| A7 | Input/PDF contract matrix | A5 |
| A8 | Local-fake ScoutingEvent contract matrix | A4, A5 |
| A9 | Inference/artifact/interface/performance matrix | A5, A7, A8 |
| A10 | Bootstrap/local-web/lifecycle/static-UI matrix | A4, A5 |
| G1 | Characterization GO | A2-A10 |
| B1 | Package boundaries and shims | G1 |
| B2 | Typed core contracts | B1 |
| B3 | Input/PDF adapter parity | B1, B2, A7 |
| B4 | Session gateway and drift detection | B1, B2, A8 |
| B5 | Bounded acquisition service | B2, B4 |
| B6 | Correct attendee identity | B2, A9 |
| B7 | Versioned atomic artifacts | B2, B6, A9 |
| B8 | Atomic report generations | B7 |
| B9 | Durable run supervisor | B2, A10 |
| B10 | Secure local web boundary | B3, B5, B8, B9, A10 |
| B11 | Entrypoint parity and rendezvous | B10 |
| B12 | Clean distributions and release root | B1, B11 |
| G2 | Identity/output/runtime GO | B3-B12 |
| C1 | Data roots, retention, backup/restore | G2 |
| C2 | OS ownership and activation | G2, B11 |
| C3 | Copy/hash migration | C1, C2 |
| C4 | Split-brain preservation | C3 |
| C5 | State/activation compatibility | C1 |
| C6 | Safe downloads/cache/disk budgets | C2 |
| C7 | Transactional release and rollback | C2, C5, C6 |
| G3 | Migration/release GO | C3-C7 |
| D1 | Optional capability payloads | G3 |
| D2 | Platform browser selection | D1, B4 |
| D3 | Immutable release channel | D1, D2, C7 |
| D4 | Native sub-18 MB platform installers | D3 |
| D5 | Offline diagnostics and telemetry protocols | G3, B9 |
| D6 | Exact release supply-chain evidence | D3-D5 |
| D7 | Measured resource/performance limits | D1-D5 |
| D8 | Final acceptance and legacy retirement | D4-D7 |

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
| --- | --- | --- | ---: | --- | --- |
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | NOT RUN | — |
| Codex Review | `/codex review` | Independent second opinion | 0 | NOT RUN | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 2 | CLEAR (PLAN) | 8 issues, 0 critical gaps; all corrections folded into the plan and sidecar |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | NOT RUN | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | NOT RUN | — |

**VERDICT:** ENG CLEARED — ready to implement

NO UNRESOLVED DECISIONS
