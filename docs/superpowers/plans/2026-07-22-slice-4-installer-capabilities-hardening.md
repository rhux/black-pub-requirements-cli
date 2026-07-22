# Slice 4 — Installer, Capabilities & Hardening (PRELIMINARY)

> ⚠️ **PRELIMINARY.** Do not execute. Carries forward the descoped Phase D task structure,
> named tests, and recovery behaviors from the prior planning round. **Refined into a ready
> plan after Slice 3's Gate 3 passes** — capability payloads and native installers consume
> the transactional-release machinery built in Slice 3. No `.tasks.json` sidecar yet;
> generate it (Slice-1 format) when finalizing. Slice 4 ends the effort with **final
> acceptance**, not a fourth gate.

**Spec:** `docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`
**Depends on:** Slice 3 complete (Gate 3 GO).
**Goal:** Split capabilities into hash-bound downloads, build thin native installers, finish
browser selection, land full diagnostics, and enforce performance and supply-chain gates.

## How to finalize this slice
1. Confirm Gate 3 is green.
2. Ensure a native Windows 11 x64 runner **and** a native macOS 14+ arm64 runner are
   available in CI — the macOS installer is the single biggest cost here.
3. Expand each task to Slice-1 fidelity + write the sidecar.

## Descope reminders folded into these tasks
- Supply-chain evidence is **`uv audit` + a license-compliance gate.** Per-payload CycloneDX
  SBOMs + exception-expiry policy are POSTPONED.
- **Auto-update release channel is POSTPONED** (Slice 3 kept transactional install/rollback;
  discovery stays manual). D3 below is therefore reduced to a local immutable-payload
  contract, not a hosted channel.
- Diagnostics are **full**: redacted rotating logs + a support-bundle command. Telemetry is
  a **no-op seam** only.
- Download/archive safety (full) landed in Slice 3 (C6); Slice 4 consumes it.

## Tasks (preliminary)

### D1 — Split core/acquisition/browser/PDF capability payloads
- **Observable result:** Core, ScoutingEvent acquisition, managed Chromium, and PDF/OpenCV
  payloads have separate manifests, dependency closures, cache identities, compatibility
  ranges, and reference-counted removal; core imports with every optional payload absent.
- **Anchors:** optional deps in `pyproject.toml` (`acquisition`, `pdf` extras from Slice 1);
  capability manifests; launcher capability installer/cache (C6); composition capability registry.
- **Contract:** Playwright Python code and browser binaries are separate payloads; each test
  environment installs its declared extra explicitly; activation is transactional (via C7).
- **Named tests:** `tests/packaging/test_capability_split.py::test_core_has_no_optional_dependency_closure`;
  `::test_each_extra_has_an_executed_test_environment`;
  `tests/launcher/test_capabilities.py::test_install_activate_remove_and_rollback`.
- **Recovery:** Keep the prior compatible capability; quarantine failed staging; leave the feature truthfully unavailable.

### D2 — Platform browser selection + readiness
- **Observable result:** Windows selects Edge → Chrome → managed Chromium; macOS selects
  Chrome → managed Chromium; Safari is an explicit experimental `safaridriver` adapter with
  a truthful warning; the selected engine must complete a loopback-fake readiness transaction.
- **Anchors:** `bootstrap/browser_setup.py`: `probe_msedge_channel`, `install_chromium_fallback`,
  `resolve_browser_channel`; ScoutingEvent browser adapter (B4).
- **Contract:** Presence is insufficient; capability failures follow the documented fallback
  order; auth/schema failures do not fall back by switching engines.
- **Named tests:** `tests/launcher/test_browser_selection.py::test_windows_preference_matrix`;
  `::test_macos_preference_and_experimental_safari`;
  `tests/integration/test_browser_readiness.py::test_selected_engine_completes_local_fake_flow`;
  `::test_auth_and_schema_failures_do_not_fallback`.
- **Recovery:** Fall back only in documented order; retain the prior compatible managed browser.

### D3 — Local immutable capability-payload contract (reduced)
- **Observable result:** Native artifacts + versioned capability payloads form one
  immutable, hash-bound, provider-neutral set validated through a **local fake** for first
  install → interrupted resume → update → offline restart. **No hosted release channel and
  no daily update check (POSTPONED).**
- **Anchors:** `src/scoutmb/ports/releases.py`; `bootstrap/release_channel.py` (local only);
  `tests/fakes/release_server.py`; `release/channel-schema.json`.
- **Contract:** Manifests bind version, ABI, OS, arch, lock digest, sizes, hashes; update
  discovery is manual/bootstrap-triggered, never resolves runtime deps from PyPI.
- **Named tests:** `tests/release/test_release_channel.py::test_immutable_names_and_hash_bound_manifests`;
  `tests/integration/test_release_server.py::test_first_install_resume_update_and_offline_restart`.
- **Recovery:** Retain the last valid immutable set; quarantine the failed candidate; rebuild manifests from the lock.

### D4 — Native thin ≤18 MB Windows & macOS installers
- **Observable result:** A native Windows 11 x64 runner and native macOS 14+ arm64 runner
  each produce a thin installer ≤ 18 MB that installs core without a system Python, can add
  capabilities, and restarts offline; Windows 10 x64 stays best-effort.
- **Anchors:** PyInstaller/launcher build defs; platform bootstrap adapters; release metadata;
  CI jobs `launcher-windows`, `launcher-macos`.
- **Contract:** No cross-build; installer excludes Playwright/browser/OpenCV/PDF/wheelhouse
  (they download during bootstrap); first install consumes only validated payloads;
  notarization deferred (D23), internal-only trust model stated.
