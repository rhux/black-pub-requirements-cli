# Phase A Characterization Matrix Design

**Date:** 2026-07-22
**Status:** Approved and hardened after written-spec review; implementation is owned by the
Slice 1b plan.
**Parent specification:** `2026-07-21-scoutmb-refactor-design.md`
**Target plan:** `../plans/2026-07-22-slice-1b-full-phase-a-characterization.md`

## Purpose

Slice 1b creates the implementation-neutral behavior contract that protects the Slice 2
package move and remains extensible for later features. It is not a collection of example
tests tied to the current flat modules. It is a central catalog of named cases, synthetic
builders, normalized observations, classifications, and evidence. Slice 1b runs the catalog
against the legacy application; Slice 2 runs the same cases against the new adapters and
services.

The matrix must be broad enough to expose an accidental behavior change at every boundary
that Slice 2 moves, while avoiding an unmaintainable Cartesian product. Every independent
behavior receives at least two focused synthetic cases. Finite observed sets receive full
coverage, high-risk failures receive success/recovery/terminal cases, and interactions are
added where one axis changes another's outcome.

## Authoritative corpus interpretation

`tools/verify_corpus.py` currently labels every dictionary in every raw payload's `data`
array as a requirement. That is semantically incorrect. The 103 rows with
`(COMPLETED_REQ_FLAG, COMPLETED_CLASS_FLAG) == (None, None)` have the schedule-class schema,
not the requirement schema.

Slice 1b corrects the verification oracle before using it for matrix evidence. The verifier
reports `data_rows`, `schedule_rows`, `requirement_rows`, and `unrecognized_rows`; classifies
rows with named schedule/requirement schema predicates rather than the flag pair alone; and
fails the required authentic lane on an ambiguous or unrecognized row. Its tests contain a
mixed schedule/requirement payload plus malformed and non-dictionary rows. This resolves two
different facts explicitly: the original 4,858-vs-4,961 discrepancy was a documentation
miscount, while the helper's current `requirements` label is unsuitable for a characterization
oracle and must be corrected in Slice 1b.

One canonical private snapshot contains:

| Species | Payloads | Rows |
| --- | ---: | ---: |
| Schedule | 22 | 103 raw class rows |
| Requirements | 98 | 4,858 requirement rows |
| Total | 120 | 4,961 `data` rows |

The 103 schedule rows deduplicate to 98 classes. The requirement rows have one stable
ten-field schema, four observed completion-flag combinations, three requirement types, and
26 distinct normalized number shapes. There are 31 requirement rows with an empty display
number and 125 `Note.`-shape rows per canonical snapshot.

The three dated private runs have equivalent raw-payload multisets. They are repeated
snapshots of one logical corpus, not three independent populations. Matrix counts use one
canonical snapshot; they do not multiply observations across the three copies.

Private output artifacts span different code revisions. They may inform schema discovery,
but they are not current-code goldens. The checked-out legacy code is authoritative for
observable output behavior; the raw payloads and source PDF are evidence for realistic
input shapes.

No private filename, name, attendee ID, QR token, description, payload, PDF, content hash,
or copied artifact is committed.

## Goals

- A central, typed, implementation-neutral matrix that later features can extend.
- Complete legacy observations for every boundary Slice 2 moves.
- Executable tripwires for known behaviors that Slice 2 intentionally changes.
- At least two cases for every independent behavior, with stronger treatment for failures.
- Deterministic synthetic inputs grounded in private-corpus aggregates without copying data.
- A variable-attendee scale generator plus the canonical 22-attendee topology.
- Normalized legacy-to-new parity that does not hide format or privacy contracts.
- Default local execution, a local-only browser lane, and automatic private-corpus
  augmentation when `raw_data/` exists.
- Explicit Windows 11 x64 and macOS 14+ arm64 seams within Slice 1b's scope.

## Non-goals

- No production fixes in Slice 1b. Unexpected behavior is recorded or separately approved.
- No live `scoutingevent.com` access.
- No committed private corpus or derived private fixtures.
- No full Cartesian product of unrelated axes.
- No full installer/provisioning, WebView2, browser-installation, download, lock, native
  installer, or capability matrix. Those remain in Slices 3 and 4.
- No portable wall-clock regression threshold before a trustworthy baseline exists.
- No full-output snapshot as a substitute for explicit behavior assertions.

## Central matrix architecture

The catalog is data-only and lives under `tests/matrix/`; builders, strict fakes, and harnesses
remain separate so the catalog never imports legacy modules or optional capabilities:

