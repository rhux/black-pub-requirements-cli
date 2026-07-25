# Phase B Design — Package Boundaries & Core

**Date:** 2026-07-24
**Status:** Authoritative for Phase B. Subordinate to
`docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`.
**Depends on:** Gate 1a GO, Gate 1b GO.
**Owns:** Contracts only. Task ordering, RED tests, and code belong to the Slice 2a and 2b
plans (D24).

## Why this document exists

The parent specification fixes *what* Phase B must be true of the system. It was written
before Slice 1b existed, so it could not name the behavior contract Slice 2 would actually
be measured against. Gate 1b produced that contract: a 478-case typed catalog with
hand-computed expected observations, an independent axis/boundary manifest, six surface
policies, per-area coverage floors, and a checked-in aggregate baseline.

That changes Phase B from "move the code and hope parity holds" into a mechanical
proposition: **the catalog is the oracle, and the restructure is correct exactly when both
the legacy and the package implementations satisfy it.** The contracts below make that
proposition enforceable.

## Scope

Phase B moves the flat modules into `src/scoutmb` behind hexagonal boundaries, decomposes
requirement inference, extracts the report template, introduces the ScoutingEvent gateway
and acquisition service, replaces `busy` flags with a run-state machine and job supervisor,
makes the local web app a factory, and ships clean distributions.

### Explicitly out of scope for Phase B

- **Structured logging, log rotation, redaction, and the support bundle.** D20 places these
  in Slice 4. Phase B keeps `print()` at the interface layer and leaves stdout and stderr
  byte-identical, which is what preserves `PRIV-EGRESS-006`, `PRIV-EGRESS-007`, and the CLI
  cases. Legacy printing is already almost entirely at the CLI edge: seven calls in
  `scout_schedule_cli` (six in `async_main`/`main`, one `pageerror` handler in
  `process_scout`), twelve in `pdf_to_scouts` all inside `main`, and none in `ui.server`.
- **Changing the `Note.`-grafting or empty-number inference behaviors.** Resolved as
  keep-as-is by the parent spec's open-questions section.
- **Everything the parent spec marks POSTPONED (vNext)**, including CSRF/CSP/auth,
  deadline budgets, the URL allowlist, auto-update discovery, and multi-file generations.

## Package layout and module responsibilities

```text
src/scoutmb/
  __init__.py  __main__.py  errors.py  config.py  network_policy.py             2a
  core/
    models.py           frozen record shapes: ScoutInput, ClassRecord,
                        RequirementRecord, ScoutResult                          2a
    identity.py         AttendeeId, RunIdentity, safe_slug, filename stems       2a
    output_schemas.py   versioned DTO <-> row serializers; operational and
                        shareable projections; pinned CSV field order            2a
    inference/          numbering, tree, status, missing                         2a
    run_state.py        versioned run-state machine                              2b
  ports/
    clock.py            Clock, Sleeper, Jitter                                   2a
    ids.py              IdFactory                                                2a
    storage.py                                                                   2a
    scoutevent.py  observability.py                                              2b
  features/
    ingest/             loaders and PDF orchestration                            2a
    reporting/          html, email, csv/json writers                            2a
    acquisition/        retry, dedup, breaker, checkpoints                       2b
  adapters/
    files/atomic.py     atomic single-file publication, CSV writing              2a
    pdf/                PyMuPDF and OpenCV behind a capability check             2a
    scoutevent/  telemetry/noop.py                                               2b
  interfaces/
    cli/pdf.py                                                                   2a
    cli/schedule.py  web/  desktop/                                              2b
  runtime/jobs.py       lifespan-owned job supervisor                            2b
  resources/templates/  report.{html,css,js}, email.html                         2a
```

`bootstrap/` stays outside the package and stdlib-only, per the parent spec.

This is Phase B's **end state**, not the project's. The parent spec's target layout also
lists `logging_setup.py`; that module arrives in Slice 4 with D20's diagnostics work and is
deliberately absent here.

