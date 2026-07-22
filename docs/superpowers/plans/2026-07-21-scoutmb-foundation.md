# ScoutMB Foundation Execution Plan

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
valid only when `planSha256` matches this file. An executor must stop if the hashes differ.

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
- Automatic telemetry upload; Phase D provides only an offline-safe OpenTelemetry seam and spool.
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
     ports + pure domain policies
        /                    \
input/PDF adapters     ScoutingEvent adapter
storage/artifacts      browser/session adapter
                 |
       explicit composition roots
```

Rules enforced by architecture tests:

- Domain and ports import no adapters, UI, bootstrap, Playwright, OpenCV, or PDF library.
- Feature services depend on ports and typed DTOs, never global filesystem or network state.
- Adapters may depend inward; composition roots select adapters and own resource lifetimes.
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

- Phase A characterization tasks A4-A8 may proceed in parallel after A1-A3, but they must not edit
  the same fixture or shared test configuration concurrently.
- After Gate 1, the gateway/acquisition lane (B4-B5), identity/output lane (B6-B8), and runtime lane
  (B9-B11) may proceed concurrently once their declared dependencies are satisfied.
- Phase C is intentionally conservative: storage and ownership land before migration and release
  activation. Do not parallelize edits to bootstrap state, locks, or activation metadata.
- After Gate 3, capabilities/browser work (D1-D3), observability (D4), and supply-chain evidence
  (D5) may proceed in parallel. D6 and D7 integrate those results.

## Phase A — Tooling and complete characterization

Production behavior stays in place. This phase creates a reproducible environment, an offline test
boundary, synthetic/private fixture paths, and a complete contract matrix.

### A1 — Establish Python 3.12 project metadata and the canonical lock

- **Observable result:** A Hatchling `src/` project syncs reproducibly from `uv.lock`, the launcher
  requirements export is derived from that lock, and the installed package imports without path
  manipulation.
- **Anchors:** `pyproject.toml`; `uv.lock`; `bootstrap/requirements-launcher.txt`; `.gitignore`.
- **Contract:** Core, optional capability, and development dependencies are separate. The export
  contains runtime dependencies only and never becomes a second source of dependency truth.
- **Named tests:** `tests/packaging/test_project_metadata.py::test_python_and_build_contract`;
  `tests/packaging/test_project_metadata.py::test_launcher_export_matches_lock`.
- **Commands:** `uv lock --check`; `uv sync --locked --all-groups`;
  `uv export --locked --no-dev --no-emit-project --format requirements.txt --output-file bootstrap/requirements-launcher.txt`;
  `uv run pytest tests/packaging/test_project_metadata.py -q`.
- **Expected:** Every command exits 0; the export has no diff after regeneration; Python reports
  3.12; `import scoutmb` resolves from the installed editable package.
- **Recovery:** If resolution or export is not reproducible, do not hand-edit exported pins. Correct
  project groups/markers, regenerate `uv.lock`, and rerun all four commands.

### A2 — Add green quality and lock CI jobs

- **Observable result:** `lint-format`, `types`, `lock`, and an initially narrow `unit-contract` job
  run on every pull request and pass on supported Python.
- **Anchors:** `.github/workflows/ci.yml`; Ruff, mypy, pytest, and coverage configuration in
  `pyproject.toml`.
- **Contract:** Every introduced job is green when merged. Branch coverage is recorded honestly;
  thresholds rise with new code instead of hiding the baseline.
- **Named tests:** `tests/ci/test_workflow_contract.py::test_phase_a_jobs_are_required`;
  `tests/ci/test_workflow_contract.py::test_ci_uses_locked_sync`.
- **Commands:** `uv run ruff check .`; `uv run ruff format --check .`;
  `uv run mypy src tests`; `uv run pytest tests/ci/test_workflow_contract.py -q`.
- **Expected:** All commands exit 0; the workflow uses Python 3.12 and `uv sync --locked`; no job
  performs a live-service smoke test.
- **Recovery:** If existing code blocks strict typing, scope documented mypy overrides to legacy
  modules only. Do not disable checks for `src/scoutmb` or allow a red CI job.

### A3 — Enforce offline-by-default tests and application egress policy

- **Observable result:** Any default test attempt to reach a non-loopback address, including from
  Playwright redirects, workers, frames, popups, WebSockets, or a browser subprocess, fails with a
  named policy error before private data leaves the process.
- **Anchors:** `tests/conftest.py`; `src/scoutmb/network_policy.py`; `.github/workflows/ci.yml` jobs
  `local-playwright` and `egress-denied`.
- **Contract:** Loopback fake services are permitted. `scoutingevent.com` requires the explicit
  staging/live marker and environment opt-in; the default constructor cannot create that gateway.
- **Named tests:** `tests/network/test_offline_policy.py::test_non_loopback_socket_is_blocked`;
  `tests/network/test_offline_policy.py::test_live_gateway_requires_two_part_opt_in`;
  `tests/integration/test_browser_egress.py::test_all_browser_request_surfaces_are_guarded`.
- **Commands:** `uv run pytest tests/network tests/integration/test_browser_egress.py -q`;
  `uv run pytest -m "not live_service" -q`.
- **Expected:** Both commands exit 0; sentinels record zero non-loopback requests; deliberately
  injected external URLs fail with `ExternalNetworkBlocked`.
- **Recovery:** Disable the new network adapter, keep the local fake path, and repair the missing
  guard. Never recover by allowlisting the real host in default tests.

### A4 — Create synthetic factories and a repository privacy tripwire

- **Observable result:** The committed test corpus covers distinct/same names, IDs, tokens,
  requirement shapes, malformed payloads, and output trees using demonstrably synthetic values;
  the suite fails if likely private data is introduced.
- **Anchors:** `tests/factories/`; `tests/fixtures/synthetic/`; `tests/privacy/test_fixture_hygiene.py`.
- **Contract:** Factories are deterministic when seeded but UUIDv4 assertions validate version and
  uniqueness, not fixed values. No fixture is generated by copying private files into the tree.
- **Named tests:** `tests/privacy/test_fixture_hygiene.py::test_committed_fixtures_are_synthetic`;
  `tests/factories/test_record_factories.py::test_identity_edge_cases_are_representable`.
- **Commands:** `uv run pytest tests/factories tests/privacy/test_fixture_hygiene.py -q`;
  `uv run python tools/check_private_data.py tests`.
- **Expected:** Both commands exit 0; the scanner prints `private-data findings: 0` and never echoes
  the matched source text.
- **Recovery:** Quarantine the new fixture outside the repository, improve the factory or scanner,
  and rerun. Do not add real values to an allowlist.

### A5 — Add optional private-corpus verification

- **Observable result:** When local `raw_data/` exists, one command runs the same contract corpus in
  addition to synthetic tests and emits only counts, hashes of fixture definitions, and redacted
  failures; absence is an explicit skip rather than a failure.
- **Anchors:** `tools/verify_private_corpus.py`; `tests/tools/test_private_corpus.py`; pytest option
  `--private-corpus`.
- **Contract:** The tool is read-only, never creates committed fixtures, rejects paths outside the
  supplied root, and never sends network traffic.
- **Named tests:** `tests/tools/test_private_corpus.py::test_absent_corpus_skips_explicitly`;
  `tests/tools/test_private_corpus.py::test_output_is_aggregate_and_redacted`;
  `tests/tools/test_private_corpus.py::test_corpus_run_is_offline`.
- **Commands:** `uv run pytest tests/tools/test_private_corpus.py -q`;
  `uv run pytest --private-corpus raw_data -m private_corpus -q`.
- **Expected:** Tool tests exit 0. The corpus command exits 0 with either `private corpus: PASS` or
  `private corpus: SKIPPED (not present)` and contains no attendee names, IDs, tokens, or URLs.
- **Recovery:** Stop at the first redaction failure, delete only tool-created temporary summaries,
  preserve `raw_data/` untouched, and repair the verifier before rerunning.

### A6 — Characterize every input and PDF extraction contract

- **Observable result:** A table-driven suite pins XLSX, CSV, JSON, text, directory/glob expansion,
  field aliases, deduplication, QR decode variants, attendee CSV order, and failure messages.
- **Anchors:** `scout_schedule_cli.py`: `load_inputs`, `load_xlsx`, `load_csv`, `load_json`,
  `load_text`; `pdf_to_scouts.py`: `expand_pdf_inputs`, `decode_embedded_qr`, `extract_pdf`,
  `write_attendees_csv`.
- **Contract:** Tests describe current observable behavior, including known awkward cases, without
  fixing them in this task. PDF/OpenCV imports remain optional at runtime.
- **Named tests:** `tests/characterization/test_input_matrix.py::test_all_supported_input_shapes`;
  `tests/characterization/test_pdf_matrix.py::test_pdf_decode_and_error_matrix`;
  `tests/characterization/test_pdf_matrix.py::test_attendee_csv_schema_is_stable`.
- **Commands:** `uv run pytest tests/characterization/test_input_matrix.py tests/characterization/test_pdf_matrix.py -q`.
- **Expected:** Command exits 0; each locked-spec matrix row names its fixture and observable; no
  test opens a browser or imports unavailable optional libraries eagerly.
- **Recovery:** Correct a mistaken expectation from observed legacy output. Do not alter production
  parsing until the matrix is reviewed and green.

### A7 — Characterize ScoutingEvent and browser-session behavior against a local fake

- **Observable result:** A loopback fake reproduces login/session responses, payload shapes,
  redirects, schema drift, retryable/terminal errors, and request counting without contacting the
  real service.
- **Anchors:** `scout_schedule_cli.py`: `navigate_and_trigger_schedule`, `post_requirement`,
  `process_scout`; `tests/fakes/scoutingevent_service.py`.
- **Contract:** The fake models only observed contracts and has a request ledger. Tests pin current
  retries and deduplication while reserving intentional changes for Phase B.
- **Named tests:** `tests/characterization/test_scoutingevent_contract.py::test_observed_payload_matrix`;
  `tests/characterization/test_scoutingevent_contract.py::test_current_retry_and_error_matrix`;
  `tests/characterization/test_browser_session.py::test_redirects_and_cookies_stay_in_session`.
- **Commands:** `uv run pytest tests/characterization/test_scoutingevent_contract.py tests/characterization/test_browser_session.py -q`.
- **Expected:** Command exits 0; fake request counts match assertions; external-request sentinel
  remains zero; schema variants are named fixtures rather than inline large payloads.
- **Recovery:** Extend the local fake with the missing observed shape. Never capture a new live
  response in an automated test or weaken the egress policy.

### A8 — Characterize inference, artifacts, interfaces, and baseline performance

- **Observable result:** The remaining legacy matrix pins requirement-path parsing, inference and
  both consumers, non-mutation, CSV/JSON/HTML/email schemas, CLI/UI defaults, errors, request counts,
  startup, runtime, memory, and artifact sizes.
- **Anchors:** `scout_schedule_cli.py`: `requirement_path`, `annotate_requirement_statuses`,
  `build_missing_requirements`, `write_email_reports`, `write_outputs`; `ui/server.py` API routes;
  `run_app.py`: `run`.
- **Contract:** Same-name merging is recorded as a known defect to be replaced in B6. Wall-clock
  numbers are descriptive baselines; request counts and growth are hard assertions.
- **Named tests:** `tests/characterization/test_inference_matrix.py::test_requirement_and_consumer_matrix`;
  `tests/characterization/test_artifact_matrix.py::test_all_output_schemas_and_failures`;
  `tests/characterization/test_interface_matrix.py::test_cli_web_desktop_defaults`;
  `tests/performance/test_baseline.py::test_request_count_growth_is_bounded`.
- **Commands:** `uv run pytest tests/characterization tests/performance/test_baseline.py -q`;
  `uv run python tools/measure_baseline.py --corpus synthetic --output build/baseline.json`.
- **Expected:** Tests exit 0; the measure command creates redacted `build/baseline.json` with machine
  class, corpus revision, repeated samples, request counts, memory, sizes, and no placeholders.
- **Recovery:** Keep the measurement non-blocking for wall time, fix missing observables, and rerun.
  Do not proceed to package movement while a correctness matrix row is absent or red.

## Gate 1 — Characterization go/no-go

- **Observable result:** Phase A has one reproducible, offline, privacy-safe evidence run and a
  recorded `GO`; any missing matrix row or failing command records `NO-GO` and blocks Phase B.
- **Named tests:** `tests/gates/test_gate_1.py::test_characterization_manifest_is_complete`;
  every named test from A1-A8.
- **Commands:** `uv sync --locked --all-groups`; `uv run ruff check .`;
  `uv run ruff format --check .`; `uv run mypy src tests`;
  `uv run pytest -m "not live_service" --cov=src/scoutmb --cov-branch -q`;
  `uv run python tools/check_private_data.py tests build/baseline.json`.
- **Expected GO:** All commands exit 0; all matrix rows are accounted for; no non-loopback request
  or private-data finding occurs; lock/export checks and baselines are reproducible.
- **Recovery / NO-GO:** Stop. Assign the failing evidence to its Phase A task, preserve legacy
  production behavior, and rerun the entire gate after repair. Waivers do not open the gate.

## Phase B — Package boundaries, identity, outputs, and local runtime

Phase B moves behavior behind ports in small slices. Compatibility entry points remain available
until final acceptance, and parity runs after each move.

### B1 — Introduce package boundaries and compatibility entry points

- **Observable result:** `scoutmb` has domain, ports, features, adapters, and composition packages;
  legacy top-level scripts delegate to package entry points; no first-party code mutates
  `sys.path`.
- **Anchors:** `src/scoutmb/`; `scout_schedule_cli.py`; `pdf_to_scouts.py`; `ui/server.py`;
  `run_app.py`; console scripts in `pyproject.toml`.
- **Contract:** This is mechanical movement only. Compatibility wrappers preserve arguments, exit
  codes, and output. Reverse imports and cycles fail architecture tests.
- **Named tests:** `tests/architecture/test_dependency_rules.py::test_hexagonal_import_direction`;
  `tests/architecture/test_dependency_rules.py::test_no_first_party_sys_path_mutation`;
  `tests/compat/test_legacy_entrypoints.py::test_legacy_entrypoints_delegate_with_parity`.
- **Commands:** `uv run pytest tests/architecture tests/compat/test_legacy_entrypoints.py -q`;
  `uv run python -m scoutmb --help`; `uv run scoutmb --help`.
- **Expected:** All commands exit 0; both help outputs retain the characterized contract; imports
  work from an installed package without repository-root assumptions.
- **Recovery:** Keep the compatibility wrapper as the active path, move one symbol group back, and
  restore parity. Do not add a path mutation or duplicate logic in the wrapper.

### B2 — Establish typed domain, clocks, errors, configuration, and DTO versions

- **Observable result:** Pure immutable models represent attendees, classes, requirements, runs,
  artifact generations, typed errors, versioned DTOs, UTC wall time, and monotonic deadlines.
- **Anchors:** `src/scoutmb/domain/`; `src/scoutmb/ports/clock.py`;
  `src/scoutmb/config.py`; `src/scoutmb/errors.py`; `src/scoutmb/contracts/`.
- **Contract:** Parsing occurs at boundaries; core policies use typed values. Wall time is persisted;
  elapsed time and deadlines use the monotonic clock.
- **Named tests:** `tests/unit/domain/test_models.py::test_invalid_states_are_unrepresentable`;
  `tests/unit/test_clocks.py::test_deadlines_ignore_wall_clock_changes`;
  `tests/contracts/test_dto_versions.py::test_unknown_versions_fail_closed`.
- **Commands:** `uv run pytest tests/unit/domain tests/unit/test_clocks.py tests/contracts/test_dto_versions.py -q`;
  `uv run mypy --strict src/scoutmb/domain src/scoutmb/ports src/scoutmb/contracts`.
- **Expected:** Both commands exit 0; domain tests require no filesystem, network, browser, UI, or
  system clock.
- **Recovery:** Remove the incomplete DTO from composition, keep boundary dictionaries behind the
  legacy adapter, and repair typed construction without weakening strict checks.

### B3 — Move input and PDF work behind ports with parity

- **Observable result:** Input loading and PDF extraction are adapter implementations selected by
  feature services; core-only installation can load non-PDF inputs without importing PDF/OpenCV
  dependencies.
- **Anchors:** `src/scoutmb/features/import_attendees/`; `src/scoutmb/adapters/input/`;
  `src/scoutmb/adapters/pdf/`; legacy loader and PDF symbols characterized in A6.
- **Contract:** Adapter DTOs preserve field aliases, ordering, deduplication, and errors. Optional
  dependency absence produces a capability message, not an import crash.
- **Named tests:** `tests/parity/test_input_adapter_parity.py::test_full_input_matrix_matches_legacy`;
  `tests/parity/test_pdf_adapter_parity.py::test_pdf_matrix_matches_legacy`;
  `tests/packaging/test_core_imports.py::test_core_does_not_import_pdf_or_opencv`.
- **Commands:** `uv run pytest tests/parity/test_input_adapter_parity.py tests/parity/test_pdf_adapter_parity.py tests/packaging/test_core_imports.py -q`.
- **Expected:** Command exits 0; legacy and new DTO projections match for every A6 fixture; core-only
  import succeeds with optional libraries absent.
- **Recovery:** Select the legacy adapter in composition and fix one matrix mismatch at a time. Do
  not make PDF/OpenCV core dependencies.

### B4 — Implement the ScoutingEvent session gateway and schema-drift boundary

- **Observable result:** One adapter owns the attendee session, URL allowlist, payload validation,
  schema profiles, redaction, and drift diagnostics while feature code sees only typed port DTOs.
- **Anchors:** `src/scoutmb/ports/scoutingevent.py`;
  `src/scoutmb/adapters/scoutingevent/`; `tests/fakes/scoutingevent_service.py`.
- **Contract:** Only HTTPS approved host/path combinations are valid outside tests. Redirects and
  discovered URLs are revalidated. Unknown/missing fields fail closed with redacted bounded samples.
- **Named tests:** `tests/contracts/test_scoutingevent_gateway.py::test_observed_profiles_validate`;
  `tests/contracts/test_scoutingevent_gateway.py::test_schema_drift_fails_closed_and_redacts`;
  `tests/security/test_url_allowlist.py::test_redirect_and_discovered_url_are_revalidated`.
- **Commands:** `uv run pytest tests/contracts/test_scoutingevent_gateway.py tests/security/test_url_allowlist.py -q`.
- **Expected:** Command exits 0; local fake profiles pass; drift cases return typed errors; diagnostics
  contain no cookies, tokens, upstream IDs, or raw payload bodies.
- **Recovery:** Keep the legacy local-fake adapter selected, store only redacted drift metadata, and
  add a reviewed schema profile. Never fall back to permissive parsing.

### B5 — Add bounded acquisition retries, deadlines, checkpoints, and a circuit breaker

- **Observable result:** The acquisition service bounds attempts and elapsed time, deduplicates
  requests, checkpoints resumable progress, stops on terminal schema/auth errors, and closes all
  attendee-session resources.
- **Anchors:** `src/scoutmb/features/acquire_schedule/`; gateway and clock ports; run checkpoint DTOs.
- **Contract:** Retry delay uses monotonic time and injectable jitter. Cancellation, timeout, and
  circuit-open paths cannot leak browser contexts or HTTP sessions.
- **Named tests:** `tests/unit/acquisition/test_retry_policy.py::test_attempt_and_deadline_budgets`;
  `tests/unit/acquisition/test_checkpointing.py::test_resume_does_not_repeat_completed_requests`;
  `tests/integration/test_acquisition_lifecycle.py::test_all_session_resources_close`.
- **Commands:** `uv run pytest tests/unit/acquisition tests/integration/test_acquisition_lifecycle.py -q`.
- **Expected:** Command exits 0; fake request ledger proves bounded counts and no duplicates; resource
  tracker ends at zero on success, failure, timeout, and cancellation.
- **Recovery:** Disable the new acquisition service at composition, retain its checkpoint for
  diagnosis, and restore the characterized adapter. Do not increase budgets to mask leaks.

### B6 — Replace name identity with fail-closed upstream IDs and per-run UUIDv4

- **Observable result:** Two same-named attendees remain distinct through acquisition, inference,
  resume, and reports; blank/malformed upstream IDs stop the attendee before work; shareable IDs are
  full UUIDv4 values unique within each run.
- **Anchors:** `src/scoutmb/domain/identity.py`; attendee import/acquisition boundaries;
  `annotate_requirement_statuses` and `build_missing_requirements` ports.
- **Contract:** Raw upstream ID remains sensitive adapter state. No unresolved bucket, stable digest,
  HMAC, UUIDv7, name key, shortened UUID, or cross-run linkable ID is permitted.
- **Named tests:** `tests/unit/domain/test_identity.py::test_same_name_distinct_upstream_ids_never_merge`;
  `tests/unit/domain/test_identity.py::test_missing_upstream_id_fails_closed`;
  `tests/integration/test_identity_flow.py::test_uuidv4_survives_resume_and_outputs_without_raw_id`.
- **Commands:** `uv run pytest tests/unit/domain/test_identity.py tests/integration/test_identity_flow.py -q`;
  `uv run python tools/check_private_data.py build/test-artifacts`.
- **Expected:** Both commands exit 0; UUID version is 4; two runs use unlinkable UUIDs; privacy scan
  reports zero upstream IDs/tokens; the A8 known-defect expectation is replaced by the correct one.
- **Recovery:** Fail the affected run before publication, preserve redacted diagnostic state, and
  restore the legacy adapter only for local fake comparison. Never synthesize identity from a name.

### B7 — Version schemas/templates and publish each artifact atomically

- **Observable result:** CSV, JSON, HTML, and email templates have explicit contract versions;
  single-artifact writes use same-directory temporary files, flush/fsync where required, atomic
  replace, and cleanup while preserving the prior file on failure.
- **Anchors:** `src/scoutmb/contracts/artifacts/`; `src/scoutmb/adapters/artifacts/atomic.py`;
  external templates under `src/scoutmb/templates/`.
- **Contract:** Output order and intentional version changes are documented. Shareable schemas omit
  sensitive adapter state. Templates contain no business logic.
- **Named tests:** `tests/contracts/test_artifact_schemas.py::test_versioned_golden_artifacts`;
  `tests/unit/artifacts/test_atomic_file.py::test_failure_preserves_previous_bytes`;
  `tests/privacy/test_artifacts.py::test_shareable_artifacts_exclude_sensitive_fields`.
- **Commands:** `uv run pytest tests/contracts/test_artifact_schemas.py tests/unit/artifacts/test_atomic_file.py tests/privacy/test_artifacts.py -q`.
- **Expected:** Command exits 0; goldens match reviewed versions; injected write/replace failures leave
  old bytes readable and no orphan temporary file.
- **Recovery:** Keep the previous schema version active, retain failed output only in private staging,
  and fix the writer. Do not partially overwrite the published artifact.

### B8 — Publish multi-file report generations atomically

- **Observable result:** A complete report/email set is staged under a generation ID, validated,
  then activated by one atomic manifest pointer; readers see the prior or new generation, never a
  mixture.
- **Anchors:** `src/scoutmb/features/generate_reports/`;
  `src/scoutmb/adapters/artifacts/generations.py`; generation manifest contract.
- **Contract:** Interrupted generations remain unreferenced and recoverable. Cleanup never removes
  the active generation or protected recovery/report generations.
- **Named tests:** `tests/integration/test_generation_publication.py::test_readers_never_observe_mixed_generation`;
  `tests/integration/test_generation_publication.py::test_interruption_preserves_active_generation`;
  `tests/unit/artifacts/test_generation_cleanup.py::test_protected_generations_survive`.
- **Commands:** `uv run pytest tests/integration/test_generation_publication.py tests/unit/artifacts/test_generation_cleanup.py -q`.
- **Expected:** Command exits 0 across every injected failure point; active manifest always references
  a complete hash-validated generation.
- **Recovery:** Leave the previous manifest active, quarantine the incomplete staging directory, and
  offer explicit retry/inspection. Never repair by merging directories.

### B9 — Introduce durable run state and lifespan-owned job supervision

- **Observable result:** Legal run transitions, checkpoints, pause/resume/cancel, startup recovery,
  bounded workers/queue, and graceful shutdown are owned by one supervisor rather than ad hoc
  threads or module globals.
- **Anchors:** `src/scoutmb/domain/run_state.py`; `src/scoutmb/features/jobs/`;
  `ui/server.py` worker and operation routes.
- **Contract:** Illegal transitions fail closed. Supervisor owns child tasks and resources;
  cancellation propagates and persists a resumable state before shutdown deadline.
- **Named tests:** `tests/unit/jobs/test_run_state.py::test_transition_table_rejects_illegal_edges`;
  `tests/integration/test_job_supervisor.py::test_restart_recovers_resumable_jobs`;
  `tests/integration/test_job_supervisor.py::test_shutdown_owns_and_closes_children`.
- **Commands:** `uv run pytest tests/unit/jobs/test_run_state.py tests/integration/test_job_supervisor.py -q`.
- **Expected:** Command exits 0; no non-daemon worker or resource survives each test; restart produces
  the documented terminal/resumable outcome.
- **Recovery:** Stop accepting new jobs, persist current checkpoint, cancel owned children within the
  grace period, and keep the legacy operation adapter selectable until lifecycle tests pass.

### B10 — Secure the loopback web boundary and stream uploads safely

- **Observable result:** A lifespan-created application uses a random session secret, loopback-only
  binding, Host/Origin validation, authentication, CSRF protection, CSP, containment-safe paths,
  streaming upload limits, parser budgets, and redacted errors.
- **Anchors:** `src/scoutmb/adapters/web/app.py`; `src/scoutmb/adapters/web/security.py`;
  migrated `ui/server.py` routes; static report response headers.
- **Contract:** No import-time filesystem/network/job side effects. Uploaded names never become
  trusted paths. Security checks apply to API, SSE, report, and state-changing routes.
- **Named tests:** `tests/security/test_local_web.py::test_auth_host_origin_and_csrf_matrix`;
  `tests/security/test_uploads.py::test_streaming_limits_and_path_containment`;
  `tests/security/test_report_csp.py::test_reports_have_restrictive_csp`;
  `tests/integration/test_app_lifespan.py::test_import_has_no_side_effects`.
- **Commands:** `uv run pytest tests/security tests/integration/test_app_lifespan.py -q`.
- **Expected:** Command exits 0; unauthorized/cross-origin/oversized/traversal cases are rejected;
  memory remains within the upload budget; valid loopback flows retain characterized responses.
- **Recovery:** Keep the prior UI disabled outside loopback, preserve completed runs, and repair the
  security boundary. Do not bypass authentication for desktop convenience.

### B11 — Compose CLI, web, and desktop entry points with port-zero rendezvous

- **Observable result:** CLI, local web, and desktop launch the same feature services; the server
  binds port 0 and reports the actual authenticated rendezvous, eliminating bind-close-rebind races.
- **Anchors:** `src/scoutmb/composition/`; console scripts; `run_app.py`: `free_port`, `start_server`,
  `wait_until_ready`, `run`; local web status APIs.
- **Contract:** Entry points differ only in interaction adapter. Configuration resolution and exit
  semantics are shared and parity-tested.
- **Named tests:** `tests/integration/test_entrypoint_parity.py::test_cli_web_desktop_share_services`;
  `tests/integration/test_rendezvous.py::test_port_zero_has_no_rebind_race`;
  `tests/integration/test_rendezvous.py::test_readiness_requires_session_nonce`.
- **Commands:** `uv run pytest tests/integration/test_entrypoint_parity.py tests/integration/test_rendezvous.py -q`;
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
- **Named tests:** `tests/packaging/test_distributions.py::test_wheel_and_sdist_clean_install`;
  `tests/packaging/test_release_root.py::test_copied_release_starts_without_repo`;
  `tests/packaging/test_distributions.py::test_expected_package_data_is_present`.
- **Commands:** `uv build`; `uv run pytest tests/packaging/test_distributions.py tests/packaging/test_release_root.py -q`.
- **Expected:** Both commands exit 0; artifacts appear under `dist/`; clean installs and release roots
  answer the offline health probe with all repository paths hidden/unmounted.
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

### C1 — Resolve installed data roots, permissions, retention, backup, and restore

- **Observable result:** All mutable data resolves from explicit/platform roots with secure
  permissions; retention enforces 120 days for terminal private runs, 45 days for logs, 7 days for
  staging, and indefinite retention for resumable work, recovery snapshots, and report generations;
  backup/restore is private, staged, and validated.
- **Anchors:** `bootstrap/paths.py`: `AppPaths`, `ensure_dirs`, `get_paths`;
  `src/scoutmb/adapters/storage/`; retention and backup services.
- **Contract:** Code/static paths never determine data paths. Cleanup is dry-run capable and protects
  active/resumable/recovery/report references. Restore never overwrites active state directly.
- **Named tests:** `tests/storage/test_data_roots.py::test_resolution_is_platform_and_code_location_independent`;
  `tests/storage/test_retention.py::test_retention_classes_and_protected_references`;
  `tests/integration/test_backup_restore.py::test_restore_is_staged_validated_and_private`.
- **Commands:** `uv run pytest tests/storage tests/integration/test_backup_restore.py -q`.
- **Expected:** Command exits 0; permission assertions pass on supported platforms; dry-run and actual
  cleanup select the same eligible data; protected data remains byte-identical.
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
  `tests/launcher/test_single_instance.py::test_stale_metadata_cannot_steal_lock`.
- **Commands:** `uv run pytest tests/launcher/test_single_instance.py -q`.
- **Expected:** Command exits 0 across repeated concurrent starts; one owner starts, every follower
  exits 0 after activation, and no unrelated process is signaled.
- **Recovery:** If ownership cannot be proven, do not launch or break the lock automatically. Show
  recovery guidance and preserve the lock/rendezvous evidence for diagnosis.

### C3 — Implement copy-only SHA-256 migration and activation marker

- **Observable result:** A throwaway legacy root is inventoried, copied into staging, collision-safe,
  SHA-256 verified, then activated with a versioned marker; interruption resumes safely and original
  files remain untouched.
- **Anchors:** `bootstrap/migrate.py`; data-root inventory and migration marker contracts;
  launcher startup composition.
- **Contract:** Never move/delete source data. Existing destination bytes are never overwritten;
  equal hashes deduplicate, unequal collisions receive deterministic preserved names and manifest
  entries. Marker is written only after full verification.
- **Named tests:** `tests/migration/test_copy_migration.py::test_source_is_never_modified`;
  `tests/migration/test_copy_migration.py::test_collision_and_hash_contract`;
  `tests/migration/test_copy_migration.py::test_each_interruption_point_resumes_idempotently`.
- **Commands:** `uv run pytest tests/migration/test_copy_migration.py -q`;
  `uv run scoutmb migrate --source build/legacy-root --destination build/new-root --dry-run`.
- **Expected:** Both commands exit 0; dry-run manifest is deterministic; test source tree hashes are
  identical before/after; activation marker references a complete verified inventory.
- **Recovery:** Leave source and current active destination untouched, retain staging/manifest, and
  resume from the last verified item. Never delete a collision or write a success marker early.

### C4 — Detect split-brain writes and preserve recovery snapshots

- **Observable result:** Post-migration writes to legacy and new roots are detected; affected files
  are snapshotted with hashes and provenance, publication/cleanup pauses, and the operator receives
  deterministic reconciliation choices.
- **Anchors:** migration watcher/inventory service; recovery snapshot contract; diagnostics API.
- **Contract:** Detection is content/inventory based, not timestamp-only. The tool never guesses
  which divergent private file wins and never auto-merges generated reports.
- **Named tests:** `tests/migration/test_split_brain.py::test_legacy_write_after_activation_is_detected`;
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
  `uv run python tools/rehearse_upgrade.py --legacy-root build/gate3/legacy --work-root build/gate3/work --sequence N,N+1,N`;
  `uv run python tools/check_private_data.py build/gate3/reports`.
- **Expected GO:** All commands exit 0; source hashes remain unchanged; simultaneous launchers have
  one owner; collisions and split-brain data are preserved; disk-full/interruption cannot corrupt
  active data; N restarts offline after rollback; reports are redacted.
- **Recovery / NO-GO:** Stop. Preserve the throwaway evidence and recovery snapshots, reactivate N,
  and return the failure to its C task. Do not run migration against the live installation.

## Phase D — Thin installer, optional capabilities, and operational hardening

Gate 3 permits release engineering to begin. Phase D has no fourth gate: D7 is final acceptance and
may complete only after every Phase D task and all three earlier gates are green.

### D1 — Split core, acquisition, browser, and PDF capability payloads

- **Observable result:** Core, ScoutingEvent acquisition, managed Chromium, and PDF/OpenCV payloads
  have separate manifests, dependency closures, cache identities, compatibility ranges, install
  state, and removal rules; a core install imports without optional payloads.
- **Anchors:** optional dependencies in `pyproject.toml`; capability manifest contracts; launcher
  capability installer/cache; composition capability registry.
- **Contract:** Playwright code and browser binaries are separate payloads. PDF/OpenCV is separate.
  Capability activation is transactional and compatible with the active release/state tuple.
- **Named tests:** `tests/packaging/test_capability_split.py::test_core_has_no_optional_dependency_closure`;
  `tests/launcher/test_capabilities.py::test_install_activate_remove_and_rollback`;
  `tests/contracts/test_capability_compatibility.py::test_release_ranges_fail_closed`.
- **Commands:** `uv run pytest tests/packaging/test_capability_split.py tests/launcher/test_capabilities.py tests/contracts/test_capability_compatibility.py -q`;
  `uv run python tools/build_capabilities.py --output build/capabilities`.
- **Expected:** Both commands exit 0; manifests and hashes are deterministic; core starts offline;
  each optional feature reports unavailable until installed and never imports eagerly.
- **Recovery:** Keep the prior compatible capability active, quarantine the failed staged payload,
  and leave the requested feature unavailable with actionable diagnostics.

### D2 — Implement platform browser selection and readiness

- **Observable result:** Windows selects system Edge, then system Chrome, then managed Chromium;
  macOS selects system Chrome, then managed Chromium; Safari appears only as an explicit experimental
  option with a truthful compatibility warning and no Playwright promise.
- **Anchors:** `bootstrap/browser_setup.py`: `probe_msedge_channel`,
  `install_chromium_fallback`, `resolve_browser_channel`; browser capability adapter and diagnostics.
- **Contract:** Browser presence is insufficient: a local-fake readiness transaction must pass.
  Browser/system detection is platform-adapter code and never launches the real service in tests.
- **Named tests:** `tests/launcher/test_browser_selection.py::test_windows_preference_matrix`;
  `tests/launcher/test_browser_selection.py::test_macos_preference_and_experimental_safari`;
  `tests/integration/test_browser_readiness.py::test_selected_engine_completes_local_fake_flow`.
- **Commands:** `uv run pytest tests/launcher/test_browser_selection.py tests/integration/test_browser_readiness.py -q`.
- **Expected:** Command exits 0 for simulated platform matrices; supported choices pass the local fake
  flow; unsupported/experimental choices explain limitations and never silently change engine.
- **Recovery:** Fall back only in the documented order, retain the previous compatible managed
  browser, and leave acquisition unavailable if readiness fails.

### D3 — Build and verify sub-18 MB Windows and macOS installers

- **Observable result:** Windows 11 x64 and macOS 14+ arm64 thin installers are each at most 18 MB,
  install core on a clean machine, optionally fetch capabilities, and restart offline; the unchanged
  Windows payload records Windows 10 results as best effort.
- **Anchors:** PyInstaller/launcher build definitions; platform bootstrap adapters; release metadata;
  CI jobs `launcher-windows` and `launcher-macos`.
- **Contract:** Installer contains launcher essentials only, not Playwright, browser binaries,
  OpenCV, or PDF engines. D23 remains deferred and release notes state the internal-only trust model.
- **Named tests:** `tests/release/test_installer_budget.py::test_each_thin_installer_is_at_most_18_mb`;
  `tests/release/test_clean_machine.py::test_first_install_then_offline_restart`;
  `tests/release/test_platform_contract.py::test_supported_and_best_effort_metadata`.
- **Commands:** `uv run python tools/build_installers.py --platform all --output dist/installers`;
  `uv run pytest tests/release/test_installer_budget.py tests/release/test_platform_contract.py -q`;
  `uv run python tools/rehearse_clean_install.py --artifacts dist/installers --offline-restart`.
- **Expected:** All commands exit 0 on supported CI runners; each installer is no larger than 18 MB;
  clean first launch works, optional payloads remain separate, and restart succeeds with egress denied.
- **Recovery:** Do not publish an oversized or failed platform artifact. Remove only build staging,
  keep last-known-good installers, and reduce launcher closure rather than raising the budget.

### D4 — Add redacted diagnostics and an offline OpenTelemetry seam

- **Observable result:** Structured logs, support bundles, metrics/traces interfaces, an in-memory
  no-op exporter, and a bounded encrypted-at-rest or access-controlled offline spool operate without
  network access; future sync can be added behind a port.
- **Anchors:** `src/scoutmb/observability/`; diagnostic bundle service; log/retention configuration;
  telemetry exporter port.
- **Contract:** Telemetry is disabled/no-op by default. Spool records are versioned, bounded,
  redacted, retention-aware, and never contain upstream IDs, QR tokens, cookies, raw payloads, names,
  or report bodies.
- **Named tests:** `tests/observability/test_telemetry_seam.py::test_default_exporter_never_uses_network`;
  `tests/observability/test_spool.py::test_bounded_offline_spool_and_future_sync_contract`;
  `tests/privacy/test_diagnostics.py::test_support_bundle_is_redacted`.
- **Commands:** `uv run pytest tests/observability tests/privacy/test_diagnostics.py -q`;
  `uv run python tools/check_private_data.py build/support-bundles`.
- **Expected:** Both commands exit 0; forced telemetry events create only bounded local records;
  network sentinel remains zero; scanner reports zero sensitive findings.
- **Recovery:** Disable the exporter, retain only schema-valid redacted spool records within policy,
  and delete corrupt spool segments through the spool manager without affecting application runs.

### D5 — Produce release supply-chain evidence

- **Observable result:** Locked vulnerability results, approved licenses, CycloneDX SBOMs, secret
  scans, artifact hashes, source revision, capability manifests, and clean-build metadata form one
  release evidence bundle.
- **Anchors:** CI job `supply-chain`; `uv.lock`; release tooling and metadata contracts.
- **Contract:** Findings are policy-gated and reviewed; suppressions are narrow, expiring, and
  documented. Hash verification does not claim publisher authenticity while D23 is deferred.
- **Named tests:** `tests/release/test_evidence_bundle.py::test_bundle_is_complete_and_reproducible`;
  `tests/release/test_evidence_bundle.py::test_deferred_signing_is_stated_truthfully`.
- **Commands:** `uv audit`; `uv export --locked --format cyclonedx1.5 --output-file build/evidence/python-sbom.json`;
  `uv run python tools/check_licenses.py`; `uv run python tools/build_release_evidence.py --artifacts dist --output build/evidence`;
  `uv run pytest tests/release/test_evidence_bundle.py -q`.
- **Expected:** All commands exit 0; evidence references exact artifact hashes and git revision;
  no unreviewed vulnerability/license/secret finding remains; signing status is `deferred-internal`.
- **Recovery:** Block publication, keep the last clean evidence bundle, update or remove the affected
  dependency/artifact, rebuild from the lock, and regenerate all evidence together.

### D6 — Lock measured resource and performance limits

- **Observable result:** Release configuration contains measured non-placeholder limits for uploads,
  PDF pages/image dimensions, parse time/memory, archive entries/expanded bytes, concurrent jobs and
  workers, queue depth, shutdown grace, cache budget, disk reserve, startup, request counts, runtime,
  installer size, and installed footprint.
- **Anchors:** typed configuration limits; `tools/measure_baseline.py`; performance CI job; synthetic
  corpus and optional private-corpus runner.
- **Contract:** Request counts and algorithmic growth are hard assertions. Controlled wall-time jobs
  compare repeated samples on named machine classes with documented variance and threshold.
- **Named tests:** `tests/performance/test_resource_limits.py::test_every_release_limit_is_bounded`;
  `tests/performance/test_complexity.py::test_request_and_memory_growth`;
  `tests/performance/test_regression_policy.py::test_baseline_metadata_and_thresholds`.
- **Commands:** `uv run pytest tests/performance/test_resource_limits.py tests/performance/test_complexity.py tests/performance/test_regression_policy.py -q`;
  `uv run python tools/measure_baseline.py --corpus synthetic --repetitions 5 --compare build/baseline.json --output build/release-baseline.json`.
- **Expected:** Both commands exit 0 on the controlled runner; every limit has value, unit, source
  measurement, headroom rationale, safe configurable range, and failure behavior; no regression
  exceeds its locked threshold.
- **Recovery:** Keep the prior measured limits, reject the release candidate, profile the regressed
  path, and rerun on the same machine class. Do not widen a limit without new evidence and review.

### D7 — Final acceptance, documentation, and legacy retirement

- **Observable result:** All three gate records and every Phase D task are green; operators can
  install, recover, migrate, run offline, add capabilities, collect redacted diagnostics, and perform
  an explicit staging smoke from current documentation; redundant legacy implementation code is
  removed while compatibility entry points remain for the documented transition window.
- **Anchors:** `README.md`; operator/install/recovery/privacy documentation; `CLAUDE.md` and
  `AGENTS.md` if commands changed; compatibility entry points; release checklist.
- **Contract:** No default command or automated test contacts the real service. The only live smoke
  is read-only, manual/staging, marked `live_service`, and requires explicit two-part opt-in. D23 is
  listed as deferred follow-up before distribution scope expands.
- **Named tests:** `tests/acceptance/test_documented_commands.py::test_all_documented_offline_commands`;
  `tests/acceptance/test_release_contract.py::test_three_gates_and_phase_d_evidence_are_green`;
  `tests/acceptance/test_legacy_retirement.py::test_compatibility_entrypoints_contain_no_business_logic`.
- **Commands:** `uv sync --locked --all-groups`; `uv run ruff check .`;
  `uv run ruff format --check .`; `uv run mypy --strict src/scoutmb`;
  `uv run pytest -m "not live_service" --cov=src/scoutmb --cov-branch -q`;
  `uv build`; `uv run python tools/verify_release.py --evidence build/evidence --installers dist/installers --capabilities build/capabilities`.
- **Expected:** Every command exits 0; branch coverage meets locked policy; wheel/sdist/installers and
  capabilities verify; all documented offline flows work; no stale implementation path, sensitive
  artifact, network escape, or unresolved decision remains.
- **Recovery:** Do not publish or migrate the live installation. Restore the last-known-good release
  bundle, return the failed check to its owning task, and rerun D7 in full after repair.

## Failure-mode coverage

| Path | Injected failure | Named coverage | Required behavior |
| --- | --- | --- | --- |
| Input/PDF import | Malformed row, QR miss, missing capability, oversized document | A6, B3, D1, D6 | Typed bounded error; no eager optional import; no partial attendee file |
| ScoutingEvent | Redirect, auth expiry, schema drift, timeout, cancellation | A3, A7, B4, B5 | Revalidate, fail closed, bounded retry, redact, close session |
| Identity/inference | Same names, blank/malformed ID, resume | B6 | Never merge; reject missing identity; keep full run UUIDv4 stable only within run |
| Single artifact | Write/flush/replace failure | B7 | Prior bytes remain readable; temporary file cleaned or quarantined |
| Report generation | Failure between files or manifest activation | B8 | Readers see one complete generation; previous generation remains active |
| Local web | Forged Host/Origin/CSRF, traversal, oversized/slow upload | B10 | Reject before state change; bounded memory/time; redacted response |
| Jobs | Illegal transition, crash, timeout, shutdown | B9 | Persist legal state; own/cancel children; leave resumable checkpoint |
| Ownership | Simultaneous/stale second launcher | C2 | One owner; authenticated activation; no lock stealing or unrelated signals |
| Migration | Collision, interruption, disk full, legacy write | C3, C4 | Source untouched; preserve both; resume; pause cleanup/publication |
| Update | Bad hash/archive, readiness failure, incompatible state | C5-C7 | No activation or atomic rollback of executable and state tuple |
| Capabilities | Missing/incompatible/corrupt payload | D1, D2 | Core stays usable; prior capability retained; feature truthfully unavailable |
| Diagnostics | Sensitive value or spool corruption | D4 | Redaction test fails; exporter disabled; app data unaffected |
| Resource limits | Queue/cache/disk/memory/time budget exceeded | C6, D6 | Reject or pause safely with actionable bounded diagnostics |

## CI growth by phase

| Phase | Jobs required by phase completion |
| --- | --- |
| A | `lint-format`, `types`, `lock`, `unit-contract`, `local-playwright`, `egress-denied` |
| B | A jobs plus `local-web-security`, `package`, `architecture` |
| C | B jobs plus `launcher-windows`, `launcher-macos` migration/update slices |
| D | Full platform launcher matrices, `supply-chain`, `performance`; local-only `private-corpus`; manual-only `live-smoke` |

## Implementation task index

| ID | Observable result | Blocked by |
| --- | --- | --- |
| A1 | Reproducible Python 3.12 package and lock | — |
| A2 | Green quality/lock CI | A1 |
| A3 | Offline-by-default enforcement | A1 |
| A4 | Synthetic factories and privacy tripwire | A1, A3 |
| A5 | Optional private-corpus verifier | A4 |
| A6 | Input/PDF contract matrix | A4 |
| A7 | Local-fake ScoutingEvent contract matrix | A3, A4 |
| A8 | Inference/artifact/interface/performance matrix | A4, A6, A7 |
| G1 | Characterization GO | A2-A8 |
| B1 | Package boundaries and shims | G1 |
| B2 | Typed core contracts | B1 |
| B3 | Input/PDF adapter parity | B1, B2 |
| B4 | Session gateway and drift detection | B1, B2, A7 |
| B5 | Bounded acquisition service | B2, B4 |
| B6 | Correct attendee identity | B2, A8 |
| B7 | Versioned atomic artifacts | B2, B6, A8 |
| B8 | Atomic report generations | B7 |
| B9 | Durable run supervisor | B2 |
| B10 | Secure local web boundary | B3, B5, B8, B9 |
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
| D3 | Sub-18 MB platform installers | D1, D2, C7 |
| D4 | Offline telemetry/diagnostic seam | G3, B9 |
| D5 | Release supply-chain evidence | D1, D3, D4 |
| D6 | Measured resource/performance limits | D1-D4 |
| D7 | Final acceptance and legacy retirement | D3-D6 |

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
| --- | --- | --- | ---: | --- | --- |
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | NOT RUN | — |
| Codex Review | `/codex review` | Independent second opinion | 0 | NOT RUN | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 5 issues, 0 critical gaps; all folded into the rewrite |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | NOT RUN | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | NOT RUN | — |

**VERDICT:** ENG CLEARED — ready to implement

NO UNRESOLVED DECISIONS
