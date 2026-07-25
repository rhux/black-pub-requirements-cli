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

## Asserted contracts vs plan-verified mechanisms

Three review rounds against this document found the same class of defect each time: not a
wrong architecture, but a **wrong claim about how Python or this codebase actually behaves**.
`dataclasses.asdict` was said to convert tuples to lists (it preserves them). The launcher was
said to put `app_dir` on `sys.path` automatically (the embeddable distribution does not; a
bootstrap `.pth` patch does). A `__file__` dataflow check was specified that no AST walk can
decide. Each read as settled fact and each was false.

So this document distinguishes two kinds of statement, and the distinction is binding:

- **Contracts** — what must be true of the system: boundaries, schemas, invariants, gate
  conditions. These are decided here and a plan may not renegotiate them.
- **Mechanisms** — how a library, interpreter, or build tool behaves. These are marked
  *plan-verified*. The plan task that depends on one must **prove it by running code** before
  the work that relies on it, and if reality disagrees, the mechanism claim is amended here
  rather than worked around in the plan.

A mechanism assertion with no verifying task is a defect in this document, not a detail. The
plan-verified items are: `importlib.resources` behavior from the copied release root; the
`.pth` and `build.spec` release-root wiring; `asdict` normalization at the serializer; and the
tractability of the token and AST checks named under Dependency rules.

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
    attendee_source.py  the port ingest adapters implement                       2a
    artifact_sink.py    the port reporting adapters implement                    2a
    scoutevent.py  observability.py                                              2b
  features/
    ingest/             orchestration only: select a source, dedup, filter       2a
    reporting/          orchestration only: compose records, drive the sink      2a
    acquisition/        retry, dedup, breaker, checkpoints                       2b
  adapters/
    files/atomic.py     atomic single-file publication                           2a
    files/tabular.py    CSV + XLSX + JSON + text parsing and CSV writing         2a
    pdf/                PyMuPDF and OpenCV parsing behind a capability check     2a
    html/               template rendering                                       2a
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

### Layer roles

A feature **orchestrates**; it never parses and never writes. All parsing of external
formats (CSV, XLSX, JSON, line-delimited text, PDF) and all production of external formats
(CSV rows, HTML, email bodies) belongs to an adapter behind a port. `features/ingest`
selects a source, deduplicates, and applies the adult filter; it does not know that a CSV
has a header row. `features/reporting` composes records into a projection and hands it to a
sink; it does not know what an `<html>` tag is.

This is stricter than "loaders live in the ingest feature," which is how the legacy code is
shaped and how an earlier draft of this document described it. The distinction is what makes
the optional-dependency contract below achievable: if PDF parsing lives in a feature, then
importing that feature imports PyMuPDF, and a core-only install breaks.

Function-local imports do not escape this rule. The dependency check walks the AST, so an
adapter imported inside a factory method on a feature is still a `features -> adapters` edge.
Convenience constructors that need an adapter belong in `interfaces/<name>/composition.py`.

`ports/storage.py` is **not** created. There is one filesystem implementation and no second
one in prospect, so a storage port would be an abstraction with nothing behind it. The two
ports that do exist (`attendee_source`, `artifact_sink`) each have at least two real
implementations — file formats and PDF for the source, and the operational and shareable
projections for the sink. A port with one implementation and no test double is a smell, not
a boundary.

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

### Frozen records and collection types

`core/models.py` records become `@dataclass(frozen=True, slots=True)`. Two consequences to
decide now rather than mid-move:

- **Collections become tuples.** `ScoutResult` currently declares
  `field(default_factory=list)` for `classes`, `requirements`, and `errors`. A frozen record
  holding a mutable list is frozen in name only, so these become `tuple[...]` with
  `default_factory=tuple` — which breaks every `.append` site in acquisition. Those sites
  accumulate into a local list and construct the record once, which is the shape the frozen
  boundary wants anyway.
- **`asdict` preserves the collection type.** `dataclasses.asdict` reconstructs sequences via
  `type(obj)(...)`, so a tuple field comes back as a **tuple**, not a list. `json.dumps` then
  emits it as a JSON array, so the on-disk JSON is unchanged — but any intermediate projection,
  golden comparison, or CSV cell holding a tuple sees a tuple. Normalization to lists is
  therefore the **serializer's** job in `output_schemas.py`, stated explicitly, and the golden
  compares the normalized projection rather than raw `asdict` output. Field order is
  `__dataclass_fields__` order either way, which is what `ART-SCHEMA-002/003` pin.

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