### Module granularity

One module holds one responsibility, not one type. Python's module *is* its namespace, so
splitting cohesive types across files buys deep import paths or `__init__` re-export
indirection, and splitting mutually-referencing types invites circular imports at runtime.
`models.py` therefore holds all four record shapes — `ClassRecord`, `RequirementRecord`,
and `ScoutResult` reference each other — and holds no serialization logic, which lives in
`output_schemas.py`. `core/inference/` **is** split four ways because numbering, tree
construction, status calculation, and missing-requirement selection are four algorithms
with four reasons to change.

A module is too big when it has more than one reason to change, or when a subgroup acquires
its own dependencies. Roughly 300–500 lines is where to start looking for that seam. If
`output_schemas.py` later accumulates several schema versions, it splits by version
(`output_schemas/v1.py`), never by type.

`scoutmb/__init__.py` stays **empty**. No convenience re-exports: they add import cost on
every entry path, create circular-import hazards between `core` and `features`, and make
"where does this actually live" unanswerable from the import statement. Callers import from
the owning module.

The package ships `src/scoutmb/py.typed` (PEP 561) so its annotations are visible to
consumers and to mypy when it is installed rather than imported from the source tree. The
marker must be present in the built wheel, which the clean-environment install test checks.

### Nondeterminism ports

The parent spec requires nondeterminism injected **per collaborator, not as one bag**, and
its illustrative layout puts all of it in `ports/time.py`. Phase B splits it, because
`IdFactory` is not a time concern and a four-collaborator module contradicts the principle
it exists to implement:

```text
ports/clock.py      Clock (UTC wall time), Sleeper (monotonic delay), Jitter (seeded RNG)
ports/ids.py        IdFactory (UUIDv4)
```

`ports/clock.py` also avoids a module named `time` inside the package. Absolute imports
make `import time` unambiguous, so this is a readability choice rather than a correctness
one — but a reader scanning `ports/` should not have to think about it.

### Optional dependencies

Today every heavy dependency is imported at legacy module scope: `scout_schedule_cli`
imports `openpyxl` and `playwright.async_api`, and `pdf_to_scouts` imports `cv2`, `fitz`,
and `numpy`. The parent spec lists this as a structural defect, and the package layout
depends on fixing it — `features/ingest` cannot select between a CSV adapter and a PDF
adapter if importing the feature drags in OpenCV.

Contract:

- Importing `scoutmb`, anything under `core/`, `ports/`, or any `features/` module pulls in
  **no** optional dependency. Only the adapter that needs one imports it, at call time or
  behind a module-level guard inside that adapter.
- A missing optional dependency produces a **typed capability error** carrying an
  actionable message (which extra to install), never a bare `ImportError` traceback.
- Enforced by a test that imports the core surface in a subprocess with the optional
  distributions absent from the environment, and asserts on `sys.modules` afterward rather
  than on the absence of an exception.

### Error model

`errors.py` defines a `ScoutmbError` hierarchy replacing the broad exception handling in
adapter paths. Changing exception *types* is free; changing what a user sees is not.

The catalog pins the error **envelope**, and it must survive unchanged: `errors.csv`'s
header is `['scout_name', 'attendee_id', 'error']` (`ART-SCHEMA-004`), the web layer's
failure body carries `error_message` (`UI-ROUTE-025`, `UI-ROUTE-027`), and in both the
underlying message text is **passed through verbatim** rather than reformatted. So an
exception type may change, gain structure, or move modules, but the string that reaches
`ScoutResult.errors` and `error_message` is the same string it is today. Wrapping that adds
a prefix, a class name, or a traceback fragment is a behavior change and needs its own
`intentional-change` row.

### Configuration

Frozen config dataclasses replace `argparse.Namespace` threading (D6). Two behaviors are
load-bearing and easy to lose:

- **CLI defaults are pinned** by the `CLI-SCHED-*` and PDF-CLI cases. The dataclass defaults
  and the argparse defaults must be the same values, defined once, so they cannot drift.
- `ui.server` hand-builds a `Namespace` that **omits** `email_report`, and `async_main`
  compensates with `getattr(args, "email_report", False)`. Replacing this with an explicit
  dataclass default of `False` preserves behavior — but the `getattr` and the missing field
  must be removed **together**. Deleting the defensive `getattr` while the web caller still
  omits the field turns a working default into an `AttributeError`.

### The 2a / 2b seam

**A boundary belongs to 2b if and only if it touches Playwright or FastAPI.** Everything
else is 2a. This splits the two CLI entry points — `pdf_to_scouts.main` is pure ingest and
moves in 2a, while `scout_schedule_cli.main` reaches `async_main` and therefore waits for
2b. The rule's purpose is that Slice 2a has no network and no server surface at all, which
is what makes Gate 2a cheap to trust.

### Console scripts

```text
troop349          = scoutmb.interfaces.desktop:main
troop349-pdf      = scoutmb.interfaces.cli.pdf:main
troop349-schedule = scoutmb.interfaces.cli.schedule:main
```

The two stage scripts mirror the two flat scripts **argument for argument**: same options,
same defaults, same exit codes, same stdout. Only the program name differs. This is a
contract, not a convenience — it is what lets the `CLI-SCHED-*` and PDF-CLI cases be
re-pointed at retirement without editing a single expected value. A `troop349 <subcommand>`
dispatcher is rejected for the same reason: it would change the argv prefix every one of
those cases is pinned to.

`pyproject.toml` currently declares `troop349 = "scoutmb.cli.app:main"`, which names a
module that has never existed; the console script is broken today and Slice 2 fixes it.

## The oracle invariant

This is the load-bearing rule of Phase B.

> **A move may add or re-point a runner. It may never edit a case's expected observation.**

`tests/matrix/cases/*.py` is data-only and holds no assertion logic, so any diff touching
`expected_by_context` is visible in review immediately. Changing an expected value requires
reclassifying the case to `intentional-change` with a named `target_owner` and a written
`target_observation` — which is what makes a behavior change a reviewed decision instead of
a refactor artifact.

The invariant admits exactly **six sanctioned exceptions**, listed below. Each was written
into the catalog by Slice 1b with `target_owner="Slice 2"` and a pre-written
`target_observation`, so updating its expected value is assigned work rather than oracle
tampering. No seventh may be added without amending this document.

Nine further rows are also owned by Slice 2 but are **not** exceptions to this invariant:
they are `new-acceptance` cases sitting at `contexts=()`, so they execute nothing today and
Slice 2 only adds to them. Fifteen rows in total carry `target_owner="Slice 2"`, and that
set is the authoritative list of behavior Phase B is permitted to change.

### The six intentional-change rows

| Case | Slice | Change |
| --- | --- | --- |
| `ART-NAME-007` | 2a | Output-root resolution rejects, or explicitly confirms, a symlinked `--output` directory before publishing any file, instead of silently following it. |
| `ACQ-HASREQ-002` | 2b | Skip the requirement request entirely when `HAS_REQ='0'`, instead of issuing it and relying on the response to be empty. |
| `ACQ-REQ-004` | 2b | Validate requirement rows against a schema; flag or reject rows missing required fields instead of coercing them to blank strings and false flags. |
| `UI-IMPORT-001` | 2b | `create_app(settings)` factory; importing the module performs no filesystem I/O at all. |
| `UI-ROUTE-023` | 2b | `open_emails_folder` dispatches on `sys.platform` so the route succeeds identically on Windows, macOS, and Linux. |
| `UI-ROUTE-030` | 2b | `open_report` rejects any `html_report` value that is not a bare filename resolving inside `RUNS_DIR/<run_id>`, instead of splicing the persisted string into an opened URL. |

### The nine new-acceptance rows