```text
tests/matrix/
  model.py
  axes.py
  policies.py
  registry.py
  cases/
    input_cases.py
    pdf_cases.py
    requirement_cases.py
    acquisition_cases.py
    artifact_cases.py
    interface_cases.py
    platform_cases.py
  scale_profile.py
tests/factories/
  inputs.py
  payloads.py
  pdf_builder.py
  scale.py
tests/fakes/
  acquisition.py
  browser.py
  clock.py
tests/harnesses/
  legacy.py
  browser.py
  corpus.py
  subprocess.py
```

`model.py` defines small enums (`Classification`, `EvidenceKind`, `Domain`, and
`SurfaceClass`), a frozen/slotted `CaseMetadata`, domain-specific frozen/slotted case and
observation dataclasses, and generic runner protocols. There is no universal
`MatrixCase[Any, Any]`, YAML schema, reflection-based discovery, or assertion callback stored
inside case data. Production code never imports the matrix. Each domain case has:

- a stable case ID such as `PDF-STRICT-002` or `ACQ-RETRY-003`;
- an independent behavior axis;
- `preserve`, `intentional-change`, or `new-acceptance` classification;
- evidence kind: corpus aggregate, current branch, public contract, or property boundary;
- a privacy-safe rationale;
- synthetic input specification;
- expected legacy observation;
- expected target observation and owning slice when different.

`axes.py` is an independent completeness manifest. Each `AxisSpec` declares its stable ID,
domain, owning public symbols/flow, required equivalence-class or finite-set members, minimum
focused-case count, required material interactions, evidence source, and phase owner. Cases
reference those axes; cases do not define which axes exist. `policies.py` holds the egress
surface inventory and field policy described below.

Registry audits fail on duplicate IDs, unknown axes, missing required members or interactions,
incomplete evidence, absent ownership, placeholder text, policy violations, an intentional
change without both expectations, or an independent axis with fewer than two focused cases.
Finite sets are audited against the `AxisSpec` members rather than inferred from the cases
themselves. A separate boundary inventory maps every scoped public legacy boundary and
critical flow to case IDs; branch exclusions require a stable ID and reviewed rationale.

### Classification semantics

- **Preserve:** the legacy and target observations are the same.
- **Intentional change:** Slice 1b asserts the current legacy behavior as a temporary
  executable tripwire and records the different target. The owning later slice replaces or
  supplements the legacy assertion deliberately.
- **New acceptance:** no meaningful legacy implementation exists. Slice 1b validates the
  case metadata and ownership but does not pretend the legacy code passes the future
  contract.

## Execution model

```text
DomainCase[InputT, ObservationT]
  -> synthetic builder
  -> legacy harness
  -> observed outcome
  -> central normalizer
  -> expected legacy outcome
```

An observed outcome may contain a value, exception, generated files, calls, progress/SSE
events, resource state, and cleanup state. Exception text is exact only when it is a
user-visible contract; internal errors compare normalized type, status, and bounded redacted
details.

Slice 2 adds a new-package harness beside the legacy harness. It consumes the same cases and
compares target or parity observations. Tests must not duplicate the matrix in a second set
of hand-authored expectations.

Harnesses may replace only true external boundaries: browser/service I/O, clocks/sleepers,
randomness, process launch, and filesystem fault injection. They do not monkeypatch the
parser, inference function, writer, route, or other behavior under test. Strict fakes honor
and validate attendee IDs, class IDs, request bodies, ordering, retry sequences, delays, and
cleanup. They reject an unexpected call rather than returning a permissive default, expose a
complete call log, and have focused self-tests proving that wrong parameters, order, or call
counts fail.

The normalizer explicitly handles UUIDs, timestamps and time zones, random attendee delays,
run IDs, filesystem roots and separators, platform newlines, and other nondeterministic
fields. Separate format assertions still verify that each normalized field had the required
UUID, timestamp, path, or ordering shape before normalization.

## Coverage rule

- At least two focused cases per independent behavior: a normal representative and a
  boundary or alternate representative.
- At least three cases for high-risk failures: immediate success, recoverable failure, and
  terminal failure.
- All 26 number shapes are exercised once through path parsing and once through complete
  tree/inference behavior.
- All four observed requirement-flag combinations are exercised in leaf and parent/consumer
  contexts.
- All three requirement types and both observed class-completion states receive full
  coverage.
- Property tests cover open-ended parsers and bounded variable attendee counts.
- Pairwise interaction cases are added only when one axis materially changes another.
- Critical public legacy boundaries and execution flows map to stable case IDs. Branch
  coverage is a completeness backstop, not the definition of correctness.
- Every executable lane audits selected and executed case IDs; a marker expression, missing
  optional dependency, or empty registry may not produce a green no-op.

