# Slice 1b — Full Phase A Characterization

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers-extended-cc:executing-plans`.
> Execute tasks in order unless their dependency lists permit otherwise. Checkbox state is
> mirrored in the `.tasks.json` sidecar.

**Status:** READY FOR EXECUTION
**Parent spec:** `docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`
**Matrix spec:** `docs/superpowers/specs/2026-07-22-phase-a-characterization-matrix-design.md`
**Companion:** `2026-07-22-slice-1a-in-place-correctness.md` — Gate 1a is complete.
**Slice:** 1b of 5. Gate 1b unblocks Slice 2.

## Outcome

Build the reusable behavior oracle for every legacy boundary Slice 2 moves. The oracle is a
typed, data-only catalog of stable case IDs, an independent axis manifest, strict synthetic
builders/fakes, normalized observations, explicit privacy policies, and legacy harnesses.
Slice 2 adds new-package harnesses around the same cases instead of rewriting expectations.

Slice 1b does not fix production behavior. It records current behavior as `preserve` or a
temporary `intentional-change` tripwire, and records future-only work as `new-acceptance`
with an owning later slice. The one tooling correction in this plan is
`tools/verify_corpus.py`: it must distinguish schedule, requirement, and unrecognized rows
before it can serve as the authentic-corpus oracle.

## Locked implementation rules

- No private file, name, ID, token, description, payload, PDF, hash, or derived fixture is
  committed. `raw_data/` is read-only evidence.
- The default and browser suites make no external request. Only loopback fakes are allowed.
- Case data never imports the legacy implementation or optional dependencies.
- Use frozen/slotted domain dataclasses, enums, and typed runner protocols; do not create a
  universal `MatrixCase[Any, Any]`, YAML framework, reflection registry, or assertion lambda.
- Fakes validate parameters, order, timing, and scripted response consumption. Unexpected or
  extra calls fail.
- Harnesses fake only external boundaries; they never patch the parser, inference function,
  writer, route, or other behavior being asserted.
- Every axis has at least two focused cases. Finite members are exhaustive. High-risk failure
  axes have immediate-success, recoverable-failure, and terminal-failure cases.
- Exact shape/schema tests compare full ordered structures and counts, never subsets or mere
  presence.
- `pytest.importorskip` is forbidden in required lanes. Missing corpus/browser capability is
  an exact automatic skip only in ordinary local pytest; `--require-corpus` and
  `--require-browser` fail Gate 1b.
- All case IDs, axes, classifications, evidence, legacy observations, target observations,
  and owners are concrete. No `TBD`, “representative”, “optionally extend”, or unchecked
  completeness prose may remain.

## Test package shape

```text
tests/matrix/
  model.py
  axes.py
  policies.py
  registry.py
  boundaries.py
  cases/{input,pdf,requirement,acquisition,artifact,interface,platform}_cases.py
  scale_profile.py
  test_registry.py