All are Slice 2b, and all currently sit at `contexts=()` so they do not execute. Slice 2b
gives each one contexts and a runner; this is additive and does not touch existing data.

- `ACQ-BREAKER-001/002/003` — consecutive-failure breaker: stays closed below threshold,
  opens at threshold, resets after a success.
- `ACQ-RESUME-001/002/003/004` — checkpoint created on a fresh run, completed scouts not
  repeated on resume, the attendee-to-output-UUID map survives a process restart, and a
  corrupt or version-mismatched checkpoint fails closed.
- `NET-WIRE-001/002` — the HTTP gateway and the Playwright navigation gateway each call
  `assert_egress_allowed(host)` before issuing a request or navigating.

### Request-count restatement

`ACQ-HASREQ-002` changes when a requirement request is issued, so the performance
assertion must be restated as **one requirement request per deduplicated class whose
`HAS_REQ` is truthy**, rather than one per deduplicated class.

The canonical corpus has `HAS_REQUIREMENTS_MARGINAL = {"1": 103}` — no class carries
`HAS_REQ='0'` — so the checked-in baseline of 22 schedule requests, 98 requirement
requests, and 120 total is **unchanged** by this. The restatement matters anyway: left as
"one per deduplicated class," the assertion becomes accidentally true on this corpus and
stops testing the new behavior at all. A synthetic case with `HAS_REQ='0'` must exercise
the skip directly.

## Parity contract

For each domain in `tests/matrix/cases/`, Slice 2 adds one file under `tests/parity/`
holding a second runner over the identical case tuple:

```text
tests/characterization/test_requirement_matrix.py
    LegacyRequirementRunner  -> scout_schedule_cli          (frozen)
tests/parity/test_requirement_package.py
    PackageRequirementRunner -> scoutmb.core.inference       (new)
```

Both import the same cases and assert against the same `expected_by_context`. **Neither
runner is the other's oracle** — the hand-computed data is, and both are measured against
it independently. The `Runner[InputT, ObservationT]` protocol in `tests/matrix/model.py`
already types this shape, so the catalog needs no change to support it.

**Lane accounting rule:** while a domain's legacy module still exists, an execution key is
satisfied only when **both** runners pass it. A domain cannot be declared moved on the
strength of one green side.

**Lane coverage.** The rule applies per lane, not only to the default lane. The eleven
browser-lane and three authentic-lane cases get package runners on the same terms, and the
authentic lane matters most for the 2a domains — it is the only place the package's ingest
and PDF adapters meet real upstream shapes. Gate 2a runs the authentic lane with
`--require-corpus`; a skip is not a pass.

**Property tests.** The parent spec's testing strategy puts Hypothesis on parsers and state
transitions, and Phase B is where both appear. Two are required rather than optional:
round-tripping the DTO boundary (`to_row(from_mapping(x))` reproduces `x` for every
generated payload shape, including the 26 requirement-number shapes), and totality of the
run-state transition table in 2b (every state/event pair either has a defined transition or
fails closed — no pair falls through). These complement the catalog; they do not substitute
for any case in it.

### Compatibility shims

While a flat module survives, it is a compatibility module in the parent spec's sense: it
delegates into `scoutmb` and holds no business logic. Two forms are permitted, chosen by
whether the signature changes:

- **Signature unchanged** — the shim is a re-export. The existing characterization test
  needs no edit at all.
- **Signature changes** — the shim body is `parse -> core -> serialize`. Both halves of
  that sandwich are real code the package needs regardless: the parser is the boundary
  parser, and the serializer is the versioned output schema. Only the wiring function is
  temporary.

There is **no deprecation surface**: no `FutureWarning`, no compatibility policy, no
migration window. One installation exists, owned by one person, published nowhere. The
flat modules and their characterization files retire together in explicit end-of-2b tasks
once the package runner covers their cases.