- **Named tests:** `tests/release/test_installer_budget.py::test_each_thin_installer_is_at_most_18_mb`;
  `tests/release/test_clean_machine.py::test_first_install_without_system_python_then_offline_restart`;
  `tests/ci/test_release_workflow.py::test_each_installer_uses_a_native_runner`.
- **Recovery:** Do not publish an oversized/cross-built artifact; retain last-known-good installers; reduce closure rather than raise the budget.

### D5 — Redacted diagnostics + no-op telemetry seam (full diagnostics)
- **Observable result:** Structured rotating logs (replacing all `print()`), a sanitized
  one-command support bundle, `ObservabilityPort` + `NoopObservability` + a `TelemetrySpool`
  protocol — no telemetry dependency, spool, or exporter shipped.
- **Anchors:** `src/scoutmb/ports/observability.py`; `src/scoutmb/adapters/telemetry/` no-op;
  `src/scoutmb/logging_setup.py`; the 19 `print()` sites + 3 silent `except`.
- **Contract:** Core never imports OpenTelemetry; default is no-op; event names/attributes
  forbid names/paths/URLs/IDs/tokens/payloads.
- **Named tests:** `tests/observability/test_observability_port.py::test_default_noop_never_persists_or_uses_network`;
  `tests/packaging/test_core_imports.py::test_core_does_not_import_opentelemetry`;
  `tests/privacy/test_diagnostics.py::test_support_bundle_and_event_schema_are_redacted`.
- **Recovery:** Keep `NoopObservability`; reject invalid event DTOs; regenerate only the requested support bundle.

### D6 — Supply-chain: uv audit + license gate (reduced)
- **Observable result:** CI runs a reproducible locked-dependency vulnerability check and a
  **license-compliance gate** that fails on a disallowed/non-redistributable license.
- **Anchors:** CI job `supply-chain`; `uv.lock`; `tools/check_licenses.py`; `release/license-policy.toml`.
- **Contract:** Build tools pinned; `project.version` authoritative. **Per-payload CycloneDX
  SBOMs + exception-expiry POSTPONED.** Hashes do not claim publisher authenticity (signing deferred).
- **Named tests:** `tests/release/test_supply_chain.py::test_vulnerability_and_license_gates`;
  `tests/ci/test_workflow_contract.py::test_supply_chain_is_a_required_job`.
- **Recovery:** Block movement; correct the lock/policy; regenerate; do not waive an unknown license/vuln.

### D7 — Measured resource & performance limits
- **Observable result:** Release config holds measured non-placeholder limits (uploads, PDF
  pages/dimensions, parse time/memory, archives, jobs/workers, queue depth, shutdown grace,
  cache/disk reserve, startup, request counts, runtime, installer size, footprint); request
  counts + growth are hard assertions; controlled wall-time compares repeated samples with variance/regression thresholds.
- **Anchors:** typed config limits; `tools/measure_baseline.py`; performance CI job; synthetic + optional private corpus.
- **Named tests:** `tests/performance/test_resource_limits.py::test_every_release_limit_is_bounded`;
  `tests/performance/test_complexity.py::test_request_and_memory_growth`;
  `tests/property/test_foundation_properties.py::test_parsers_states_and_archive_invariants`.
- **Recovery:** Keep prior limits; reject the candidate; profile; rerun on the same machine class; do not widen limits without evidence.

### D8 — Final acceptance, documentation, legacy retirement
- **Observable result:** All three gates + D1-D7 green; docs let an operator install, update,
  recover, migrate, manage/delete data, run offline, add/remove capabilities, and create
  redacted diagnostics; redundant legacy code removed while compatibility shims remain for the
  transition window.
- **Anchors:** `README.md`; install/update/recovery/migration/privacy docs; `CLAUDE.md`;
  `AGENTS.md`; `GEMINI.md`; compatibility shims; release checklist.
- **Contract:** No default command or automated test contacts the real service; the sole
  live smoke is read-only, manual, `live_service`, two-part opt-in; the first real migration
  requires a verified manual backup; shims kept one release past introduction.
- **Named tests:** `tests/acceptance/test_documented_commands.py::test_all_documented_offline_commands`;
  `tests/acceptance/test_release_contract.py::test_three_gates_and_phase_d_evidence_are_green`;
  `tests/acceptance/test_no_live_service.py::test_only_manual_two_part_opt_in_can_reach_real_service`.
- **Recovery:** Do not publish/migrate the live install; restore the last-known-good bundle; return the failure to its task; rerun D8.

## Carried-forward reference

| Path | Injected failure | Task | Required behavior |
| --- | --- | --- | --- |
| Capabilities | Missing/incompatible/corrupt payload | D1, D2 | Core stays usable; prior capability retained; feature truthfully unavailable |
| Native installer | Cross-build, missing system Python, oversized, offline restart | D4 | Build only on target runner; reject artifact; keep last-known-good |
| Diagnostics | Sensitive value, invalid event DTO, accidental exporter dep | D5 | Reject/redact; keep no-op; data + network unaffected |
| Supply chain | Vulnerability, disallowed license | D6 | Block; regenerate from the lock |
| Resource limits | Queue/cache/disk/memory/time exceeded | D7 | Reject or pause safely with bounded diagnostics |

## Note on final documentation

`CLAUDE.md` still describes the two-script layout and points agents at the code-review-graph
before reading files. D8 rewrites it to match the installed package; the graph must be
rebuilt after the restructure or it will confidently describe a codebase that no longer exists.
