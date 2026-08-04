# Slice 2b — Runtime & Interfaces (PRELIMINARY)

> ⚠️ **PRELIMINARY. Do not execute.** This carries forward the descoped Phase B task
> structure, named tests, and recovery behaviors from the archived Slice 2 skeleton
> (`archive/2026-07-22-slice-2-package-boundaries-and-core.md`), narrowed to what 2a leaves
> behind. It is refined into a ready plan **after Gate 2a passes**, because the exact seams
> depend on what 2a's parity runners and goldens reveal. No `.tasks.json` sidecar exists yet;
> generate one when finalizing, matching the 2a format.

**Spec:** `docs/superpowers/specs/2026-07-24-phase-b-package-boundaries-design.md`
**Parent spec:** `docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`
**Depends on:** Gate 2a GO.
**Goal:** Move the network- and server-facing boundaries into the package, land the nine
`new-acceptance` rows and the five remaining `intentional-change` rows, retire the flat
modules, and ship a release root that starts without the repository.
**Gate at end:** Gate 2 — identity, output, and runtime go/no-go.

## How to finalize this slice

1. Confirm Gate 2a is green and the goldens are committed.
2. Re-read 2a's parity runners — they are the pattern every task here repeats.
3. Confirm the four plan-verified mechanisms from 2a Task 3 still hold, and add one for the
   embedded-interpreter `.pth` path before Task B11.
4. Expand each task below to 2a fidelity (RED test + real code + exact verify + recovery) and
   write the sidecar. Then run via `executing-plans`.

## What 2a left behind

- `ScoutResult` is still legacy-defined and mutable — `process_scout` calls `.append` on its
  collections. Freezing it is B5's job, not a separate cleanup.
- `scout_schedule_cli.py` still owns argparse, Playwright control, acquisition, and
  `async_main`. It is not yet a delegation shim, so `SHIMMED_MODULES` in the architecture test
  is still empty.
- `ui/server.py` and `run_app.py` are untouched. **Known gap to close here:** 2a Task 7 threaded
  one `RunIdentity` through `write_outputs` → `write_email_reports` → `async_main` so an
  attendee gets the same `output_id` in `raw/` and `emails/` filenames within one run — but
  `ui/server.py`'s `POST /api/runs/{run_id}/generate-emails` endpoint (`generate_emails`,
  ~line 365) still calls `write_email_reports(run_dir, scouts)` with no `run_identity`, so it
  still mints an unrelated fresh identity map. Whichever task threads `ui/server.py`'s routes
  through the new services must pass that run's `RunIdentity` through to this endpoint too, or
  the split-map defect 2a fixed reappears through this second call path.
- `tests/harnesses/legacy.py` still loads the legacy UI.
- **`pdf_to_scouts.py` already qualifies for `SHIMMED_MODULES` but isn't armed.** Post-2a
  senior-engineer review: `pdf_to_scouts.py` became pure delegation this slice (only imports
  plus one `if __name__` guard), but `tests/architecture/test_dependency_rules.py`'s shape
  check (search `SHIMMED_MODULES`) currently flags any top-level `ast.If`, including a
  canonical `if __name__ == "__main__": raise SystemExit(main())` guard — so adding this module
  today would immediately red the suite. Whoever next touches that shape check should special-
  case the canonical main-guard pattern, then add `pdf_to_scouts.py` to `SHIMMED_MODULES` so its
  coverage-floor-proves-nothing status is actually caught, not just documented.
- **`ArtifactSink.publish_rows`/`write_csv` (`src/scoutmb/adapters/files/atomic.py`) assumes
  dataclass rows** (`asdict()` inside `write_csv`), which is why `ReportingService.publish`
  can't route `errors.csv`/`missing_requirements.csv` through the sink port like everything else
  it writes and instead hand-rolls two separate `csv.DictWriter` blocks in
  `src/scoutmb/features/reporting/service.py` (post-2a code review finding). If B4/B5 touch this
  port again, consider widening it to `Sequence[Mapping[str, Any]]` (coercing dataclasses only
  when given one) so the two hand-rolled writers can be retired.

## Tasks (preliminary)

### B4 — ScoutingEvent gateway + schema-drift boundary
- **Observable result:** One adapter owns the attendee session and payload validation against
  named schema profiles; feature code sees only typed port DTOs; unknown or missing fields fail
  closed with redacted bounded samples.
- **Owns:** `ACQ-REQ-004` (validate requirement rows instead of coercing to blanks),
  `NET-WIRE-001`, `NET-WIRE-002` (both gateways call `assert_egress_allowed` before any request
  or navigation).
- **Anchors:** `src/scoutmb/ports/scoutevent.py`, `src/scoutmb/adapters/scoutevent/`,
  `tests/fakes/scoutingevent_service.py`.
- **Contract:** Only an HTTPS approved host and path is valid outside tests; redirects
  revalidated. URL allowlist enforcement is minimal here (host + scheme); the full allowlist is
  vNext.