Breaking the installed application mid-slice is acceptable by owner decision — no release
occurs until Phase B completes. The D2 launcher bridge therefore lands with the entrypoint
and packaging work at the end of 2b, built once, rather than as a temporary bridge erected
early and reworked later. One integration check does move earlier: a clean-environment
wheel install runs in 2a as soon as `resources/` exists, because package data omitted from
a build is invisible until something installs it somewhere else.

## Test-asset migration

Gate 1b's enforcement machinery is pinned to legacy file paths, legacy symbol names, and
legacy line numbers. Moving code invalidates all of it at once, and a silently-degraded
gate is worse than no gate. Four invariants govern the migration.

1. **Boundaries are dual-named, not rewritten.** Each of the 61 `BoundarySpec` entries
   gains a package-side qualified name alongside its legacy one. Both remain declared until
   the legacy module retires, at which point the legacy name is removed with it.

2. **Coverage areas are added, not edited.** The five existing areas stay keyed to their
   legacy files. New package areas are added at D10's floors — new core and
   payload-validation code at ≥95% branch, new feature and file-adapter code at ≥90% —
   which are higher than the legacy floors they eventually replace.

3. **Branch exclusions move with their code.** All 16 `BranchExclusion` entries carry both
   `file` and `line`, and a stale exclusion is defined to fail. They therefore migrate in
   the same task that moves the code they annotate, never in a batch afterward.

4. **Coverage collection must actually reach the package.** `[tool.coverage.run] include`
   currently specifies `src/scoutmb/*.py`. Verified against coverage.py's own
   `globs_to_regex`: `*` does not cross a path separator, so `src/scoutmb/core/inference/
   tree.py` is not matched. Left uncorrected, every subpackage Phase B creates reports zero
   coverage while the gate stays green. The pattern becomes `src/scoutmb/**/*.py`.

**Shimmed modules lose their coverage floor.** Once a legacy module is pure delegation, its
branch percentage is passed trivially by a few lines of imports and proves nothing. Its
coverage area is then replaced by a structural assertion. Coverage measures the package;
the shim gets a shape check.

"Contains no business logic" is checked against the module's AST, and means every
top-level statement is one of: an import; a module-level assignment binding an imported
name or a literal; a class or function definition whose body contains no branching, no
loop, no comprehension, and no `try` — only a call forwarding to an imported name, with
argument adaptation and a return. Anything else — a conditional, an arithmetic expression,
a string built from parts — is business logic and fails the check. This is deliberately
strict: the point is that a shim cannot quietly re-acquire behavior that the package is
supposed to own.

`tests/harnesses/legacy.py` exists to drive the legacy modules and retires with them, in
the same task that removes the last module it loads.

**Catalog growth is explicit.** `tests/baselines/phase_a.json` carries a `case_ids` array
of all 478 cases, so every case Slice 2 adds requires a reviewed baseline bump. This is
intended friction: it makes catalog growth visible in review rather than incidental.

**Lint and type coverage arrive automatically.** `[tool.ruff] extend-exclude` lists the four
flat scripts and mypy's `files` omits them, so code becomes linted and type-checked the
moment it moves into `src/`. No separate enablement step exists, and the exclusion list
shrinks as the shims retire.

## Artifact surface tiering

The parent spec forbids upstream identity in shareable artifacts and separately pins CSV
field order through `__dataclass_fields__`. Those collide, because `attendee_id` is field
two of both `ClassRecord` and `RequirementRecord`. The tiering resolves it by fixing which
artifacts are shareable rather than by weakening either rule.

| Artifact | Class | Carries |
| --- | --- | --- |
| `scouts.json` | operational-private | `attendee_id`, `qr_url` |
| `classes.csv`, `requirements.csv`, `errors.csv` | operational-private | `attendee_id` |
| `raw/` | adapter-private | full upstream payloads |
| `emails/missing_requirements.csv` | operational-private | `attendee_id` |
| `report.html` | audience-shareable | neither `attendee_id` nor `qr_url` |
| `emails/<slug>.txt`, `emails/<slug>.html` | audience-shareable | neither `attendee_id` nor `qr_url` |