First, which dependencies are actually optional. `pyproject.toml` today makes `openpyxl` a
**mandatory** dependency and only `playwright`, `PyMuPDF`, and `opencv-python-headless`
extras, so treating all four alike would be wrong:

| Distribution | Status | Owning adapter | Extra |
| --- | --- | --- | --- |
| `openpyxl` | mandatory | `adapters/files/tabular.py` (XLSX path) | — |
| `PyMuPDF`, `opencv-python-headless`, `numpy` | optional | `adapters/pdf/` | `pdf` |
| `playwright` | optional | `adapters/scoutevent/` (2b) | `acquisition` |
| `fastapi`, `uvicorn`, `python-multipart`, `pywebview` | mandatory | `interfaces/web`, `interfaces/desktop` (2b) | — |

`openpyxl` stays mandatory in Phase B. Moving it to an extra would change what a bare install
can load, which is a packaging behavior change and not part of this restructure.

Contract:

- Importing `scoutmb`, anything under `core/` or `ports/`, or any `features/` module pulls in
  **no** optional dependency. This is achievable precisely because parsing lives in adapters:
  `features/ingest` imports the `attendee_source` port, never `adapters/pdf`.
- An adapter that needs an optional distribution imports it inside the function that uses it,
  or behind a module-level guard in that adapter only.
- A missing optional dependency raises `CapabilityUnavailable` (a `ScoutmbError` subclass)
  carrying the capability name, the distribution names, and the exact
  `pip install 'scoutmb[<extra>]'` remedy — never a bare `ImportError` traceback.
Enforcement is two separate tests, because neither alone establishes the contract:

1. **Import isolation, enforced by a meta-path blocker.** A `python -I -c` child installs a
   `sys.meta_path` finder that raises `ImportError` for `cv2`, `fitz`, and `playwright`, then
   imports **every leaf module** under `core/`, `ports/`, and `features/` — enumerated by
   walking the package, not a hand-kept list that silently stops covering new modules. If any
   module reaches a blocked dependency the import raises and the test fails, naming it.
2. **Capability failure.** In the same blocked child, call the PDF capability entry point and
   assert `CapabilityUnavailable` naming its extra — proving the guard converts a *real*
   `ImportError` rather than a monkeypatched stub.

**A note on how NOT to write these.** `python -I` implies `-E` and therefore **ignores
`PYTHONPATH`**. A probe that sets `PYTHONPATH` in the child's environment and runs `-I` imports
whatever is already installed — for this repo, the editable `scoutmb` — and passes while
testing nothing. Where a subprocess needs a path, set it *inside* the executed source
(`sys.path.insert(...)`), or install into a real venv and run that interpreter. The existing
`tests/harnesses/subprocess.py::run_import_probe` already does this correctly and is the
reference implementation.

The blocker is preferred over an extras-free venv because it is stronger: absence-from-a-venv
plus `sys.modules` inspection cannot distinguish "never attempted" from "attempted, raised
`ImportError`, and got swallowed by a bare `except`". A blocker fails at the attempt.

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

### Dependency rules

The layer roles above are enforced mechanically, and the rule has to be precise about what
"imports" means or it can be satisfied while being false.

Allowed edges, and no others, between first-party `scoutmb` modules:

```text
interfaces  ->  interfaces, features, core, ports, config, errors,
                adapters (composition roots only)
features    ->  features, core, ports, config, errors
adapters    ->  adapters, core, ports, config, errors
runtime     ->  core, ports, config, errors
core        ->  core, errors
ports       ->  core, errors
```

Same-layer edges are permitted and necessary: `interfaces/cli/pdf.py` must import
`interfaces/cli/composition.py`, and `adapters/html/` must use `adapters/files/atomic.py` to
publish. An earlier draft omitted them while saying "and no others," which forbade the wiring
the design requires.

Enforcement details, all of which are load-bearing:

- The check runs over the **transitive** first-party import graph, not direct imports only.
  `core` importing a module that imports an adapter is a violation.
- Both **static** (module-level and function-level `import` statements found by AST walk) and
  **runtime** imports are covered. Function-level imports are the common way this rule gets
  quietly broken, and the graph is built from the AST so they are visible.
- Dynamic imports inside `core/`, `ports/`, or `features/` are banned as a **syntactic
  restriction**, not a semantic one, because "any dynamic import" is not decidable. The
  prohibited AST forms are exactly: a `Call` whose function resolves to the name
  `importlib.import_module`, `importlib.__import__`, `__import__`, `imp.load_module`, or
  `exec`/`eval` with a string argument. Anything cleverer than that list defeats the check and
  is a review problem rather than a lint problem — the rule exists to stop the ordinary case,
  and says so. Adapters may use `importlib` only for the optional-dependency guard below.
