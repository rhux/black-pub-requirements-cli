# Slice 3 — Storage, Migration Hardening & Transactional Releases (PRELIMINARY)

> ⚠️ **PRELIMINARY.** Do not execute. Carries forward the descoped Phase C task structure,
> named tests, and recovery behaviors from the prior planning round. **Refined into a ready
> plan after Slice 2's Gate 2 passes** — transactional releases depend on the durable
> run-state and package boundaries built in Slice 2. No `.tasks.json` sidecar yet; generate
> it (Slice-1 format) when finalizing.

**Spec:** `docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`
**Depends on:** Slice 2 complete (Gate 2 GO).
**Goal:** Manage the installed data root, harden migration, version durable state, and
install releases transactionally with rollback — operating only on throwaway roots and
snapshots, never the live install in place.
**Gate at end:** Gate 3 — migration/release go/no-go.

## How to finalize this slice
1. Confirm Gate 2 is green.
2. Prepare a throwaway copy of the live layout for rehearsals (`build/gate3/...`).
3. Expand each task to Slice-1 fidelity + write the sidecar.

## Descope reminders folded into these tasks
- **OS-backed ownership is POSTPONED.** Carry the existing mtime lock forward unchanged.
- Data lifecycle is **permissions + explicit delete only.** Timed retention and
  backup/staged-restore are POSTPONED.
- Split-brain is a **migration-time hash manifest + old-root marker** (Slice 1 already
  writes the marker). Per-launch monitoring is POSTPONED.
- Transactional install keeps **A/B swap + versioned state + rollback + readiness.** The
  release-channel + daily auto-check are POSTPONED.

## Tasks (preliminary)

### C1 — Installed data root: resolution, permissions, explicit deletion
- **Observable result:** The app resolves a supported data root (never from code location),
  applies current-user permissions, exposes category sizes, and supports explicit deletion.
- **Anchors:** `bootstrap/paths.py`; `src/scoutmb/ports/storage.py`;
  `src/scoutmb/adapters/files/`; `src/scoutmb/ui/settings.py` (from Slice 1).
- **Contract:** Current-user-only permissions on private dirs; explicit per-run deletion; a
  capability probe fails unsupported/removable roots with guidance. **Timed retention +
  backup/restore POSTPONED.**
- **Named tests:** `tests/storage/test_data_roots.py::test_resolution_is_platform_and_code_location_independent`;
  `tests/storage/test_permissions.py::test_current_user_permissions_on_supported_platforms`;
  `tests/storage/test_data_management.py::test_sizes_and_explicit_deletion_contract`.
- **Recovery:** Stop mutation; retain the active root; require explicit operator retry.

### C2 — Carry the existing mtime lock into the restructured launcher (no change)
- **Observable result:** The current mtime-based single-instance lock behavior is preserved
  intact through the restructure; no OS-lock/rendezvous work.
- **Anchors:** `bootstrap/main.py`: `_acquire_lock`, `_release_lock`.
- **Contract:** Behavior parity with today. **OS-backed ownership is POSTPONED (vNext).**
- **Named tests:** `tests/launcher/test_mtime_lock_parity.py::test_lock_behavior_matches_legacy`.
- **Recovery:** Restore the legacy lock code verbatim.

### C3 — Copy-only SHA-256 migration hardening + resumability
- **Observable result:** Migration (basic copy landed in Slice 1) gains per-file SHA-256
  verification, sibling-staging on one filesystem, resumable interruption, and a
  versioned marker written last; originals stay untouched.
- **Anchors:** `bootstrap/migrate.py` (from Slice 1); migration marker contract.
- **Contract:** Never move/delete source; equal hashes dedupe; unequal collisions get
  deterministic preserved names; a manual backup receipt is required before first production run.
- **Named tests:** `tests/migration/test_copy_migration.py::test_source_is_never_modified`;
  `::test_sibling_staging_fsync_promotion_and_marker_contents`;
  `::test_each_interruption_point_resumes_idempotently`;
  `::test_production_mode_requires_manual_backup_receipt`.
- **Recovery:** Leave source + current destination untouched; retain staging; resume from last verified item.

### C4 — Split-brain: migration-time hash manifest + old-root marker
- **Observable result:** Migration records a content hash manifest of the source and leaves
  an explanatory marker in the old root, so a later manual comparison can detect old-root edits.