tests/factories/{inputs,payloads,pdf_builder,scale}.py
tests/fakes/{acquisition,browser,clock}.py
tests/harnesses/{legacy,browser,corpus,subprocess}.py
tests/plugins/matrix_gate.py
tests/characterization/test_{input,pdf,acquisition,requirement,artifact,interface,platform}_matrix.py
tests/vertical/test_legacy_flows.py
tests/scale/test_profiles.py
tests/private_corpus/test_authentic.py
```

Existing focused tests remain until the catalog covers them. Consolidate duplicate helpers,
but do not delete an existing assertion unless its stable replacement is named in the same
commit.

---

## Task 16: Correct corpus truth and build the matrix kernel

**Depends on:** Gate 1a

**Files:**

- Modify: `tools/verify_corpus.py`
- Modify: `tests/tools/test_verify_corpus.py`
- Modify: `tests/conftest.py`
- Modify: `pyproject.toml`
- Create: `tests/matrix/{model,axes,policies,registry,boundaries}.py`
- Create: `tests/matrix/test_registry.py`
- Create: `tests/harnesses/{corpus,subprocess}.py`
- Create: `tests/plugins/matrix_gate.py`
- Create: `tests/private_corpus/test_authentic.py`

### Case and audit inventory

| IDs | Classification | Exact assertion |
| --- | --- | --- |
| `CORP-SPLIT-001` | preserve | A mixed synthetic payload reports `data_rows=2`, `schedule_rows=1`, `requirement_rows=1`, `unrecognized_rows=0`; requirement shapes/flags exclude the schedule row. |
| `CORP-SPLIT-002` | preserve | A requirement-schema row with absent completion flags remains a requirement, proving classification is schema-based rather than flag-only. |
| `CORP-SPLIT-003`, `CORP-SPLIT-004` | preserve | Ambiguous mapping and non-mapping `data` entries increment `unrecognized_rows`; required authentic verification fails with bounded redacted output. |
| `CORP-CLI-001`, `CORP-CLI-002` | preserve | Valid aggregate-only CLI output exits 0 and contains no fixture description; absent corpus exits 2 on stderr. |
| `CORP-CANON-001` | preserve | Required private lane asserts 120 payloads, 4,961 data rows, 103 schedule rows, 4,858 requirement rows, 98 deduplicated classes, four flag combinations, three types, 26 shapes, 31 empty numbers, and 125 `Note.` rows for one canonical snapshot. |
| `CORP-SNAPSHOT-001`, `CORP-SNAPSHOT-002` | preserve | Three dated runs have identical raw-payload multisets; counts are not multiplied, and a synthetic differing run is detected. |
| `CORP-FP-001` … `CORP-FP-004` | preserve | Unchanged tree passes; content mutation fails; symlink/non-regular entry fails; metadata-only difference does not change the content fingerprint. No path/hash is emitted. |
| `CORP-MODE-001` … `CORP-MODE-004` | preserve | Auto mode skips absent corpus with one exact reason; present corpus executes; `--require-corpus` fails absence/wrong layout; alternate `--corpus-dir` is honored. |
| `REG-ID-001`, `REG-ID-002` | new-acceptance (1b) | Unique IDs pass; duplicate IDs fail. |
| `REG-AXIS-001` … `REG-AXIS-006` | new-acceptance (1b) | Unknown axis, missing finite member, fewer than two focused cases, missing required interaction, unmapped boundary, and unreviewed branch exclusion each fail. |
| `REG-META-001` … `REG-META-005` | new-acceptance (1b) | Placeholder text, incomplete evidence, missing later owner, intentional change lacking either observation, and privacy-policy mismatch each fail. |
| `REG-LANE-001` … `REG-LANE-004` | new-acceptance (1b) | Empty, deselected, skipped, or duplicated required case IDs fail the active lane audit. |

### Steps

- [ ] Add the mixed-row tests first. Confirm they fail because `summarize_run` currently
  labels every mapping as a requirement.
- [ ] Replace the single `requirements` counter with partitioned `data_rows`,
  `schedule_rows`, `requirement_rows`, and `unrecognized_rows`. Implement named schema
  predicates and keep aggregate output privacy-safe.
- [ ] Define `Classification`, `EvidenceKind`, `Domain`, and `SurfaceClass` enums;
  frozen/slotted `CaseMetadata`; domain observation types; and generic runner protocols.
- [ ] Define independent `AxisSpec` and boundary manifests. Keep registries data-only and
  free of optional imports.
- [ ] Define the surface-policy model and seed it with every surface in the matrix spec.
- [ ] Add pytest options `--corpus-dir`, `--require-corpus`, `--require-browser`, and
  `--matrix-lane={default,browser,authentic}` plus markers `private_corpus`, `playwright`,
  `scale`, `vertical`, and `intentional_change`.
- [ ] At root-conftest import time, force `SCOUTMB_DATA_DIR` to a session-owned temporary
  directory before test modules are collected; clean it at session end. Do not rely on a
  fixture or `SCOUTMB_DEV=1`.
- [ ] Implement lane accounting in `tests/plugins/matrix_gate.py`: collect stable IDs,
  record pass/fail/skip, and fail session finish when the active lane's required IDs did
  not execute exactly once.
- [ ] Implement the content-tree fingerprint over relative path, entry type, size, and
  SHA-256; reject symlinks/devices; never serialize hashes.
- [ ] Configure branch coverage so later reports can include the legacy flat modules and
  scoped bootstrap code, not only `src/scoutmb`.

**Verify:**

```bash
uv run pytest tests/tools/test_verify_corpus.py tests/matrix/test_registry.py -q
uv run pytest tests/private_corpus/test_authentic.py --corpus-dir raw_data --require-corpus --matrix-lane authentic -q
uv run ruff check tests/matrix tests/harnesses tests/plugins tools/verify_corpus.py
uv run mypy tests/matrix tests/harnesses tools/verify_corpus.py
```

**Expected:** all commands exit 0; the authentic command executes `CORP-CANON-001` rather
than skipping; `git status --short raw_data` is empty before and after.

**Commit:** `test: add typed matrix kernel and correct corpus oracle`

---

## Task 17: Complete the input-loader matrix

**Depends on:** Task 16

**Files:**

- Create: `tests/matrix/cases/input_cases.py`
- Create: `tests/factories/inputs.py`
- Create: `tests/characterization/test_input_matrix.py`
- Extend: `tests/harnesses/subprocess.py`
- Update: `tests/matrix/{axes,boundaries}.py`

### Case inventory

| IDs | Required members and exact assertions |
| --- | --- |
| `IN-FORMAT-001` … `IN-FORMAT-008` | CSV, XLSX, JSON list, `scouts` wrapper, `data` wrapper, single dictionary, JSON string row, and text all normalize to the exact ordered `ScoutInput` observations. |
| `IN-ALIAS-NAME-001` … `003` | `Attendee Name`, `Name`, `Scout Name` are exhaustive name aliases in CSV and XLSX contexts. |
| `IN-ALIAS-URL-001` … `004` | `QR Code Contents`, `URL`, `QR URL`, `Link` are exhaustive URL aliases in CSV and XLSX contexts. |
| `IN-ALIAS-TYPE-001`, `002` | `Registrant Type` and `Type` are exhaustive type aliases. |
| `IN-HEADER-001` … `004` | UTF-8 BOM, case/punctuation normalization, whitespace, and unknown headers produce exact current observations. |
| `IN-XLSX-SHEET-001` … `003` | Requested sheet wins, then `Scouts Only`, then first sheet; empty workbook and missing URL column have separate exact error cases `IN-XLSX-ERR-001`, `002`. |
| `IN-JSON-001` … `006` | `name`/`attendee_name`, `url`/`qr_url`/`qr_code_contents`, `registrant_type`/`type`, string items, ignored non-string/non-mapping items, and malformed top-level data are pinned. |
| `IN-TEXT-001` … `004` | URL-only, `name,url`, blank/comment, and comma-without-HTTPS lines preserve exact parsing and order. |
| `IN-FILTER-001` … `006` | Valid prefix, invalid scheme/host/path, Adult, Part-Time Adult, include-adults, and all-filtered error are exact. |
| `IN-DEDUP-001`, `002` | First duplicate URL wins across different names; distinct URLs for the same name remain distinct. |
| `IN-EMPTY-001`, `002` | Empty input and recognized-but-empty/all-filtered input raise the exact current exception class and bounded message. |
| `IN-IMPORT-001` … `004` | Fresh subprocess profiles `base`, `pdf`, `acquisition`, and `all` pin current eager optional-import behavior without `sys.modules` contamination. Current failures are intentional-change tripwires owned by Slice 2. |

### Steps

- [ ] Add all input `AxisSpec` members and boundary mappings first; run the registry audit
  and observe missing-member failures.
- [ ] Build files at test time with synthetic names/tokens only. Do not commit XLSX binaries.
- [ ] Parameterize domain cases through the legacy harness and compare complete ordered
  observations, not only the first result.
- [ ] Exercise optional-import cases in fresh subprocesses using an import blocker and a
  real-symbol probe. Do not add `sys.path.insert` to test modules.
- [ ] Add bounded Hypothesis strategies for header punctuation/whitespace and text rows;
  assert invariant normalization, stable order, and no unexpected exception.
- [ ] Run privacy scanning across factory source and generated files.

**Verify:**

```bash
uv run pytest tests/characterization/test_input_matrix.py tests/matrix/test_registry.py -q
uv run pytest tests/characterization/test_input_matrix.py -k import -q
uv run ruff check tests/matrix/cases/input_cases.py tests/factories/inputs.py tests/characterization/test_input_matrix.py
```

**Expected:** every `IN-*` ID executes once; no optional-import test is skipped; registry and
privacy audits pass.

**Commit:** `test: characterize the complete legacy input matrix`

---

## Task 18: Complete the PDF and PDF-CLI matrix

**Depends on:** Task 16

**Files:**

- Create: `tests/matrix/cases/pdf_cases.py`
- Create: `tests/factories/pdf_builder.py`
- Create: `tests/characterization/test_pdf_matrix.py`
- Update: `tests/matrix/{axes,boundaries}.py`

### Case inventory

| IDs | Required members and exact assertions |
| --- | --- |
| `PDF-DISC-001` … `006` | Direct file, directory, glob, recursive directory, overlapping inputs, and missing/non-PDF inputs assert resolved case-insensitive sort, path dedup, and exact emptiness. |
| `PDF-ID-001` … `008` | Present fields plus every non-empty combination of missing name/type/QR assert exact attendee and `ExtractionError` schemas; blank page emits neither attendee nor false success. |
| `PDF-CASE-001` … `004` | Narrow obvious-case normalization fixes `MIles`; disabled normalization, `McDonald`, and `AJ` remain exact. |
| `PDF-QR-001` … `006` | Embedded success, rendered fallback, ScoutingEvent-value preference, first nonmatching fallback, multiple symbol dedup/order, and total decode failure assert value and method. |
| `PDF-PAGE-001`, `002` | Multipage and multi-PDF input preserve page/file order. |
| `PDF-CORRUPT-001`, `002` | Corrupt PDF and corrupt embedded image produce bounded errors without an uncaught exception. |
| `PDF-DEBUG-001`, `002` | QR failure with/without debug directory asserts exact PNG creation/non-creation and safe filename. |
| `PDF-FILTER-001` … `006` | Adult defaults/custom adult type, include adults, ScoutingEvent-only, duplicate QR default, and keep-duplicates assert exact retained rows/counts. |
| `PDF-SCHEMA-001`, `002` | Attendee CSV and error CSV compare exact seven/five ordered headers and exact row encoding. |
| `PDF-CLI-001` … `008` | Defaults/help, no match, invalid DPI low/high, normal success, strict warning exit 1, quiet success, and stale error-file removal assert exact exit code and stdout/stderr separation. Quiet prints only the final path on stdout. |

### Steps

- [ ] Register all PDF axes/members and observe registry failures before adding cases.
- [ ] Implement a deterministic test-time PDF builder for text lines, raster embedded QR,
  vector/rendered QR, multiple pages, blank pages, and deliberately corrupt input. Generated
  binaries live only below `tmp_path`.
- [ ] Exercise real `expand_pdf_inputs`, extraction, decoder tiers, CSV writers, and `main`.
  Mock only image-decoder failure injection where constructing that decoder state is
  impractical; do not mock `extract_pdf` in CLI cases.
- [ ] Assert full stdout and stderr line lists, complete schemas, file counts, and cleanup.
- [ ] Add bounded properties for DPI sequences, filename Unicode, and discovery overlap.

**Verify:**

```bash
uv run pytest tests/characterization/test_pdf_matrix.py tests/matrix/test_registry.py -q
uv run ruff check tests/matrix/cases/pdf_cases.py tests/factories/pdf_builder.py tests/characterization/test_pdf_matrix.py
```

**Expected:** every `PDF-*` ID executes exactly once with no skip; generated PDFs and debug
images exist only under pytest temporary roots.

**Commit:** `test: characterize PDF extraction and CLI behavior`

---

## Task 19: Complete acquisition, retry, strict-fake, and local-browser coverage

**Depends on:** Task 16

**Files:**

- Create: `tests/matrix/cases/acquisition_cases.py`
- Create: `tests/fakes/{acquisition,browser,clock}.py`
- Create: `tests/fakes/test_strict_fakes.py`
- Create: `tests/harnesses/browser.py`
- Create: `tests/characterization/test_acquisition_matrix.py`
- Create: `tests/characterization/test_browser_matrix.py`
- Update: `tests/matrix/{axes,boundaries}.py`

### Case inventory

| IDs | Required members and exact assertions |
| --- | --- |
| `ACQ-RESP-001` … `004` | Schedule URL+POST recognition succeeds; wrong URL, method, and body do not. |
| `ACQ-ID-001` … `004` | Present attendee ID, absent ID, blank ID, and repeated form key (last wins) assert exact result/error. |
| `ACQ-SCHED-001` … `005` | Empty, one, multiple, failed status, and missing/falsey data assert classes/errors/raw output. |
| `ACQ-DEDUP-001` … `005` | Unique IDs, missing IDs, duplicate incomplete→complete, complete→incomplete, and equal duplicates assert order and retained row exactly. |
| `ACQ-HASREQ-001`, `002` | Nonblank `HAS_REQ=1` and `HAS_REQ=0` classes both currently request requirements; the latter is intentional-change owned by Slice 2. Blank class ID never requests. |
| `ACQ-REQ-001` … `006` | Success, failed status, empty data, missing fields, unknown fields, and non-list/invalid data assert current mapping/coercion/error behavior. |
| `ACQ-RETRY-001` … `003` | Immediate success, transient failures then success, and three terminal failures assert attempts and waits `[500,1000,1500]` exactly. |
| `ACQ-DELAY-001`, `002` | Zero and positive request delay assert exact wait calls. |
| `ACQ-RAW-001` … `003` | Schedule/requirement raw files have output-UUID filenames, exact content, and no collision for same-name attendees. |
| `ACQ-CLEAN-001` … `003` | Success, schedule exception, and terminal requirement failure close context/page resources and leave no pending scripted response. |
| `ACQ-ASSET-001`, `002` | Dead assets are aborted by default and continued when allowed. |
| `FAKE-STRICT-001` … `006` | Wrong attendee ID, class ID, order, delay, extra call, and unconsumed response each fail the fake's own contract test. |
| `BROWSER-LOCAL-001` … `004` | Loopback fake captures schedule POST, serves requirement JSON, exercises browser interception, and completes without external request. |
| `BROWSER-EGRESS-001` … `006` | Navigation, redirect, frame, popup, worker/fetch, and WebSocket attempts outside loopback fail the browser sentinel. |

### Steps

- [ ] Register acquisition/browser axes before cases and confirm the audit fails.
- [ ] Move reusable fake behavior out of test modules. Implement strict scripted request and
  browser fakes with typed expectations, call logs, and `assert_consumed()`.
- [ ] Use injected fake clock/sleeper observations; never sleep in focused tests.
- [ ] Characterize `process_scout` through external seams only. Assert whole records, request
  bodies/counts/order, raw artifacts, delays, and cleanup.
- [ ] Start a loopback-only fake service for Playwright. Install external-request listeners
  before page creation and cover redirects, frames, popups, workers, fetch/XHR, and WebSockets.
- [ ] Add `--require-browser` preflight that fails rather than skipping when the browser lane
  is required.

**Verify:**

```bash
uv run pytest tests/fakes/test_strict_fakes.py tests/characterization/test_acquisition_matrix.py tests/matrix/test_registry.py -q
uv run pytest tests/characterization/test_browser_matrix.py -m playwright --require-browser --matrix-lane browser -q
```

**Expected:** focused and browser commands exit 0; browser lane executes all required
`BROWSER-*` IDs and reports zero external requests.

**Commit:** `test: characterize acquisition and guarded browser contracts`

---

## Task 20: Complete inference, artifact, failure, and privacy coverage

**Depends on:** Task 16

**Files:**

- Create: `tests/matrix/cases/{requirement,artifact}_cases.py`
- Create: `tests/characterization/test_requirement_matrix.py`
- Create: `tests/characterization/test_artifact_matrix.py`
- Create: `tests/privacy/test_surface_policies.py`
- Update: `tests/factories/{payloads,scale}.py`
- Update: `tests/matrix/{axes,policies,boundaries}.py`

### Requirement case inventory

`REQ-SHAPE-001` … `REQ-SHAPE-026` cover these exact normalized members once through
`requirement_path` and once through a complete tree/consumer flow:

```text
#Na, #N(a), #N., N.a., #Na., N., #N, #N.Aaaaaa.A.(N), <empty>, Aaaa.,
N.a.N., #N(a)(N), #N.Aaaaaa.A(N), #(a), N, #N.Aaaaaa.A.(N)(a),
#N..Aaa.A.(N), #Na(N), #N..Aaa.A.(N)(a)(N), Aaaa.Aaaa., #Na[N],
Aaaa.N., #(N), #A., #N..Aaa.A.(N)(a), #N.AaaaaaA.(N)
```

| IDs | Required members and exact assertions |
| --- | --- |
| `REQ-FLAG-001` … `008` | All four completion-flag pairs execute in leaf and parent/consumer contexts with exact calculated status and selected output. |
| `REQ-TYPE-001` … `003` | Types 1, 2, and 3 assert exact leaf/header/exclusion behavior. |
| `REQ-CLASS-001`, `002` | Both class-completion states preserve exact mapping/consumer output. |
| `REQ-EMPTY-001`, `002` | Empty display number with/without current top level pins path `()` behavior and consumer placement. |
| `REQ-NOTE-001`, `002` | `Note.` following a numbered requirement and at the beginning pin current graft/fallback behavior. |
| `REQ-TREE-001` … `006` | Leaf, parent, grandparent, missing parent, malformed numbering, and label rows assert ancestry/depth/order. |
| `REQ-CHOICE-001` … `030` | `do`, `complete`, `choose`, `select`, `perform` each test below/equal/above threshold with both digit and word counts. |
| `REQ-EXCLUDE-001`, `002` | `(not used)` and type 3 never become actionable leaves. |
| `REQ-NONMUTATE-001`, `002` | Successful and malformed inputs remain byte/deep-equal after annotation/build. |
| `REQ-IDENTITY-001` … `003` | Same name/different IDs isolate; same ID groups; blank defensive fallback is pinned as current behavior. |

### Artifact, policy, and failure inventory

| IDs | Required members and exact assertions |
| --- | --- |
| `ART-SCHEMA-001` … `008` | `scouts.json`, classes, requirements, errors, summary, report data, email CSV, and email text/HTML compare exact ordered keys/headers/counts and empty/error variants. |
| `ART-HTML-001` … `005` | `__REPORT_DATA__` is replaced exactly once; `</script>`, `<>&`, U+2028/U+2029, and Unicode parse safely with no residual sentinel. |
| `ART-EMAIL-001` … `004` | Missing, all-complete, no-data, and same-name attendees assert status, conditional files, filenames, and bodies. |
| `ART-NAME-001` … `006` | Traversal, absolute path, Unicode, case-only collision, Windows reserved name, and empty name assert current safe-name/output behavior and target owner. |
| `ART-FORMULA-001` … `006` | `=`, `+`, `-`, `@`, tab, and CR prefixes are asserted in every outward spreadsheet column as current tripwires with Slice 2 target expectations. |
| `ART-FAIL-001` … `006` | Failure before render, temp write, before replace, after replace, cleanup, and between sibling writers assert prior bytes, temp cleanup, reported state, and partial publication exactly. |
| `PRIV-INPUT-001/002`, `PRIV-ADAPTER-001/002`, `PRIV-OPS-001/002`, `PRIV-SHARE-001/002`, `PRIV-UI-001/002`, `PRIV-DIAG-001/002` | Each surface class has separate allowed-value and forbidden-sentinel cases enforcing its exact field policy. |
| `PRIV-EGRESS-001` … `010` | Filenames, JSON, CSV, HTML, email, stdout, stderr, API error, SSE, and diagnostics each pin current leakage or target-safe behavior with explicit owner. |
| `PRIV-CONTAIN-001`, `002` | Adapter-private data remains inside selected root and never appears in generated shareable/support surfaces. |

### Steps

- [ ] Replace the old 18-shape fixture list with the 26-member normalized catalog and
  privacy-safe concrete values. Keep expected shape members in the independent axis manifest.
- [ ] Add every requirement axis before cases and observe registry failures.
- [ ] Run each shape through both path and tree/consumer harnesses. Do not satisfy the rule by
  calling the same parser twice.
- [ ] Test HTML and email consumers independently using the same requirement case inputs.
- [ ] Materialize every surface policy from the matrix spec. Scanner tests cover committed
  factories and non-adapter generated surfaces; adapter-private tests enforce allowlists and
  containment instead of flagging expected private sentinels.
- [ ] Inject filesystem failures at the real I/O boundary and assert prior bytes plus cleanup.
- [ ] Use exact full structures and occurrence counts; no subset-key or “contains token”
  assertions may stand in for schema tests.

**Verify:**

```bash
uv run pytest tests/characterization/test_requirement_matrix.py tests/characterization/test_artifact_matrix.py tests/privacy/test_surface_policies.py tests/matrix/test_registry.py -q
uv run python tools/check_private_data.py tests
```

**Expected:** all 26 shape members execute in both contexts; all six surface classes and ten
egress cases execute; privacy findings are zero outside explicitly allowlisted adapter-private
test outputs.

**Commit:** `test: characterize inference artifacts and privacy surfaces`

---

## Task 21: Complete interfaces, lifecycle, desktop, and scoped-platform coverage

**Depends on:** Tasks 16 and 19

**Files:**

- Create: `tests/matrix/cases/{interface,platform}_cases.py`
- Create: `tests/characterization/test_interface_matrix.py`
- Create: `tests/characterization/test_platform_matrix.py`
- Create: `tests/characterization/test_static_ui.py`
- Update: `tests/harnesses/{legacy,browser}.py`
- Update: `tests/matrix/{axes,boundaries}.py`

### Case inventory

| IDs | Required members and exact assertions |
| --- | --- |
| `CLI-SCHED-001` … `006` | Defaults, successful empty/single batch, partial failure, top-level exception, and keyboard interrupt assert exact exit/stdout/stderr and output invocation. |
| `CLI-PDF-001` … `008` | Reuse Task 18 cases; interface registry proves both CLIs have complete option/default/exit/channel mappings without duplicate expectations. |
| `UI-IMPORT-001`, `002` | Import with sandboxed root creates only the temporary tree; current import-time creation is an intentional-change tripwire. Plain collection never touches user data. |
| `UI-ROUTE-001` … `012` | Every route/method—health, status, scouts, PDF start, schedule start, pause, resume, operation events, runs, open report, generate emails, open email folder—asserts exact status and response schema for present/missing/busy/error states. |
| `SSE-FRAME-001` … `006` | Batch start, scout start/done, pause/resume, batch done, and error/terminal sequences assert exact ordered `data:` frames, JSON schemas, blank-line framing, and one terminal end. |
| `SSE-CLEAN-001` … `004` | Success, worker exception, terminal failure, and client disconnect remove operation/queue state and leave no pending task or busy flag. |
| `RUN-LIST-001` … `004` | Empty, multiple sorted runs, corrupt summary, and missing optional report assert exact results. |
| `RUN-ID-001` … `004` | Valid, traversal, absolute, and separator-containing run IDs assert containment/error. |
| `UI-ACTION-001` … `004` | Current server-side browser open, Windows-only folder open, email generation, and unguarded JSON behavior are executable intentional-change tripwires with Slice 2 owners. |
| `STATIC-UI-001` … `003` | Local Playwright success, progress/paused, and error flows prove the DOM consumes exact API/SSE schemas and renders expected terminal state. |
| `DESK-PORT-001`, `002` | Free port binds loopback and closes probe resources; bind failure is surfaced. |
| `DESK-READY-001` … `003` | Immediate readiness, retries then readiness, and timeout assert monotonic attempts without real sleep. |
| `DESK-MODE-001` … `004` | Browser/native modes, server startup failure, and keyboard interrupt assert process/browser/window behavior and cleanup. |
| `BOOT-PATH-001` … `004` | Override/default root, spaces, and Unicode assert resolved layout without writing outside temp roots. |
| `BOOT-MARK-001` … `006` | Missing, valid, corrupt JSON, schema mismatch, Python mismatch, and requirements-hash mismatch assert validity exactly. |
| `BOOT-SYNC-001` … `004` | File and directory copy, missing optional source, frozen/unfrozen source root, and copied-release startup assert scoped source-copy behavior. |
| `PLAT-WIN-001` … `008` | Reserved devices, trailing dot/space, case-only collision, backslash/slash, drive, UNC, extended path, and traversal are simulated pure observations with explicit target owners. |
| `PLAT-MAC-001` … `005` | NFC/NFD, case-only collision, volume root, spaces/Unicode, and traversal are simulated pure observations with explicit target owners. |

### Steps

- [ ] Register all interface/platform axes and exact route/method members before cases.
- [ ] Implement a `load_legacy_ui(data_root)` harness that sets environment before import,
  removes/reloads `ui.server` deliberately, and resets globals before and after each case.
- [ ] Execute SSE generators and HTTP routes; never scan source text for event strings.
- [ ] Configure async tests to fail on leaked tasks/resources. Drive clocks/events rather than
  sleeping.
- [ ] Run static UI only against loopback fake APIs/SSE with the guarded browser harness.
- [ ] Test platform normalization as pure inputs/observations. Do not claim native Windows or
  macOS filesystem behavior and do not import full provisioning/installer modules.
- [ ] Pin scoped bootstrap paths, markers, source copy, and copied startup only; leave browser
  install, downloads, locks, WebView2, native packaging, and provisioning to Slices 3/4.

**Verify:**

```bash
uv run pytest tests/characterization/test_interface_matrix.py tests/characterization/test_platform_matrix.py tests/matrix/test_registry.py -q
uv run pytest tests/characterization/test_static_ui.py -m playwright --require-browser --matrix-lane browser -q
```

**Expected:** route/method inventory is exact; no source-presence tests; no user-data write;
no leaked async resources; both Windows and macOS simulated seams execute.

**Commit:** `test: characterize interfaces lifecycle and platform seams`

---

## Task 22: Add vertical flows, scale profiles, baselines, and close Gate 1b

**Depends on:** Tasks 17–21

**Files:**

- Create: `tests/factories/scale.py`
- Create: `tests/matrix/scale_profile.py`
- Create: `tests/scale/test_profiles.py`
- Create: `tests/vertical/test_legacy_flows.py`
- Create: `tests/performance/test_phase_a_baseline.py`
- Create: `tools/measure_baseline.py`
- Create: `tests/baselines/phase_a.json`
- Update: `tests/matrix/{axes,boundaries,registry}.py`
- Update: `tests/conftest.py`, `pyproject.toml`

### Scale, flow, and baseline inventory

| IDs | Exact assertion |
| --- | --- |
| `SCALE-000`, `SCALE-001`, `SCALE-002` | Zero, one, and two same-name/different-ID attendees assert empty/minimum/identity behavior. |
| `SCALE-SMALL-001` … `003` | Named deterministic small profiles vary attendee count/grouping/order and reproduce from profile version+seed. |
| `SCALE-CANON-022` | Exactly 22 attendees, 103 raw class rows, five duplicate rows, 98 deduplicated classes/payloads, and 4,858 requirements with exact safe marginals. |
| `SCALE-LARGE-050` | Fifty attendees complete with deterministic totals/order and bounded request growth. |
| `SCALE-PROP-001`, `002` | Bounded generated counts assert partition totals, identity isolation, order, and no exception; no correlation assertion is permitted. |
| `SCALE-PAIR-001`, `002` | Reordering the intentionally synthetic marginal pairing preserves all permitted assertions; a test attempting a cross-axis correlation is rejected by profile API/metadata. |
| `FLOW-SUCCESS-001` | Generated PDF → attendee CSV → real loader → strict fake acquisition → real inference/writers → real UI read routes, with exact request/artifact/schema/cleanup assertions. |
| `FLOW-PARTIAL-001` | One success plus one terminal attendee failure produces truthful partial results, exit/status/events/artifacts, and complete cleanup. |
| `FLOW-BROWSER-001` | Local Playwright schedule interception plus static UI succeeds entirely on loopback with zero egress. |
| `PERF-REQ-001` … `003` | Request counts for zero, canonical, and larger profiles are exact. Legacy requests requirements for every nonblank class ID, including `HAS_REQ=0`; that current rule is not mislabeled as “requirement-bearing only.” |
| `PERF-GROWTH-001`, `002` | Tree/inference and artifact row counts grow within reviewed algorithmic bounds; no portable wall-clock threshold is introduced. |

### Generator contract

- Profile/schema version and seeds are explicit and serialized in safe baseline metadata.
- `SCALE-CANON-022` assigns exact shape, flag, type, and class-completion marginals using a
  deterministic stable allocation. Their row-level pairing is intentionally synthetic.
- Tests may assert marginals, topology, ordering, counts, and algorithmic behavior only.
  Correlation-sensitive expectations require focused cases supported by code semantics or
  separately approved privacy-safe joint evidence.
- Smaller profiles use documented largest-remainder allocation and stable tie-breaking;
  they assert totals/invariants rather than impossible tiny-profile marginals.

### Steps

- [ ] Add all scale/flow axes and expected case IDs before implementation.
- [ ] Implement deterministic profiles without copying a corpus row or string. Add a policy
  guard that prevents consumers from treating synthetic pairings as corpus evidence.
- [ ] Implement both vertical flows with real legacy boundaries. Assert preconditions so a
  missing generated PDF/CSV/artifact cannot result in a vacuous pass.
- [ ] Measure request counts and scoped branch coverage. Write only safe aggregate baseline
  metadata to `tests/baselines/phase_a.json`: schema/profile version, case IDs, request/row
  counts, per-area coverage totals, and reviewed exclusions. No path, host identity, time,
  private hash, or portable timing threshold.
- [ ] Replace every remaining old helper import with `tests/fakes`/`tests/harnesses`; preserve
  existing assertions under named matrix cases.
- [ ] Run all lanes below. Review the exact branch report; every uncovered scoped branch must
  gain a case or a stable reviewed exclusion ID in the boundary manifest.
- [ ] Regenerate the `.tasks.json` sidecar only after the plan text is final.

## Gate 1b — go/no-go

Run each lane separately so a marker cannot hide another lane:

```bash
# Static quality and matrix integrity
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python tools/check_private_data.py tests
uv run pytest tests/matrix/test_registry.py -q