- `interfaces` is the only layer permitted to import an adapter, and only from a **composition
  root**, which is the module `interfaces/<name>/composition.py` and no other. Naming the file
  is what makes the rule checkable — "a module whose sole job is wiring" is not a property a
  linter can evaluate, so the convention carries it. An adapter import anywhere else under
  `interfaces/` fails.

Consequence worth stating rather than discovering: `interfaces/web/composition.py` drives both
pipelines, so it imports the PDF adapter and the ScoutingEvent adapter, and the local web app
therefore requires every extra installed. That matches today's behavior — `ui/server.py`
imports both flat modules, which import `cv2`, `fitz`, and `playwright` at module scope — so
it is not a regression. The optional-dependency contract below constrains `core`, `ports`, and
`features`; it does not promise a web app that runs without the extras.

### No `__file__` in the package

The parent spec bans deriving data paths from `__file__` (D6). Phase B implements that as a
flat prohibition rather than a dataflow rule:

> `__file__` may not appear anywhere under `src/scoutmb/`.

An earlier draft specified a check "keyed on `__file__` appearing anywhere in the dataflow of
an argument to the data-root resolver." That is interprocedural taint analysis, not something
an AST walk decides, and specifying it would guarantee a weak approximation shipping under a
strong description.

The check is a **lexical token scan**, not an AST walk: `tokenize` the module and reject any
`NAME` token equal to `__file__`. A token scan is used because an AST walk misses `__file__`
inside a string passed to `eval`, and because the flat ban has no legitimate exception to
carve out — there is nothing for a syntax tree to disambiguate.

The ban is achievable only if bundled resources can be read without it. The intended mechanism
is `importlib.resources.files("scoutmb.resources")`, which requires `resources/` to be a real
package with an `__init__.py` and the templates declared as package data in the build config.

**This mechanism is plan-verified, not asserted here.** The release root is a *copied
directory*, not an installed distribution, and `importlib.resources` behavior in that setting
depends on how the package is laid out and imported. The first Slice 2a task that touches
`resources/` must prove `files("scoutmb.resources").joinpath(...).read_text()` works from (a)
an installed wheel and (b) the copied release root, before any template moves. If it does not
work from the copied root, the resource-loading mechanism changes and this section is amended
— the `__file__` ban stands either way, since a `__file__`-based loader is what the ban exists
to prevent. No claim is made about zipped distributions; that case is untested and unused.

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

The two stage scripts mirror the two flat scripts **argument for argument**. Spelled out,
because "same arguments" is where this contract gets read loosely — preserved unchanged:

- the full option set, their short and long forms, and every default value;
- exit codes for success, handled error, and interrupt;
- **stdout** content, and **stderr** content, byte for byte;
- `--help` / usage text, except for the program name substitution itself;
- behavior under a relative `--output` path, i.e. resolution against the process working
  directory rather than anything derived from the package location.

Only the program name differs. This is what lets the `CLI-SCHED-*` and PDF-CLI cases be
re-pointed at retirement without editing a single expected value. A `troop349 <subcommand>`
dispatcher is rejected for the same reason: it would change the argv prefix every one of
those cases is pinned to.

Entry-point tests **execute the installed console script as a subprocess**. Calling `main()`
in-process is not equivalent: it skips the wrapper that `pyproject.toml` generates, the
`sys.argv[0]` the parser sees, and the exit-code path. Both are worth having, but only the
subprocess form tests what a user runs.

`pyproject.toml` currently declares `troop349 = "scoutmb.cli.app:main"`, which names a
module that has never existed; the console script is broken today and Slice 2 fixes it.

### Release root

Gate 2 requires a copied release root that starts with no repository present, and D2 keeps
the source-copy bridge until the transactional payload install replaces it in Slice 3/4. The
condition is only testable if the layout is named, so:

```text
<app_dir>/
  run_app.py                 launcher entry (or its package-era replacement)
  scoutmb/                   copied from src/scoutmb, including resources/ and py.typed
  requirements.txt
  scouts.csv  pdf-uploads/  runs/     pre-existing user data, never touched by a sync
```

**Three** places must change together, and an earlier draft named only one.

1. `bootstrap/source_sync.py` extends its `_FILES`/`_DIRS` allowlist to copy `src/scoutmb` to
   `<app_dir>/scoutmb`, keeping the sync a targeted overwrite of an explicit allowlist, never
   a directory wipe.