- **Named tests:** `tests/contracts/test_scoutingevent_gateway.py::test_observed_profiles_validate`;
  `::test_schema_drift_fails_closed_and_redacts`;
  `tests/parity/test_scoutevent_adapter_parity.py::test_normalized_gateway_results_match_legacy`.
- **Recovery:** Keep the legacy local-fake adapter; store only redacted drift metadata; never
  parse permissively to get a test green.

### B5 — Bounded acquisition: retries, dedup, circuit breaker, checkpoints
- **Observable result:** The acquisition service keeps the current retry (×3 at 500/1000/1500 ms)
  and schedule dedup, adds a consecutive-failure circuit breaker and resumable checkpoints, and
  closes every attendee-session resource.
- **Owns:** `ACQ-BREAKER-001/002/003`, `ACQ-RESUME-001/002/003/004`, `ACQ-HASREQ-002` (skip the
  requirement request when `HAS_REQ='0'`). Also freezes `ScoutResult` by rewriting
  `process_scout`'s `.append` sites to accumulate locally and construct once.
- **Anchors:** `src/scoutmb/features/acquisition/`, the gateway and clock ports, checkpoint DTOs.
- **Contract:** Retry delay uses the monotonic `Sleeper` plus injectable `Jitter`; cancellation
  and breaker-open paths leak no browser context or HTTP session. Deadline budgets are POSTPONED.
  The request-count assertion is restated as **one requirement request per deduplicated class
  whose `HAS_REQ` is truthy** — the canonical corpus has none with `HAS_REQ='0'`, so a synthetic
  case must exercise the skip directly or the assertion is accidentally true.
- **Named tests:** `tests/unit/acquisition/test_retry_policy.py::test_attempt_budget_and_breaker_trip`;
  `tests/unit/acquisition/test_checkpointing.py::test_resume_does_not_repeat_completed_requests`;
  `::test_uuid_survives_resume` (the checkpoint persists the **single** run-scoped identity map
   2a introduced — persisting one of several maps was the defect 2a fixed);
  `tests/integration/test_acquisition_lifecycle.py::test_all_session_resources_close`;
  `tests/parity/test_acquisition_parity.py::test_results_match_or_are_reviewed_changes`.
- **Recovery:** Disable the new service at composition, keep the checkpoint, restore the
  characterized adapter.

### B6 — Typed configuration replaces `Namespace`
- **Observable result:** Frozen config dataclasses replace `argparse.Namespace` threading; the
  `getattr` defenses in `async_main` and `ui.server`'s hand-built `Namespace` go together.
- **Contract:** CLI defaults and dataclass defaults are defined **once** so they cannot drift
  (`CLI-SCHED-*` pins them). `ui.server` omits `email_report` today and `async_main` compensates
  with `getattr(args, "email_report", False)` — removing the `getattr` while the caller still
  omits the field turns a working default into an `AttributeError`, so both change in the same
  task.
- **Named tests:** `tests/unit/test_config.py::test_cli_and_dataclass_defaults_agree`;
  `tests/parity/test_cli_defaults_parity.py`.
- **Recovery:** Keep `Namespace` at the boundary and convert inside `async_main` only.

### B7 — Durable run state + lifespan-owned job supervisor
- **Observable result:** A versioned run-state machine and one lifespan-owned supervisor replace
  `busy` flags and the unreferenced `create_task` workers; illegal transitions fail closed;
  cancellation owns and closes children.
- **Anchors:** `src/scoutmb/core/run_state.py`, `src/scoutmb/runtime/jobs.py`,
  `ui/server.py` worker and operation routes.
- **Named tests:** `tests/unit/jobs/test_run_state.py::test_transition_table_rejects_illegal_edges`;
  a Hypothesis property that the transition table is **total** (every state/event pair either
  transitions or fails closed — no pair falls through);
  `tests/integration/test_job_supervisor.py::test_shutdown_owns_and_closes_children`;
  `::test_cancellation_during_a_blocking_adapter_call_leaves_no_pending_task` (covers
  `asyncio.to_thread` work, which "cancellation owns every child" does not catch);
  `tests/parity/test_operation_parity.py::test_user_visible_operation_outcomes_match_or_are_reviewed`.
- **Recovery:** Stop accepting jobs, persist the checkpoint, cancel owned children, keep the
  legacy operation adapter selectable.

### B8 — Structural loopback web boundary + JobRegistry + the four UI defects
- **Observable result:** A `create_app(settings)` lifespan factory with no import-time side
  effects, a `JobRegistry` on `app.state` retaining task references, loopback bind, and the four
  UI defects fixed — including the `app.js` half of the report-open change.
- **Owns:** `UI-IMPORT-001` (no filesystem I/O on import), `UI-ROUTE-023` (`open_emails_folder`
  dispatches on `sys.platform`), `UI-ROUTE-030` (`open_report` validates `html_report` is a bare
  filename resolving inside `RUNS_DIR/<run_id>`).
