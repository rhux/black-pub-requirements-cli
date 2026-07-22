# Phase A Characterization Matrix Design

**Date:** 2026-07-22
**Status:** Approved design; implementation plan follows after written-spec review.
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

The catalog lives under `tests/matrix/`:

```text
tests/matrix/
  model.py
  registry.py
  input_cases.py
  pdf_cases.py
  requirement_cases.py
  acquisition_cases.py
  artifact_cases.py
  interface_cases.py
  platform_cases.py
  scale_profile.py
```

Each `MatrixCase` has:

- a stable case ID such as `PDF-STRICT-002` or `ACQ-RETRY-003`;
- an independent behavior axis;
- `preserve`, `intentional-change`, or `new-acceptance` classification;
- evidence kind: corpus aggregate, current branch, public contract, or property boundary;
- a privacy-safe rationale;
- synthetic input specification;
- expected legacy observation;
- expected target observation and owning slice when different.

Registry audits fail on duplicate IDs, incomplete evidence, absent ownership, placeholder
text, privacy findings, an intentional change without both expectations, or an independent
axis with fewer than two focused cases. Finite sets are audited against explicit expected
members rather than inferred from the cases themselves.

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
MatrixCase
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
class-completion states. It does not invent correlations that aggregate evidence cannot
support. Other profiles derive deterministic proportional workloads.

## Behavioral domains

### Inputs

Cover CSV, XLSX, JSON, and text; every name/URL/type alias; BOM and normalized headers;
XLSX sheet selection and fallbacks; JSON list/wrapper/string/dictionary forms; comments and
name-URL text rows; whitespace; ordering; first-URL-wins dedup; both adult types; invalid
schemes; missing columns; empty/all-filtered inputs; and current eager optional imports.

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
already established in Slice 1a.

Every artifact is classified as private or shareable and lists whether upstream IDs, QR
tokens, names, or raw payload state are allowed. Current leaks use synthetic values and are
intentional-change tripwires. Both committed fixtures and generated artifacts pass the
privacy scanner.

### Interfaces, lifecycle, and platforms

Cover exact defaults and exits for both CLIs; UI-created acquisition settings; all local-web
routes and methods; missing/present/busy/error states; complete SSE framing, event schemas,
terminal cleanup, and disconnects; run sorting and corrupt summaries; safe run IDs; report
and email actions; static DOM/API/event compatibility; desktop loopback, free port,
readiness retry/timeout, browser/native modes; data-root precedence; spaces, Unicode, BOM,
newline and separator behavior; Windows and macOS platform expectations; markers,
source-copy, and copied-release startup.

Tests sandbox `ui.server` before collection and reset its environment, module cache,
settings, derived paths, operations, busy flags, and current download. A plain local pytest
run must not touch the user's application data directory or depend on test order.

## End-to-end flows

At minimum, two vertical flows cross the real legacy boundaries:

1. Generated PDF -> attendee CSV -> input loader -> fake acquisition -> inference ->
   artifacts -> UI read routes.
2. The same pipeline with one successful attendee and one terminally failed attendee,
   asserting truthful partial results, events, cleanup, and artifacts.

A separate local-browser flow uses Playwright only against local fakes to verify browser and
static-UI contracts without live service access.

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
- current synthetic leakage of upstream identity/QR fields into artifacts that the target
  classifies as shareable.

## Private-corpus execution

The focused and scale layers always run locally and in CI. When `raw_data/` exists, the same
pytest invocation automatically adds read-only private-corpus characterization. An explicit
`--corpus-dir` supports another location. CI skips the private cases because the corpus is
absent.

Private-corpus tests record a structural fingerprint before and after execution and fail if
anything changes. They emit only aggregates, schema field names, counts, and redacted
findings. The authentic lane validates the canonical payload split, number/flag/type
profiles, PDF page/decode aggregates, and the generator's structural fidelity.

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
- local browser: Playwright against local fakes only;
- authentic: automatic when private `raw_data/` exists;
- static quality: lint, format, types, privacy, registry audit, and scoped legacy branch
  coverage.

The gate is green only when every preserve and intentional-change case executes, every new
acceptance has a later owner, every independent axis has at least two cases, every critical
boundary/flow maps to case IDs, no scoped branch lacks either coverage or an explicit
reviewed justification, the private corpus remains unchanged, privacy findings are zero,
browser/default tests make no external requests, the variable and canonical scale profiles
pass, and baseline evidence is recorded without a premature portable timing threshold.