2. `bootstrap/build.spec` adds `src/scoutmb` to `datas` under `app_src`. Its current list
   carries only the four flat modules, `requirements.txt`, and `ui/` — so a built installer
   would have nothing to sync, and step 1 alone would silently no-op in the one configuration
   that matters.
3. `bootstrap/python_env.py` already appends `app_dir` to the embedded interpreter's `.pth`
   file, which is what puts it on `sys.path`. That entry keeps working for `scoutmb` with no
   change, but the dependency must be recorded — it is load-bearing and non-obvious.

An earlier draft claimed `scoutmb/` beside the entry script "imports without any `sys.path`
mutation" because the launcher runs with `app_dir` as its script directory. That is **false**
for this runtime, and `python_env.py` says so in a comment: the embeddable distribution's
isolated path mode does not add the launched script's directory to `sys.path`, which is
precisely why the `.pth` patch exists. The architecture rule is still satisfied — the `.pth`
entry is interpreter path configuration written by bootstrap, not first-party code mutating
`sys.path` at runtime — but the stated reason was wrong and the mechanism is bootstrap's, not
Python's.

Acceptance is a specific sequence, not a claim: copy the release root to a temporary directory
outside the repository, remove the repository from the environment, launch under the embedded
interpreter configuration, and assert the health endpoint responds and one report renders. The
2b plan owns the exact invocation; what this document fixes is that all three change sites and
the assertion exist.

## The oracle invariant

This is the load-bearing rule of Phase B.

> **A move may add or re-point a runner. It may never edit a case's expected observation.**

`tests/matrix/cases/*.py` is data-only and holds no assertion logic, so any diff touching
`expected_by_context` is visible in review immediately. Changing an expected value requires
reclassifying the case to `intentional-change` with a named `target_owner` and a written
`target_observation` — which is what makes a behavior change a reviewed decision instead of
a refactor artifact.

**Visible in review is not the same as enforced.** One commit can edit an expected value, its
classification, its owner, the coverage baseline, and this document together, and nothing
mechanical objects. So the invariant is backed by a check: a digest over every `preserve`
case's `(case_id, expected_by_context)` pair is checked in beside
`tests/baselines/phase_a.json`, and CI fails when the computed digest differs from the stored
one. Updating it is an explicit command that prints which case IDs changed, and the Gate runs
in check mode only — the same shape as the coverage baseline this repo already enforces.

That is deliberately lighter than a per-case approval allowlist keyed to a spec digest. With
one owner and no external consumers, the failure mode worth defending against is *forgetting*
— editing an expectation to make a red test green and not noticing the significance — not an
adversary. A digest that names the changed case IDs stops that.

**Escape hatch.** If implementation reveals a genuine correctness bug that requires an
expected value to change and no sanctioned exception covers it, that is not a reason to
deadlock behind a spec amendment. Reclassify the case to `intentional-change`, name the owner,
write the `target_observation`, update the digest, and record the row in this document's
exception table in the same commit. The rule is that the change is *declared and attributable*
— not that it is impossible.

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
satisfied only when **both** runners pass it.

Be precise about what that buys, because it is less than it sounds. Where the shim is a
**re-export**, the two runners execute the same function object, so both-green is one result
counted twice — it proves the catalog is satisfied, not that two implementations agree.
Where the shim **adapts** (`parse → core → serialize`), the two paths genuinely differ and
both-green catches a broken parser or serializer. The rule is retained for the second case
and as a guard against a runner being silently dropped from collection; it is not
independent verification of the move, and must not be described as such in a plan or a gate
report.

What actually protects a move is the **depth of the observation**, which is why the section
below exists.

### Observation depth and golden projections

Several catalog observations are much shallower than the domain they cover, and the
restructure is exactly the kind of change they would miss:

- `ART-SCHEMA-006` observes the embedded report data as a bool, a top-level key set, and two
  integer counts. Nothing about the fields inside `scouts[]`, `classes[]`, `requirements[]`,
  or `errors[]`.
- `ART-SCHEMA-008` observes file counts, a greeting prefix, and a doctype.

So a move that dropped `class_completed` from every requirement row, changed a numeric field
to a string, reordered a collection, or broke per-scout correspondence between a name and
its rows would leave the artifact domain green.

Phase B closes this **additively**, without touching any existing case, using two golden
fixtures rather than one. Two are required because 2a both moves the reporting code *and*
changes what it emits (the shareable projection), so a single pre-move golden would be
invalidated by an intentional change inside the same slice.