- **Anchors:** migration inventory/manifest; the old-root marker (Slice 1's `MOVED-README.txt`).
- **Contract:** Content/inventory based, not timestamp-only. **Per-launch automated
  monitoring is POSTPONED — this provides the manifest a manual check would use.**
- **Named tests:** `tests/migration/test_split_brain.py::test_manifest_records_source_hashes`;
  `::test_old_root_receives_explanatory_marker`.
- **Recovery:** Preserve both copies; never auto-merge.

### C5 — Version durable state + activation compatibility tuple
- **Observable result:** Runs, checkpoints, settings, and the activation pointer carry
  schema versions; an activation tuple proves executable + state-generation + capability
  compatibility before startup; unknown/newer state fails closed before mutation.
- **Anchors:** internal state contracts; `bootstrap/marker.py`; `current.json` contract.
- **Contract:** Current and previous release read the supported N/N-1 window; upgrades stage
  and validate before the pointer switch.
- **Named tests:** `tests/contracts/test_state_compatibility.py::test_n_and_n_minus_one_matrix`;
  `::test_unknown_newer_schema_fails_before_write`;
  `tests/integration/test_activation_tuple.py::test_all_components_validated_together`.
- **Recovery:** Reactivate the last-known-good tuple atomically; retain failed staged state as a protected snapshot.

### C6 — Harden downloads, archives, disk budgets, cache ownership (full)
- **Observable result:** Downloads stream to staging and are hash+size validated; archive
  extraction rejects traversal/symlink/device/expansion attacks; disk is preflighted; cache
  eviction is reference-counted and never evicts active/rollback payloads.
- **Anchors:** `bootstrap/downloader.py`; Python/browser/capability installers; safe-extract + cache services.
- **Contract:** All remote payloads are declared in hash-bound release metadata (signing deferred); redirects revalidate scheme/host.
- **Named tests:** `tests/launcher/test_downloader.py::test_stream_hash_size_and_redirect_policy`;
  `tests/security/test_safe_extract.py::test_hostile_archive_matrix`;
  `tests/launcher/test_disk_budget.py::test_active_and_rollback_reserve_is_enforced`;
  `tests/launcher/test_capability_cache.py::test_referenced_payloads_are_not_evicted`.
- **Recovery:** Delete only verified unreferenced staging; keep current + rollback payloads; retry after disk/network available.

### C7 — Transactional release install + readiness + rollback
- **Observable result:** A release installs into a fresh versioned environment, validates
  package + state compatibility, launches with a one-time readiness nonce, then atomically
  switches `current.json`; any failure returns executable + state to the last-known-good tuple.
- **Anchors:** launcher release installer/activator; `bootstrap/main.py`: `_run`;
  `bootstrap/marker.py`; authenticated readiness endpoint.
- **Contract:** Readiness means the expected release + state generation + capability manifest
  + nonce responded; process-alive/open-port alone cannot activate. **Auto-update discovery
  POSTPONED — install/rollback mechanics only.**
- **Named tests:** `tests/launcher/test_transactional_update.py::test_each_failure_point_rolls_back_tuple`;
  `::test_readiness_nonce_and_release_identity`;
  `::test_offline_restart_uses_last_known_good`.
- **Recovery:** Atomically restore the last-known-good pointer + state; retain failed staging; never mutate the working release in place.

## Gate 3 — Migration & release go/no-go
- A throwaway copy of the live layout completes migrate → N→N+1 update → forced rollback →
  N restart; source hashes unchanged; one owner (mtime lock); collisions/old-root edits
  preserved; disk-full/interruption cannot corrupt active data; N restarts offline after
  rollback. **Never run migration against the live installation.**
- **NO-GO:** preserve throwaway evidence, reactivate N, return the failure to its task.

## Carried-forward reference

| Path | Injected failure | Task | Required behavior |
| --- | --- | --- | --- |
| Data root | Unsupported filesystem, permission failure, protected deletion | C1 | Fail before mutation; show active root; preserve protected data |
| Migration | Collision, interruption, race, disk full | C3, C4 | Source untouched; same-filesystem verified promotion; preserve both |
| Update | Bad hash/archive, readiness failure, incompatible state | C5-C7 | No activation, or atomic rollback of executable + state tuple |
| Downloads | Hostile archive, oversized, hash mismatch, disk exhaustion | C6 | Reject before activation; keep current install/cache valid |