# Default synthetic: focused, scale, and vertical; no browser/private/live cases
uv run pytest -m "not live_service and not playwright and not private_corpus" --matrix-lane default -q

# Required local browser lane
uv run pytest -m playwright --require-browser --matrix-lane browser -q

# Required authentic read-only lane
uv run pytest -m private_corpus --corpus-dir raw_data --require-corpus --matrix-lane authentic -q

# Scoped legacy branch coverage
uv run coverage erase
uv run coverage run --branch -m pytest -m "not live_service and not playwright and not private_corpus" --matrix-lane default -q
uv run coverage report --include="scout_schedule_cli.py,pdf_to_scouts.py,ui/server.py,run_app.py,bootstrap/paths.py,bootstrap/marker.py,bootstrap/source_sync.py" --show-missing

# Baseline and private-tree immutability
uv run python tools/measure_baseline.py --profile canonical-22 --output build/phase-a-baseline.json
git status --short raw_data
```

**GO requires all of the following:**

- [ ] Every command exits 0.
- [ ] Every preserve and intentional-change ID executes exactly once in its required lane.
- [ ] Every new-acceptance case has a later owner.
- [ ] Every `AxisSpec` member, material interaction, scoped boundary, and critical flow maps
  to concrete case IDs.
- [ ] No required case is skipped/deselected and no lane has an empty required set.
- [ ] All 26 shapes run in path and tree/consumer contexts; all finite flag/type/class sets
  are exhaustive.
- [ ] Default/browser lanes report zero external requests.
- [ ] Authentic lane reports the canonical 103/4,858/4,961 split and leaves `raw_data/`
  unchanged.
- [ ] All surface-policy, formula-injection, platform, async cleanup, strict-fake, and
  vertical-flow cases execute.
- [ ] Scoped branch report has no uncovered branch without a stable reviewed exclusion.
- [ ] `tests/baselines/phase_a.json` contains reviewed aggregate values and no placeholders or
  private/machine-identifying data.
- [ ] No wall-clock performance threshold is introduced.

Any failed condition is **NO-GO**. Slice 2 must not start until Gate 1b is green.

**Commit:** `test: close exhaustive Phase A characterization gate`

## Recovery and compatibility

- All new fixtures and generated outputs are synthetic and disposable.
- Characterization failures do not authorize production fixes. Record the observation or
  obtain separate approval for a change, then classify it with an owner.
- If private counts differ, stop and inspect schema/provenance. Never weaken the verifier or
  copy private rows into tests.
- If a browser/corpus capability is unavailable during ordinary development, use the exact
  automatic skip. Do not use that skip as Gate 1b evidence.
- Existing Slice 1a tests remain green throughout; changes to shared helpers must preserve
  their public behavior or migrate them to named matrix cases in the same commit.