- **Golden V1** — the operational projection, generated before the first reporting symbol
  moves. Its job is to prove the *move* changed nothing.
- **Golden V2** — the shareable projection, generated after the tiering lands. Its job is to
  be the new contract.

The gate asserts more than "each golden matches." It asserts the **V1→V2 diff is exactly the
declared field substitution and nothing else** — `attendee_id` removed, `output_id` inserted
at that index, across the **four transformed row collections** (`scouts[]`, `classes[]`,
`requirements[]`, `errors[]`); the top-level object is unchanged, which is what `ART-SCHEMA-006`
already pins. That is stronger than either golden alone, because it catches a move-induced
change hiding inside an intentional one, which is the specific way a refactor smuggles a
regression past a gate.

**Required scope — exact values, not shapes.** An earlier draft asked for "every field with its
Python type," which would pass while every cell held the wrong content. Both goldens record:

- the **full canonical value** of every cell in all four collections, not merely field names
  and types;
- rows keyed by `output_id` (or by position within the null-identity group), **not by display
  name** — keying on name collapses two same-named attendees into one entry, which is the exact
  corruption D3 exists to prevent and which a golden must therefore be able to see;
- the complete text of every rendered email body and subject, byte for byte;
- the per-scout mapping from `output_id` to its rows and its output files.

The generating fixture must contain, at minimum: two attendees sharing a display name with
different upstream IDs; one attendee with zero classes; one with a partial failure (some
classes acquired, one error); and one pre-identity failure carrying `output_id: null`. A golden
built only from clean single-attendee data proves almost nothing about this refactor.

**What a golden is and is not.** It records what the code *does*, not what it *should* do. The
catalog is the correctness oracle because its expectations were hand-computed from the source;
a golden is drift detection, and it will faithfully freeze a bug living in a field no case
observes. That is acceptable here — detecting unintended change is the entire job during a
restructure — but it must not be described as equivalent to a catalog case, and it never
outranks one. Where the two overlap, the catalog wins and the golden is regenerated.

It is also deliberately **not** a differential harness against a frozen pre-move wheel. The
catalog's expectations are already implementation-independent, so the real gap is observation
depth; preserving an old implementation would work around that rather than close it, and costs
a second build pipeline to maintain.

Generation is a one-time reviewed step per golden, and regenerating later is an explicit
command that prints a diff — the same discipline the coverage baseline already uses.

**Lane coverage.** The rule applies per lane, not only to the default lane. The eleven
browser-lane and three authentic-lane cases get package runners on the same terms, and the
authentic lane matters most for the 2a domains — it is the only place the package's ingest
and PDF adapters meet real upstream shapes. Gate 2a runs the authentic lane with
`--require-corpus`; a skip is not a pass.

**Property tests.** The parent spec's testing strategy puts Hypothesis on parsers and state
transitions, and Phase B is where both appear. Two are required rather than optional.

The first is the DTO round trip, stated in the **correct direction**:
`from_mapping(to_row(dto)) == dto` for every generated DTO. An earlier draft specified
`to_row(from_mapping(x)) == x` over arbitrary mappings, which is not merely hard but false by
construction — `from_mapping` coerces types, resolves header aliases, drops unknown keys, and
supplies defaults for absent ones, so the mapping it started from is not recoverable. Starting
from a DTO makes the property true and still exercises both directions. The DTO generator must
cover all 26 requirement-number shapes; a generator that only emits well-formed numbers tests
nothing the catalog does not already cover.

The second is totality of the run-state transition table in 2b: every state/event pair either
has a defined transition or fails closed, with no pair falling through.

These complement the catalog; they do not substitute for any case in it.

### Where the DTO boundary lives

`core/models.py` holds record shapes and no serialization logic, so `from_mapping` and `to_row`
cannot live on the records — an earlier draft's shim example called `RequirementRow.from_mapping`
without ever saying what `RequirementRow` was or where it lived.

They live in `core/output_schemas.py` as **module-level functions over the record types**, not
methods:

```python
def requirement_from_mapping(data: Mapping[str, object]) -> RequirementRecord: ...
def requirement_to_row(record: RequirementRecord, *, shareable: bool) -> dict[str, object]: ...
```

Free functions keep `models.py` dependency-free and let the operational and shareable
projections be one parameter apart rather than two parallel method hierarchies. The shim
template below is written against these names.

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

"Contains no business logic" is checked by comparing each definition's AST **shape against an
explicit shim template**, not by enumerating banned node types. Template-matching is used
because a ban-list is simultaneously too strict and too weak: it rejects harmless argument
normalization while still permitting a single forwarding call whose arguments hide arbitrary
work in a nested expression or an imported helper.