## Synthetic data layers

### Focused behavior catalog

Small deterministic builders create inputs, payloads, PDFs, records, filesystem layouts,
browser responses, SSE streams, and platform contexts at test time. No generated binary is
committed. Structural goldens are limited to contracts where exact shape matters: CSV
headers/order, JSON key sets, sanitized report data, and bounded HTML structure.

### Variable and production-scale profiles

The generator supports:

- zero attendees for empty-batch behavior;
- one attendee for the minimum valid flow;
- two same-named attendees with distinct IDs for identity isolation;
- several small seeded attendee counts for grouping and ordering variation;
- the canonical 22-attendee profile;
- a larger profile, initially 50 attendees, for growth behavior;
- bounded property-generated attendee counts.

Only the canonical profile reproduces the safe production topology: 103 raw class rows,
five duplicate-class rows, 98 deduplicated classes and requirement payloads, and 4,858
requirements. It reproduces exact safe marginal counts for number shapes, flags, types, and
class-completion states. Pairing those independent marginal assignments onto the same
synthetic rows is **intentionally synthetic**: it is deterministic test construction, not an
assertion about production correlations. Tests using this profile may assert each marginal,
topology, request count, ordering, and algorithmic behavior, but may not infer or lock a
cross-axis relationship from the generated pairings. Any correlation-sensitive behavior is
covered by a focused interaction case supported by code semantics or separately approved,
privacy-safe joint evidence.

The generator has a schema/profile version, stable seed inputs, and deterministic allocation
rules. Smaller profiles derive totals using a documented largest-remainder allocation and
stable tie-break order; they assert totals and invariants rather than pretending to preserve
every canonical marginal at tiny sizes. Property tests use bounded strategies and explicit
example limits; deterministic named profiles remain available for reproduction without
turning one random seed into the only tested population.

## Behavioral domains

### Inputs

Cover CSV, XLSX, JSON, and text; every name/URL/type alias; BOM and normalized headers;
XLSX sheet selection and fallbacks; JSON list/wrapper/string/dictionary forms; comments and
name-URL text rows; whitespace; ordering; first-URL-wins dedup; both adult types; invalid
schemes; missing columns; empty/all-filtered inputs; and current eager optional imports.
Optional-dependency profiles execute in clean subprocesses (`base`, `pdf`, `acquisition`, and
`all`) so `sys.modules` and test order cannot hide an eager import. CSV/XLSX cases include
formula/control-prefix values (`=`, `+`, `-`, `@`, tab, and carriage return) as synthetic
current-behavior tripwires for every outward spreadsheet field.

### PDF and PDF CLI

Cover file/directory/glob/recursive discovery, overlap, sorting, path dedup, non-PDF and
missing inputs, embedded-image and rendered-page QR paths, QR preference, multipage order,
case normalization, every missing-field combination, blank and corrupt pages, debug images,
the exact attendee/error schemas, filters, duplicate handling, strict exits, invalid DPI,
stale error-file behavior, and quiet output. Quiet mode intentionally prints the final path;
that matches its help contract and is not a defect.

### ScoutingEvent acquisition and browser

Cover schedule-response recognition, attendee-ID extraction, payload status/data profiles,
zero/multiple/missing-ID classes, every dedup branch, field mapping, requirement status and
schema variants, raw artifacts, immediate/transient/terminal retries and exact delays,
request delay, resource cleanup, dead-asset routing, local browser interception, and browser
subprocess egress denial. A class with `HAS_REQ="0"` currently receives a requirement request
when it has a class ID; that is an intentional-change tripwire.

### Inference, consumers, artifacts, and privacy

Cover number paths and trees, flags, types, empty and label rows, parent/child ancestry,
malformed numbering, choice verbs and threshold boundaries, non-mutation, exclusions,
identity isolation, deterministic ordering, HTML and email consumers independently,
prerequisite rendering, exact CSV/JSON/summary/report/email schemas, empty/error variants,
HTML/script escaping, safe names, conditional email files, and atomic publication behavior
already established in Slice 1a. Path safety includes traversal, absolute paths, symlinks,
case-only collisions, and platform filename edge cases.

Privacy is enforced through an explicit egress inventory, not a generic "scan all files"
claim. Synthetic sentinels represent names, upstream IDs, QR tokens, session material,
payload fragments, and filesystem paths:

| Surface class | Concrete surfaces | Target allowance |
| --- | --- | --- |
| Input-private | source/uploaded PDFs; attendee CSV/XLSX/JSON/text | Names and QR URLs are allowed input data; never committed or copied outside the selected data root. |
| Adapter-private | `raw/*.json`; resumable private checkpoint | Only these surfaces may retain upstream ID/session/payload state when required. Filenames use output UUIDs, and the surfaces are never served, shared, logged, or included in support bundles. |
| Operational-private | `scouts.json` and future internal run state | Names, requirement data, and output UUID are allowed; upstream ID, QR/session material, and raw payload state are forbidden in the target. |
| Audience-shareable | `classes.csv`, `requirements.csv`, `errors.csv`, `summary.json`, report HTML/data, email CSV/text/HTML | Display names and necessary schedule/requirement content are allowed; identity uses output UUID where needed; upstream ID, QR/session material, and raw payload state are forbidden. Spreadsheet fields also enforce the formula/control-prefix policy. |
| Local user interface | CLI stdout/stderr, API responses/errors, SSE/progress events, report/email actions | Only contractually necessary display names, counts, statuses, safe run IDs, and user-facing paths are allowed; upstream ID, QR/session material, payload fragments, and unredacted internal exceptions are forbidden in the target. |
| Diagnostics | structured logs and support bundles | No names, upstream IDs, QR/session material, raw payloads, or absolute user paths. Bounded redacted reason codes and counts only. |

Every surface receives stable policy and case IDs, a current observation, target observation,
and owning slice. Current violations use synthetic sentinels and are intentional-change
tripwires. The privacy scanner always scans committed fixture sources and all generated
operational/shareable/interface/diagnostic surfaces. Adapter-private outputs are instead
checked against their narrow field allowlist, containment, filename, and no-copy rules; an
expected private token in the one authorized raw surface is not mislabeled as a scanner
failure.

### Interfaces, lifecycle, and platforms

Cover exact defaults and exits for both CLIs; UI-created acquisition settings; all local-web
routes and methods; missing/present/busy/error states; complete SSE framing, event schemas,
terminal cleanup, and disconnects; run sorting and corrupt summaries; safe run IDs; report
and email actions; static DOM/API/event compatibility; desktop loopback, free port,
readiness retry/timeout, browser/native modes; data-root precedence; spaces, Unicode, BOM,
newline and separator behavior; Windows and macOS platform expectations; markers,
source-copy, and copied-release startup.

Slice 1b's platform rows are explicitly simulated pure-contract tests. Windows cases cover
reserved device names, trailing dots/spaces, case-only filename collisions, backslash and
forward-slash inputs, drive/UNC/extended path forms, and traversal. macOS cases cover NFC/NFD
Unicode equivalence, case-only collisions, volume-root paths, spaces, and traversal. They do
not claim native filesystem or shell behavior from a monkeypatched `sys.platform`; native
Windows/macOS installer and filesystem acceptance remains in Slices 3 and 4.

Tests sandbox `ui.server` before collection and reset its environment, module cache,
settings, derived paths, operations, busy flags, and current download. A plain local pytest
run must not touch the user's application data directory or depend on test order.
Pre-collection environment setup uses a pytest startup hook rather than a fixture that runs
too late. Stateful tests reset globals before and after, and async cases fail on pending tasks,
leaked queues, unclosed browser contexts, or retained operations after success, exception,
terminal failure, and SSE disconnect.

## End-to-end flows

At minimum, two vertical flows cross the real legacy boundaries:

1. Generated PDF -> attendee CSV -> input loader -> fake acquisition -> inference ->
   artifacts -> UI read routes.
2. The same pipeline with one successful attendee and one terminally failed attendee,
   asserting truthful partial results, events, cleanup, and artifacts.

A separate local-browser flow uses Playwright only against local fakes to verify browser and
static-UI contracts without live service access.

The flows assert their preconditions and the exact boundaries executed: a generated PDF and
attendee CSV exist, the real legacy loader/inference/writers/routes run, the strict fake sees
the expected requests, every expected artifact exists with exact structure, and cleanup is
complete. They may not replace an in-process legacy function merely to make the flow easier.

## Required focused edge cases

The case catalog includes stable IDs for all of the following; none may remain prose-only:

- spreadsheet formula/control-prefix values in every CSV/XLSX output field;
- synthetic sensitive sentinels across filenames, file contents, stdout, stderr, API errors,
  SSE/progress events, exception messages, report data, email bodies, logs, and support data;
- exact stdout/stderr separation and exit codes for both CLIs, including quiet mode;
- clean-subprocess optional-dependency profiles with the wrong import target and module-cache
  false positives excluded;
- corpus absent, present, wrong layout, schema-unrecognized, unreadable, symlinked, and
  attempted-mutation states;
