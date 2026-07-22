# Slice 2 — Package Boundaries & Core (PRELIMINARY)

> ⚠️ **PRELIMINARY.** Do not execute. This skeleton carries forward the descoped Phase B
> task structure, named tests, and recovery behaviors from the prior planning round. It is
> **refined into a ready plan after Slice 1's Gate 1 passes** — because the exact seams
> depend on what Slice 1's characterization matrix reveals (notably the `Note.`-row and
> empty-row questions, and the exact `id()` ancestor-walk behavior the inference
> decomposition must preserve). No `.tasks.json` sidecar exists yet; generate it (with
> `description` + `json:metadata` + checkbox steps + real code, per Slice 1's format) when
> finalizing.

**Spec:** `docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`
**Depends on:** Slice 1 complete (Gate 1 GO).
**Goal:** Move behavior behind hexagonal boundaries in small parity-checked slices. The
flat scripts become thin compatibility shims; the new package is the home for all logic.
**Gate at end:** Gate 2 — identity/output/runtime go/no-go.

## How to finalize this slice

1. Confirm Slice 1's Gate 1 is green and the live install's `app/` is backed up.
2. Re-read the Slice 1 characterization tests — they are the parity oracle for every move here.
3. Resolve the two suspect behaviors (`Note.` grafting, empty rows) with a direct
   `tree.py` test; decide keep-as-is vs fix (fix = its own RED-tested task).
4. Expand each task below to Slice-1 fidelity (RED test + code + exact verify) and write
   the sidecar. Then run via `executing-plans`.

## Descope reminders folded into these tasks

- Identity (B6 in the old plan) is **already fixed in Slice 1, in place.** Here it is only
  carried into the package and held by parity — no new behavior.
- Web boundary is **structural only**: `create_app` factory, `JobRegistry` (fixes the
  `create_task` GC bug), loopback bind, and the four UI defects. CSRF/CSP/auth/Host-Origin
  are POSTPONED (vNext).
- Multi-file report **generations** are POSTPONED. Keep Slice 1's atomic single-file writes;
  add only versioned schemas + template extraction.
- Scraper gateway keeps the **circuit breaker + resumable checkpoints**; deadline budgets
  and the URL allowlist are POSTPONED.

## Tasks (preliminary)

### B1 — Package skeleton + compatibility shims
- **Observable result:** `scoutmb` gains `core`, `features`, `ports`, `adapters`,
  `interfaces`, `runtime`, `resources`; flat scripts (`scout_schedule_cli.py`,
  `pdf_to_scouts.py`, `ui/server.py`, `run_app.py`) delegate to package entry points; no
  first-party `sys.path` mutation remains.
- **Anchors:** `src/scoutmb/`; the four flat scripts; console scripts in `pyproject.toml`.
- **Contract:** Mechanical movement only; shims preserve arguments, exit codes, and output;
  shims emit a `FutureWarning` naming `troop349`; reverse imports/cycles fail architecture tests.
- **Named tests:** `tests/architecture/test_dependency_rules.py::test_hexagonal_import_direction`;
  `::test_no_first_party_sys_path_mutation`;
  `tests/compat/test_legacy_entrypoints.py::test_legacy_entrypoints_delegate_with_parity`.
- **Recovery:** Keep the shim as the active path; move one symbol group back; restore parity.

### B2 — Typed core: models, clocks, errors, config, versioned DTOs
- **Observable result:** Pure immutable models for attendees/classes/requirements/runs;
  `ScoutmbError` hierarchy; frozen config dataclasses replacing `Namespace`; separate
  `Clock` (UTC wall) and monotonic deadline source; versioned DTOs that reject unknown versions.
- **Anchors:** `src/scoutmb/core/`; `src/scoutmb/ports/time.py`; `src/scoutmb/config.py`;
  `src/scoutmb/errors.py`.
- **Contract:** Parsing at boundaries; core uses typed values; wall time persisted, deadlines monotonic.
- **Named tests:** `tests/unit/core/test_models.py::test_invalid_states_are_unrepresentable`;
  `tests/unit/test_clocks.py::test_deadlines_ignore_wall_clock_changes`;
  `tests/contracts/test_dto_versions.py::test_unknown_versions_fail_closed`.
- **Recovery:** Remove the incomplete DTO from composition; keep boundary dicts behind the legacy adapter.

### B3 — Input & PDF behind ports (parity)
- **Observable result:** Loading and PDF extraction are adapters selected by feature
  services; core-only install loads non-PDF inputs without importing PDF/OpenCV.
- **Anchors:** `src/scoutmb/features/ingest/`; `src/scoutmb/adapters/files/`,
  `src/scoutmb/adapters/pdf/`; legacy loaders characterized in Slice 1.
- **Contract:** Adapter DTOs preserve field aliases, ordering, dedup, errors; optional-dep
  absence is a capability message, not an import crash.
- **Named tests:** `tests/parity/test_input_adapter_parity.py::test_full_input_matrix_matches_legacy`;
  `tests/parity/test_pdf_adapter_parity.py::test_pdf_matrix_matches_legacy`;
  `tests/packaging/test_core_imports.py::test_core_does_not_import_pdf_or_opencv`.
- **Recovery:** Select the legacy adapter at composition; fix one mismatch at a time.

### B4 — ScoutingEvent gateway + schema-drift boundary
- **Observable result:** One adapter owns the attendee session and payload validation
  against named schema profiles; feature code sees only typed port DTOs; unknown/missing
  fields fail closed with redacted bounded samples.
- **Anchors:** `src/scoutmb/ports/scoutevent.py`; `src/scoutmb/adapters/scoutevent/`;
  `tests/fakes/scoutingevent_service.py`.
- **Contract:** Only HTTPS approved host/path is valid outside tests; redirects revalidated.
  **URL allowlist enforcement is minimal here (host/scheme check); the full allowlist is vNext.**
- **Named tests:** `tests/contracts/test_scoutingevent_gateway.py::test_observed_profiles_validate`;
  `::test_schema_drift_fails_closed_and_redacts`;
  `tests/parity/test_scoutevent_adapter_parity.py::test_normalized_gateway_results_match_legacy`.
- **Recovery:** Keep the legacy local-fake adapter; store only redacted drift metadata; never parse permissively.

### B5 — Bounded acquisition: retries, dedup, circuit breaker, checkpoints
- **Observable result:** The acquisition service keeps the current retry (×3 at
  500/1000/1500 ms) and schedule dedup, adds a **circuit breaker** (trips on
  consecutive-failure count) and **resumable checkpoints** (resume never repeats completed
  requests), and closes all attendee-session resources.
- **Anchors:** `src/scoutmb/features/acquisition/`; gateway + time ports; checkpoint DTOs.
- **Contract:** Retry delay uses the monotonic `Sleeper` + injectable jitter; cancellation/
  breaker-open paths leak no browser context or HTTP session. **Deadline/elapsed budgets are POSTPONED.**
- **Named tests:** `tests/unit/acquisition/test_retry_policy.py::test_attempt_budget_and_breaker_trip`;
  `tests/unit/acquisition/test_checkpointing.py::test_resume_does_not_repeat_completed_requests`;
  `tests/integration/test_acquisition_lifecycle.py::test_all_session_resources_close`;
  `tests/parity/test_acquisition_parity.py::test_results_match_or_are_reviewed_changes`.
- **Recovery:** Disable the new service at composition, keep the checkpoint, restore the characterized adapter.

### B6 — Carry the identity fix into the package (parity only)
- **Observable result:** The Slice-1 attendee-ID keying and per-run UUIDv4 output identity
  live in `core/identity.py` + the inference/reporting features, with **no behavior change**
  from Slice 1.
- **Anchors:** `src/scoutmb/core/identity.py` (from Slice 1); inference + reporting features.
- **Contract:** Parity against Slice 1's identity tests is exact; this is a move, not a change.
- **Named tests:** reuse `tests/unit/test_identity.py`, `tests/unit/test_inference_identity.py`,
  `tests/unit/test_output_filenames.py` against the package paths.
- **Recovery:** Keep the flat-module identity code active until package parity is green.

### B7 — Versioned output schemas + template extraction
- **Observable result:** CSV/JSON/HTML/email have explicit schema versions; the 658-line
  embedded HTML string becomes `resources/templates/report.{html,css,js}` with a single
  `__REPORT_DATA__` injection (substitute CSS→JS→DATA, DATA last); atomic single-file
  writes (from Slice 1) are reused.
- **Anchors:** `src/scoutmb/core/output_schemas.py`; `src/scoutmb/adapters/files/atomic.py`
  (Slice 1); `src/scoutmb/resources/`.
- **Contract:** Output order and intentional version changes documented; templates hold no
  logic; **multi-file generation pointer is POSTPONED — single-file atomic only.**
- **Named tests:** `tests/contracts/test_artifact_schemas.py::test_versioned_golden_artifacts`;
  `tests/contracts/test_report_template.py::test_no_report_token_survives_and_uuidjs_scout`;
  `tests/parity/test_output_parity.py::test_outputs_match_or_are_versioned_changes`.
- **Recovery:** Keep the previous schema/template active; fix the writer; never partially overwrite.

### B8 — Durable run state + lifespan-owned job supervisor
- **Observable result:** A versioned run-state machine and one lifespan-owned supervisor
  replace `busy` flags and the unreferenced `create_task` workers; illegal transitions fail
  closed; cancellation owns and closes children.
- **Anchors:** `src/scoutmb/core/run_state.py`; `src/scoutmb/runtime/jobs.py`;
  `ui/server.py` worker/operation routes (`:162`, `:223`).
- **Named tests:** `tests/unit/jobs/test_run_state.py::test_transition_table_rejects_illegal_edges`;
  `tests/integration/test_job_supervisor.py::test_shutdown_owns_and_closes_children`;
  `tests/parity/test_operation_parity.py::test_user_visible_operation_outcomes_match_or_are_reviewed`.
- **Recovery:** Stop accepting jobs, persist checkpoint, cancel owned children, keep the legacy operation adapter selectable.

### B9 — Structural loopback web boundary + JobRegistry + UI-bug fixes
- **Observable result:** A `create_app(settings)` lifespan factory (no import-time side
  effects), a `JobRegistry` on `app.state` retaining task references, loopback bind, and the
  four UI defects fixed — **including the `app.js` half** of the report-open change.
- **Anchors:** `src/scoutmb/interfaces/web/app.py`; migrated `ui/server.py` routes;
  `ui/static/app.js` (`:170` ignores the response body).
- **Contract:** No import-time filesystem/network/job side effects; the four bugs
  (`:114-116` unlink guard, `:334` os.startfile, `:301` server-side webbrowser.open, unguarded
  `json.loads` at `:205`/`:296`/`:311`) fixed. **CSRF/CSP/auth/Host-Origin POSTPONED.**
- **Named tests:** `tests/integration/test_app_lifespan.py::test_import_has_no_side_effects`;
  `tests/unit/web/test_job_registry.py::test_tasks_are_retained`;
  `tests/parity/test_local_web_parity.py::test_preserved_routes_match`;
  `tests/integration/test_report_open.py::test_client_opens_report_via_anchor`.
- **Recovery:** Keep the prior UI behind loopback; preserve completed runs; repair the factory.

### B10 — Compose CLI/web/desktop; port-zero rendezvous
- **Observable result:** CLI, web, and desktop drive the same feature services; the server
  binds port 0 and reports the actual port, removing the bind-close-rebind race in
  `run_app.py`.
- **Anchors:** `src/scoutmb/interfaces/{cli,web,desktop}`; `run_app.py`: `free_port`,
  `start_server`, `wait_until_ready`, `run`.
- **Contract:** Entry points differ only in interaction adapter; config resolution shared.
  **Authenticated rendezvous is POSTPONED — port-zero bind only.**
- **Named tests:** `tests/parity/test_entrypoint_parity.py::test_legacy_cli_web_desktop_observables_match`;
  `tests/integration/test_rendezvous.py::test_port_zero_has_no_rebind_race`.
- **Recovery:** Abort the attempted launch without killing an unrelated process; restore the prior entry adapter.

### B11 — Clean package + copied-release startup
- **Observable result:** Wheel and sdist install in clean environments; the launcher copies/
  installs `src/scoutmb` + package data into a clean release root that starts without the repo.
- **Anchors:** Hatchling build config; `bootstrap/source_sync.py`; `bootstrap/build.spec`;
  package-data declarations.
- **Named tests:** `tests/packaging/test_distributions.py::test_wheel_installs_in_clean_environment`;
  `::test_archives_exclude_private_tests_logs_and_secrets`;
  `tests/packaging/test_release_root.py::test_copied_release_starts_without_repo`.
- **Recovery:** Keep the working source-copy manifest; correct package-data/build rules; no runtime fallback to repo files.

## Gate 2 — Identity, output, and runtime go/no-go
- Same-name attendees stay separate; missing ID fails closed; no shareable artifact leaks
  upstream identity/QR tokens; single-file output failures preserve prior files; illegal run
  transitions fail closed; cancellation closes all children; loopback bind holds; clean
  install runs. Parity green except reviewed intentional changes. Architecture tests pass.
- **NO-GO:** restore the relevant compatibility adapter as default; return the defect to its task; rerun the gate.

## Carried-forward reference (from the prior planning round)

**Failure-mode coverage (Phase B rows, descoped):**

| Path | Injected failure | Task | Required behavior |
| --- | --- | --- | --- |
| Input/PDF | Malformed row, QR miss, missing capability | B3 | Typed bounded error; no eager optional import; no partial attendee file |
| ScoutingEvent | Redirect, auth expiry, schema drift, timeout, cancellation | B4, B5 | Revalidate, fail closed, bounded retry + breaker, redact, close session |
| Identity/inference | Same names, blank ID, resume | B6 | Never merge; reject missing ID; UUIDv4 stable within run |
| Single artifact | Render/write/fsync/replace failure | B7 | Prior bytes remain; never overwrite twice |
| Local web | Traversal, oversized upload, forged request | B9 (structural) | Reject before state change; the 4 bugs fixed; deeper hardening vNext |
| Jobs | Illegal transition, crash, shutdown | B8 | Persist legal state; own/cancel children; resumable checkpoint |