The permitted shapes are:

```python
# Form 1 — re-export
from scoutmb.core.inference.numbering import requirement_path   # noqa: F401

# Form 2 — adapting shim: parse, delegate, serialize. Nothing else.
def annotate_requirement_statuses(requirements):
    rows = tuple(requirement_from_mapping(item) for item in requirements)
    return [requirement_to_row(row, shareable=False) for row in annotate(rows)]
```

A module passes when every top-level statement is an import, a module-level binding of an
imported name or a literal, or a definition matching Form 2: at most one call to a package
function, whose arguments are either passed through unchanged or wrapped in a single
comprehension over a named DTO constructor, and whose result is returned either directly or
through a single comprehension. No branching, loop nesting, `try`, arithmetic, or
string-building.

Be honest about the limit: this establishes *shape*, not semantic purity. A `from_mapping`
that grew a side effect would still match the template. What the check guarantees is that a
shim cannot accumulate visible logic — the DTO constructors it delegates to are themselves
package code under the package's own tests.

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

### The shareable report schema

"Drops `attendee_id`" is not a specification, so here is the schema. The shareable
projection of the embedded report data has exactly these keys, and the enforcing test
asserts the **complete** field set of each row rather than the absence of one name:

| Collection | Fields | Change from operational |
| --- | --- | --- |
| top level | `generated_at_local`, `generated_at_iso`, `run_id`, `scouts`, `classes`, `requirements`, `errors` | unchanged (`ART-SCHEMA-006` holds) |
| `scouts[]` | `name`, `output_id`, `class_count`, `requirement_count`, `error_count` | `attendee_id` → `output_id` |
| `classes[]` | every `ClassRecord` field except `attendee_id`, plus `output_id` | `attendee_id` → `output_id` |
| `requirements[]` | every `RequirementRecord` field except `attendee_id`, plus `output_id`, plus the inference fields `annotate_requirement_statuses` adds | `attendee_id` → `output_id` |
| `errors[]` | `scout_name`, `output_id`, `error` | `attendee_id` → `output_id` |

`output_id` is the per-run UUIDv4 from `RunIdentity`, which gives the report JS a stable
per-scout key without exposing upstream identity.

**This is a projection, never a record change.** `output_id` is not added to `ClassRecord` or
`RequirementRecord`. Adding a field would change `__dataclass_fields__`, which is exactly what
`ART-SCHEMA-002` and `ART-SCHEMA-003` pin as the CSV header. The substitution happens in
`output_schemas.py` when building the shareable row, and the record shapes are untouched.
Within the projected row, `output_id` occupies the position `attendee_id` held, so the
transformation is a deletion plus an insertion at the same index — never a reordering.

#### Single run-scoped identity

The substitution requires one `RunIdentity` per run, and today there is not one.
`RunIdentity` is instantiated in three independent places: `process_scout` (defaulted),
`async_main` (threaded into `process_scout`, so `raw/` filenames share a map), and
`write_email_reports`, which creates its **own** instance because `write_outputs` passes it
none. The same attendee in the same run therefore receives one UUID in `raw/` filenames and a
different UUID in `emails/` filenames.

`write_html_report` has no `RunIdentity` parameter at all, so a naive implementation of this
schema would create a third map, and the report's `output_id` would match neither the email
filenames nor the raw filenames. A cross-reference key that does not cross-reference is worse
than no key.

Phase B therefore requires: **one `RunIdentity` created at the run's composition root and
threaded through acquisition, reporting, and email rendering.** No collaborator constructs its
own. This is a prerequisite for the shareable projection, not an independent cleanup, and it
is also what makes `ACQ-RESUME-003` meaningful — persisting one of three maps in the
checkpoint would leave the other two regenerating fresh UUIDs on resume.

Filename stems already consume a passed-in `output_id`, so this is a threading change, not a
change to `attendee_filename_stem`. Because the UUID is random, existing `ART-NAME-*`
expectations already normalize it and are unaffected.

#### Attempts with no identity

Identity is not always available, and the schema must say what happens when it is not.
`process_scout` constructs its `ScoutResult` from the scout's name and QR URL **before** the
attendee ID exists — the ID is read from the schedule request's post data, several statements
later. If navigation or the schedule response fails, the `except` clause records the error and
returns a result whose `attendee_id` is still empty. That is preserved behavior: a failed
attempt still appears in `errors.csv` and in the report's `errors[]`.