The `emails/` directory holds two different kinds of file and they tier differently.
`missing_requirements.csv` is a **mail-merge worksheet** — it carries `subject`,
`body_text`, and `body_html` columns for the owner to send from, and it is not itself sent
to anyone. The per-scout `.txt` and `.html` files are the bodies that actually reach a
recipient.

### Consistency with the frozen catalog

This tiering was chosen so that it does not require editing a single `preserve` case:

- `ART-SCHEMA-001` pins `scouts.json` as containing `qr_url` and `attendee_id`;
  `ART-SCHEMA-002/003` pin the two record CSV headers as
  `__dataclass_fields__` in declaration order; `ART-SCHEMA-004` pins
  `errors.csv` as `['scout_name', 'attendee_id', 'error']`; `ART-SCHEMA-007` pins
  `emails/missing_requirements.csv` as
  `['scout_name', 'attendee_id', 'status', 'merit_badge_count',
  'missing_requirement_count', 'subject', 'body_text', 'body_html']`. All five stay
  operational-private and are untouched.
- `ART-SCHEMA-006` pins only the **top-level key set** of the embedded report data
  (`generated_at_local`, `generated_at_iso`, `run_id`, `scouts`, `classes`,
  `requirements`, `errors`) and asserts nothing about the fields inside those collections.
  No `ART-HTML-*` or `REQ-*` html-consumer case pins `attendee_id` either. The shareable
  projection therefore changes only inner rows and breaks no pinned expectation.
- The per-scout email bodies already contain no `attendee_id` and no `qr_url`, and their
  filenames are display-slug plus per-run UUID. Declaring them audience-shareable is a
  **policy declaration plus a new enforcing test**, not a code change.

Net effect: the only production change the tiering requires is the `report.html`
projection, where `attendee_id` currently reaches the embed four ways — `scouts[]`,
`classes[]` and `requirements[]` via `asdict`, and the `errors[]` list built explicitly.

`output_schemas.py` therefore exposes two projections of the same records. The operational
projection is today's shape and preserves CSV field order, so the D16 goldens are
unaffected. The shareable projection drops `attendee_id` and substitutes the per-run
UUIDv4. `write_html_report` embeds `asdict(ClassRecord)`, `asdict(RequirementRecord)`, and
an `errors` list built with `attendee_id` explicitly; all three move to the shareable
projection.

**Recorded consequence:** `scouts.json` retains `qr_url`, which is a live bearer credential
for a minor's record. The surface policy must state this rather than leave it implicit, and
Slice 3's data-root permissions and explicit-deletion work is what actually protects it.
Obscurity is not the control.

## Inference decomposition contract

`annotate_requirement_statuses` decomposes into `core/inference/{numbering, tree, status,
missing}.py`, dataclasses in and dataclasses out. Group identity, path derivation, the
header-stack fallback, choice thresholds, and the exact status strings and reason sentences
are preserved as characterized.

`build_missing_requirements` currently keys ancestor bookkeeping on `id(item)`, which cannot
survive frozen dataclasses. The re-expression is over explicit node indices from the tree —
**and a naive index substitution is not equivalent.** The legacy walk resolves a parent by
looking up `(attendee, class, parent_requirement_number)` in a dict comprehension where the
**last matching row wins**, while the tree's `children[]` links are positional. When one
`(scout, class)` group contains two rows sharing a requirement number, those two resolve to
different objects.

No `REQ-*` case covers duplicate requirement numbers within a group. Slice 2a therefore
adds that case and confirms the current behavior **before** re-expressing the walk. The
re-expression must reproduce whichever resolution the legacy code exhibits; if that
behavior is judged wrong, changing it is a separate `intentional-change` row with its own
owner, not part of the move.

## Gates

### Gate 2a — Core & Content