- Windows reserved names/trailing dots/spaces/drive/UNC/case collisions and macOS NFC/NFD,
  volume-root, and case-collision inputs within the simulated seam;
- traversal, absolute-path, symlink, case-only collision, and duplicate filename handling;
- async success, exception, terminal failure, and SSE disconnect with no pending task, queue,
  browser context, operation, busy flag, or partial-publication leak;
- strict-fake self-tests for wrong attendee/class IDs, wrong order, unexpected retries, ignored
  delays, extra calls, and unconsumed scripted responses;
- failure injection before render, during temp write, before/after replace, during cleanup,
  and between sibling artifact writers, with prior bytes and partial-publication state asserted;
- vertical-flow proof that the real loaders, inference, writers, and UI readers executed.

## Intentional-change tripwires

Slice 1b pins and assigns owners for at least these current behaviors:

- eager optional acquisition imports in the legacy schedule module;
- missing requirement fields coerced to empty/false instead of rejected;
- requirement requests sent for nonblank class IDs even when `HAS_REQ="0"`;
- UI tasks created without retained references;
- import-time UI data-directory creation;
- pause/resume without cancel;
- server-side `webbrowser.open` report launch;
- Windows-only `os.startfile` email-folder launch;
- unguarded persisted-JSON reads;
- spreadsheet formula/control prefixes written without target-safe handling;
- current synthetic leakage of upstream identity/QR fields through outward-facing files,
  stdout, and progress/SSE surfaces forbidden by the target surface policy.

## Private-corpus execution

The focused and scale layers always run locally and in CI. When `raw_data/` exists, the same
pytest invocation automatically adds read-only private-corpus characterization. An explicit
`--corpus-dir` supports another location. CI skips the private cases because the corpus is
absent.

Automatic augmentation may skip with one exact reason when no corpus exists. Gate 1b's
authentic command uses `--require-corpus`; absence, an empty selection, a wrong layout, or an
unrecognized schema is a failure. The browser gate similarly uses `--require-browser` rather
than `importorskip`.

Private-corpus tests reject symlinks and non-regular files, then compute an in-memory content
tree fingerprint over relative path, entry type, size, and SHA-256 before and after execution.
Timestamps and ownership metadata are excluded so a content-preserving metadata difference
does not masquerade as mutation. Raw hashes are never printed or committed. Tests open inputs
read-only, write only beneath pytest temporary roots, fail if the fingerprint changes, and
emit only aggregates, schema field names, counts, and redacted findings. The authentic lane
validates the canonical payload split, number/flag/type profiles, PDF page/decode aggregates,
and the generator's structural fidelity.

## Phase ownership

Slice 1b builds the observation harness, legacy assertions, normalization, evidence, and
baselines. Slice 2 consumes the same cases for package parity and implements its assigned
intentional changes. Slices 3 and 4 own full Windows/macOS installer, provisioning,
capability, browser-installation, download, lock, and native-runner matrices. Slice 4 owns
portable performance comparison thresholds.

## Implementation task boundaries

1. Corpus truth and matrix kernel.
2. Input-loader matrix.
3. PDF and PDF-CLI matrix.
4. Acquisition and browser matrix.
5. Inference, consumers, artifacts, and privacy.
6. Web, SSE, static UI, desktop, and scoped platforms.
7. Vertical flows, variable/scale profiles, baselines, and Gate 1b.

Each plan task must name concrete case IDs and assertions. It may not defer breadth through
phrases such as "representative rows", "optionally extend", or an unchecked completeness
list.

## Gate 1b

Gate 1b has four lanes:

- default synthetic: focused cases, variable attendees, scale, and vertical flows;
- local browser: Playwright against local fakes only, with `--require-browser`;
- authentic: automatic augmentation during ordinary local pytest when private `raw_data/`
  exists, plus a required Gate 1b command using `--require-corpus`;
- static quality: lint, format, types, privacy, registry audit, and scoped legacy branch
  coverage.

The gate is green only when every preserve and intentional-change case executes, every new
acceptance has a later owner, every independent axis has at least two cases, every critical
boundary/flow maps to case IDs, no scoped branch lacks either coverage or an explicit
reviewed justification, the private corpus remains unchanged, privacy findings are zero,
browser/default tests make no external requests, the variable and canonical scale profiles
pass, and baseline evidence is recorded without a premature portable timing threshold. Each
lane records selected and executed stable IDs and fails if its required set is empty,
deselected, skipped, duplicated, or incomplete. Scoped coverage measures the legacy flat
modules and scoped bootstrap code actually moved by Slice 2; `src/scoutmb` coverage alone
cannot satisfy Gate 1b.