`AttendeeId.parse("")` raises `MissingAttendeeId`, so `RunIdentity` cannot mint an `output_id`
for such a row, and a schema that requires one in every `scouts[]` and `errors[]` entry is
unsatisfiable as written.

The contract: an attempt with no resolved identity carries `output_id: null`, never a
placeholder string, never a fabricated UUID, and never an omitted key. `null` is chosen so the
report JS distinguishes "this row has no identity" from "this row belongs to scout X" without
string comparison, and so two unidentified attempts never collide into one apparent scout.
Rows with `output_id: null` are grouped by nothing — each is its own entry.

Both goldens must include a pre-identity failure attempt, and the end-to-end identity
assertion in Gate 2a covers the null case explicitly. This is the path most likely to be
missed, because every successful-run test has an identity by construction.

#### Encoding and line terminators

Pinned as part of the schema, because the current behavior survives on an interaction that a
rewrite would plausibly break: CSV bytes are produced by `csv.DictWriter` into a `StringIO`
(default `lineterminator="\r\n"`), then written by `atomic_write_text`, which opens with
`newline=""`. The `newline=""` is what prevents Python from translating the terminator. Change
either half and `ART-SCHEMA-002/003` fail.

The contract: CSV artifacts are `utf-8-sig` with `\r\n` terminators written through a handle
opened `newline=""`; `scouts.json` and `report.html` are `utf-8` without a BOM. Encoding is
per-artifact and is part of the output schema, not an adapter detail.

The enforcing test is not a substring scan. It requires:

- a synthetic fixture carrying a distinct sentinel in **every** forbidden position — upstream
  attendee ID, QR token, session material, raw payload fragment, and absolute path — so a
  leak through any one of them fails on its own;
- exact field-set equality per collection, so a field added later cannot smuggle identity in
  without failing;
- assertion against the rendered file's parsed JSON, not the pre-render dictionary, so the
  template substitution path is covered too.

Both audience-shareable email bodies get the same sentinel fixture and the same
whole-content assertion via goldens V1 and V2 above.

Net effect: the tiering requires **two** production changes, not one. The visible change is
the `report.html` projection, where `attendee_id` currently reaches the embed four ways —
`scouts[]`, `classes[]` and `requirements[]` via `asdict`, and the `errors[]` list built
explicitly. The second is the single run-scoped `RunIdentity` described above, which the
substitution depends on and which does not exist today. An earlier draft of this section
claimed the projection was the only change; that was wrong, and the identity threading is the
larger of the two.

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

No `REQ-*` case covers duplicate requirement numbers within a group. Slice 2a adds one
**before** re-expressing the walk — but "add a duplicate-number case" is not sufficient, and
a generic one would be vacuous. Most duplicate arrangements resolve identically under both
schemes and would pass whichever way the re-expression went.

The fixture must be **discriminating**: a `(scout, class)` group in which the positional
parent from `children[]` and the last-wins ancestor from `by_key` are *different rows*. That
requires at minimum two rows sharing one `requirement_number` at the parent depth, each with
distinguishable content, plus a child whose `parent_requirement_number` matches that shared
number — so the walk's choice of ancestor is observable.

And it must observe the fields that reveal *which* row was chosen. Asserting only that some
ancestor was selected passes under both schemes. The observation covers, for every selected
row: `requirement_number`, `description` (the two duplicate rows carry different
descriptions), `depth`, and `is_leaf` — the four fields `build_missing_requirements` puts in
its entry dicts. A case that omits `description` cannot distinguish the two candidates and
does not satisfy this requirement.

The re-expression must then reproduce whichever resolution the legacy code exhibits. If that
behavior is judged wrong, changing it is a separate `intentional-change` row with its own
owner, not part of the move.

## Gates

### Gate 2a — Core & Content

- Both runners green for every execution key in the input, PDF, requirement, and artifact
  domains — legacy runners against the shims, package runners against `scoutmb`.
- Golden V1 and V2 both match on **exact cell values**, keyed by `output_id`, over the fixture
  containing two same-named attendees, a zero-class attendee, a partial failure, and a
  pre-identity failure. The **V1→V2 diff equals exactly** the declared
  `attendee_id`→`output_id` substitution across the four transformed collections, with no other
  field, value, type, or ordering change.
- Exactly one `RunIdentity` exists per run: acquisition, the HTML report, and email rendering
  all report the same `output_id` for the same attendee, asserted end to end rather than per
  writer. An attempt that failed before identity resolution carries `output_id: null` in every
  surface, and two such attempts never merge.