- **Contract:** No import-time filesystem, network, or job side effects. The four bugs: the
  PDF-upload cleanup unlink without an `is_file()` guard; Windows-only `os.startfile`;
  server-side `webbrowser.open`; unguarded persisted-JSON reads in the run/report/email routes.
  CSRF, CSP, auth, and Host/Origin remain POSTPONED.
- **Note:** `interfaces/web/composition.py` imports both the PDF and ScoutingEvent adapters, so
  the web app requires every extra. That matches today's behavior and is not a regression, but
  state it in the capability docs rather than leaving it implied.
- **Named tests:** `tests/integration/test_app_lifespan.py::test_import_has_no_side_effects`;
  `tests/unit/web/test_job_registry.py::test_tasks_are_retained`;
  `tests/parity/test_local_web_parity.py::test_preserved_routes_match`;
  `tests/integration/test_report_open.py::test_client_opens_report_via_anchor`.
- **Recovery:** Keep the prior UI behind loopback; preserve completed runs; repair the factory.

### B9 — Compose CLI, web, desktop; port-zero rendezvous
- **Observable result:** All three interfaces drive the same feature services; the server binds
  port 0 and reports the actual port, removing the bind-close-rebind race in `run_app.py`.
- **Anchors:** `src/scoutmb/interfaces/{cli,web,desktop}`; `run_app.py`'s `free_port`,
  `start_server`, `wait_until_ready`, `main`.
- **Contract:** Entry points differ only in interaction adapter; config resolution is shared.
  `troop349-schedule` and `troop349` must match the flat scripts on options, defaults, exit
  codes, stdout, stderr, and `--help`, and are tested as **installed subprocesses**.
  Authenticated rendezvous is POSTPONED — port-zero bind only.
- **Named tests:** `tests/parity/test_entrypoint_parity.py::test_legacy_cli_web_desktop_observables_match`;
  `tests/integration/test_rendezvous.py::test_port_zero_has_no_rebind_race`.
- **Recovery:** Abort the attempted launch without killing an unrelated process; restore the
  prior entry adapter.

### B10 — Retire the flat modules
- **Observable result:** `scout_schedule_cli.py`, `pdf_to_scouts.py`, `ui/server.py`, and
  `run_app.py` are deleted, together with `tests/harnesses/legacy.py` and the characterization
  runners that drove them. The catalog cases survive; only the legacy runners go.
- **Contract:** A module is deleted only after its package runner covers every execution key it
  held. Immediately before deletion each module must pass the no-business-logic shape check, so
  add it to `SHIMMED_MODULES` first and watch it go green — that is the evidence that nothing
  was left behind.
- **Named tests:** the existing `tests/architecture/test_dependency_rules.py::test_shimmed_module_contains_no_business_logic`,
  parametrized over each module as it qualifies.
- **Recovery:** `git revert` the deletion. Retirement is the one genuinely irreversible step in
  Phase B, so it happens last and in its own commit per module.

### B11 — Release root and clean distributions
- **Observable result:** Wheel and sdist install in clean environments; the launcher copies
  `src/scoutmb` into a release root that starts with no repository present.
- **Three change sites, all required:** `bootstrap/source_sync.py` `_FILES`/`_DIRS` allowlist;
  `bootstrap/build.spec` `datas` (currently ships only the flat modules, so a built installer
  would have nothing to sync); and the recorded dependency on `bootstrap/python_env.py`'s `.pth`
  entry, which is what actually puts `app_dir` on `sys.path` — the embeddable distribution's
  isolated path mode does not add the launched script's directory.
- **Plan-verified mechanism:** prove `importlib.resources` reads a template under the embedded
  interpreter configuration, not just under the dev interpreter, before this task lands.
- **Named tests:** `tests/packaging/test_distributions.py::test_wheel_installs_in_clean_environment`;
  `::test_archives_exclude_private_tests_logs_and_secrets`;
  `tests/packaging/test_release_root.py::test_copied_release_starts_without_repo`.
- **Recovery:** Keep the working source-copy manifest; correct the package-data and build rules;
  never add a runtime fallback to repository files.

## Gate 2 — Identity, output, and runtime

Everything in Gate 2a, plus:

- Both runners green across the whole catalog; all fifteen owned rows landed and reviewed.
- Same-named attendees stay separate through acquisition, inference, reports, and resume;
  a missing upstream ID fails closed and surfaces as `output_id: null`.
- Single-file publication failures preserve prior bytes.
- Illegal run-state transitions fail closed; cancellation owns and closes every child, including
  `asyncio.to_thread` work; loopback bind holds; importing the web module performs no I/O.
- All three console scripts match the flat scripts they replace on stdout, stderr, and exit code,
  run from outside the repository.
- Flat modules retired; `tests/harnesses/legacy.py` removed with them.
- The release-root acceptance sequence passes under the embedded interpreter configuration.

**NO-GO:** restore the relevant compatibility adapter as the composed default, return the defect
to its task, rerun the gate.