- Both runners green for every execution key in the input, PDF, requirement, and artifact
  domains — legacy runners against the shims, package runners against `scoutmb`.
- Catalog diff review: no `expected_by_context` edited except `ART-NAME-007`; every added
  case accompanied by a reviewed `phase_a.json` bump.
- Architecture tests: `core/` and `ports/` import no adapter, interface, bootstrap,
  Playwright, OpenCV, or PDF library; no first-party `sys.path` mutation anywhere; no data
  path derived from `__file__`.
- Coverage: package areas meet their D10 floors; the `include` pattern reaches every
  package module and the existing missing-file check confirms each declared area file
  appears in the report; no legacy area regresses below its baseline unless it has been
  replaced by the no-business-logic assertion.
- A clean-environment wheel install succeeds with `resources/templates/` and `py.typed`
  present, and `troop349-pdf` runs stage 1 from a directory outside the repository.
- Importing the core surface in a subprocess without the optional distributions installed
  loads no optional dependency, and requesting a missing capability raises a typed error
  with an actionable message.
- The shareable projection contains no `attendee_id` and no `qr_url`; the per-scout email
  bodies are covered by the same assertion.
- The authentic lane runs with `--require-corpus` against both runners for the 2a domains.
- Default lane remains offline; `egress-denied` green.
- **NO-GO:** restore the moved symbol's original body to the flat module, delete the
  package module and its parity file, return the defect to its task, rerun the gate. There
  is no adapter-selection switch during 2a — a shim either delegates or it does not, so
  rollback is a revert, not a configuration change.

### Gate 2 — Identity, output, and runtime

Everything in Gate 2a, plus:

- Both runners green across the whole catalog; all fifteen owned rows landed and reviewed.
- Same-named attendees stay separate through acquisition, inference, reports, and resume;
  a missing upstream ID fails closed.
- Single-file publication failures preserve prior bytes.
- Illegal run-state transitions fail closed; cancellation owns and closes every child;
  loopback bind holds; importing the web module performs no I/O.
- Flat modules retired, `source_sync` ships the package, and a copied release root starts
  with no repository present.
- **NO-GO:** restore the relevant compatibility adapter as the composed default, return the
  defect to its task, rerun the gate.

## Traceability

| Parent-spec decision | Phase B treatment |
| --- | --- |
| D2 launcher bridge | Built once at the end of 2b; no early temporary bridge |
| D3, D25 identity | Carried into `core/identity.py` unchanged; parity only |
| D6 typed config | Frozen config dataclasses replace `Namespace`; `ui.server`'s hand-built `Namespace` and the `getattr` defenses in `async_main` go with it (2b) |
| D8 behavior matrix | The catalog is the oracle; the oracle invariant protects it |
| D10 coverage | Package areas added at ≥95% / ≥90%; shimmed modules get shape checks |
| D11, D16 artifacts | Atomic single-file writes reused; two projections; CSV order pinned |
| D13 parity | Dual runners, both-green lane accounting, legacy retired only after |
| D14 privacy | Resolved by the surface tiering |
| D19 hexagonal | Layout above; enforced by architecture tests |
| D20 diagnostics | Out of scope for Phase B; stays in Slice 4 |
| D22 gateway | Port, drift, breaker, checkpoints in 2b; budgets and allowlist stay vNext |
| D24 spec/plan split | This document holds contracts; ordering lives in the plans |
| D27 offline | `NET-WIRE-001/002` wire `assert_egress_allowed` into both gateways |
| D30 web boundary | Structural only: factory, `JobRegistry`, loopback, four UI defects |
| D32 determinism | `ports/clock.py` (`Clock`, `Sleeper`, `Jitter`) and `ports/ids.py` (`IdFactory`) — a deliberate split of the parent spec's single `ports/time.py` |
| D33 run state | Versioned machine in `core/run_state.py` (2b) |

## Open questions

None. Every Phase B contract above is decided. Items the parent spec marks POSTPONED remain
deferred by decision, not by omission.