- Optional-dependency isolation proven by a `python -I` subprocess in an extras-free
  environment importing every enumerated leaf module of `core`/`ports`/`features`, plus a
  separate assertion that the PDF and acquisition entry points raise `CapabilityUnavailable`.
- The `preserve`-case digest matches its stored value; no `expected_by_context` edited except
  `ART-NAME-007`; every added case accompanied by a reviewed `phase_a.json` bump.
- The discriminating duplicate-requirement-number case exists, its two candidate rows carry
  different descriptions, and it observes `description` — so it can actually distinguish
  positional from last-wins ancestor resolution.
- Dependency-rule test green over the **transitive** first-party import graph, with the
  allowed-edge table (including same-layer edges) enforced, adapter imports confined to
  `interfaces/<name>/composition.py`, the enumerated dynamic-import forms absent from
  `core`/`ports`/`features`, no first-party `sys.path` mutation anywhere, and **no `__file__`
  token anywhere under `src/scoutmb/`** by lexical scan.
- `importlib.resources.files("scoutmb.resources")` proven to read a template from both an
  installed wheel and the copied release root, with `resources/__init__.py` present in each.
- CSV artifacts round-trip as `utf-8-sig` with `\r\n` terminators through a `newline=""`
  handle; `scouts.json` and `report.html` are BOM-free `utf-8`.
- Coverage: package areas meet their D10 floors; the `include` pattern reaches every
  package module and the existing missing-file check confirms each declared area file
  appears in the report; no legacy area regresses below its baseline unless it has been
  replaced by the no-business-logic assertion.
- A clean-environment wheel install succeeds, and `resources/templates/` and `py.typed` are
  verified **inside the built wheel's contents**, not merely present in the source tree.
- Every console script that exists at this point runs `--help` from outside the repository
  and its usage text matches the flat script it replaces, program name aside.
- `troop349-pdf` runs stage 1 as a **subprocess** from a directory outside the repository.
- Importing the core surface in a subprocess without the optional distributions installed
  leaves `cv2`, `fitz`, and `playwright` absent from `sys.modules`, and requesting a missing
  capability raises `CapabilityUnavailable` naming the extra.
- The shareable projection asserts exact field sets per collection against the rendered
  file's parsed JSON, with a distinct sentinel in every forbidden position; the per-scout
  email bodies are covered by the same fixture.
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
- All three console scripts run `--help` and their stage-equivalent argv from outside the
  repository, matching the flat scripts they replace on stdout, stderr, and exit code.
- Flat modules retired and `tests/harnesses/legacy.py` removed with them.
- All three release-root change sites landed — `source_sync` allowlist, `build.spec` `datas`,
  and the `.pth` dependency recorded — and the acceptance sequence passes: copy the root
  outside the repository, remove the repository, launch under the embedded interpreter
  configuration, health endpoint responds, one report renders.
- Async shutdown: cancelling during a blocking adapter operation leaves no pending task after
  lifespan exit, including work dispatched through `asyncio.to_thread`.
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

## Deliberate simplifications

An independent review (OpenAI Codex, 2026-07-24) raised four things this document declines,
recorded here so they read as decisions rather than oversights.

**No differential harness against a frozen pre-move implementation.** Proposed to cover
shallowly-observed surfaces. Declined because the catalog's expectations are hand-computed and
therefore already implementation-independent; the gap is observation depth, and preserving an
old implementation works around that instead of closing it. The golden-projection requirement
closes it directly, and a golden is one reviewed file rather than a second build pipeline.

**No per-case approval allowlist keyed to a spec digest** for the oracle invariant. Reduced to
a digest over `preserve`-case expected observations that names changed case IDs on failure.
With one owner and no external consumers, the failure mode is forgetting, not an adversary,
and the digest stops forgetting at a fraction of the machinery.

**The 2a/2b seam stays a scheduling heuristic.** "Touches Playwright or FastAPI" is not an
architectural rule, correctly. It is not trying to be one — its only job is deciding which
slice a boundary ships in. The architectural rule is the allowed-edge table under Dependency
rules, which is enforced mechanically and outlives the slice split.

**`Jitter` stays a named collaborator** rather than becoming a general seeded-RNG protocol
with distribution owned by the retry policy. The cleaner shape is granted, but D32 names
`Jitter` and the parent spec's collaborator list is not worth churning for one use site.
Reconsider if a second randomized behavior appears.

## Open questions

None. Every Phase B contract above is decided. Items the parent spec marks POSTPONED remain
deferred by decision, not by omission.
