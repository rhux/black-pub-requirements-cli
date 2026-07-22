# ScoutMB Software Foundation Design

**Date:** 2026-07-21
**Status:** Engineering decisions locked; implementation plan must be regenerated against this revision
**Supersedes:** `docs/refactor-plan.md` and the earlier revision of this specification
**Related plan:** `docs/superpowers/plans/2026-07-21-scoutmb-foundation.md`
**Review state:** Architecture, correctness, testing, performance, migration, and distribution decisions D1-D26 are recorded in the decision appendix

## Problem

ScoutMB began as a quick Python script. It is now an application with two data pipelines,
a FastAPI web interface, a desktop launcher, and a self-bootstrapping installer. It exists
because the legacy `scoutingevent.com` PHP and jQuery UI workflows are not reliable enough
for the troop's operational needs.

The current repository has useful behavior, but not yet a safe software foundation:

| Component | Approximate size | Current responsibility |
| --- | ---: | --- |
| `scout_schedule_cli.py` | 1,798 lines | Browser acquisition, inference, and reporting |
| `pdf_to_scouts.py` | 579 lines | PDF and QR extraction into CSV |
| `ui/server.py` | 339 lines | Local FastAPI application |
| `ui/static/app.js` | 328 lines | Browser UI |
| `run_app.py` | 89 lines | Desktop entry point |
| `bootstrap/` | 14 modules | Windows launcher, runtime, and source installation |

The code works well enough to be valuable, but its boundaries allow silent data corruption,
unsafe upgrades, hard-to-reproduce behavior, and tests that would otherwise need live access
to a third-party service containing data about minors.

### Confirmed correctness and structural defects

The refactor must preserve the useful behavior while fixing these confirmed defects:

1. Display names are used as attendee identity in grouping, lookup, and filenames. Two
   attendees with the same name can have requirements merged and output files overwritten.
2. `ui/server.py` creates unreferenced background tasks that can disappear before work
   completes.
3. The UI has unsafe stale-file deletion, a Windows-only `os.startfile` path, a server-side
   `webbrowser.open`, and unguarded JSON decoding.
4. `--quiet` is not honored consistently.
5. `scout_schedule_cli.py` combines argument parsing, four input loaders, browser control,
   retry policy, response parsing, inference, templates, and output writers.
6. `process_scout` combines browser state, retries, deduplication, mapping, and filesystem
   writes.
7. `argparse.Namespace` crosses into application logic; the UI constructs a synthetic
   namespace and can silently omit newer options.
8. Inference uses untyped dictionaries and internal object identity through `id(item)`.
9. User data is stored next to replaceable application source.
10. External JSON is trusted too far into the application, so an upstream schema change can
    be interpreted as a legitimate incomplete requirement.
11. Logging, timing, jitter, IDs, and output publication are not consistently controlled.
12. The launcher synchronizes loose source files in place and has no transactional application
    release boundary.

### Claims that must not be reintroduced

- Inference copies its input dictionaries before mutation. It does not currently mutate
  caller-owned dictionaries at its public boundary.
- The HTML and email inference consumers currently receive the same shape. They still need
  separate contract coverage because they are independently reachable.
- `write_html_report` already accepts generated timestamps. Its caller owns the remaining
  clock nondeterminism.
- HMAC does not require special hardware. It was rejected here because a stable derived value
  is unnecessary for shareable output and would remain linkable across runs.

## What already exists

This is a strangler refactor, not a rewrite. The implementation must reuse and characterize:

- The current PDF extraction and QR decode paths, including embedded and rendered QR fallbacks.
- The current CSV, JSON, text, and XLSX input formats and header aliases.
- The current browser workflow and its proven login, cookie, CSRF, and legacy-site semantics.
- The current requirement numbering, tree construction, completion, choice, and missing-work
  inference behavior.
- The current HTML, CSV, JSON, email, error, and summary outputs.
- The current FastAPI and desktop workflows.
- The current standard-library bootstrap modules and source-copy launcher bridge.
- The gitignored `raw_data/` corpus as an optional local verification asset only.

No replacement implementation is accepted until an implementation-neutral contract suite can
run the legacy and new adapters against the same inputs and compare normalized outputs.

## Goals

- Prevent same-named attendees from sharing state or overwriting one another.
- Put pure rules behind stable boundaries and all I/O behind adapters.
- Preserve every intentional legacy behavior through an explicit behavior contract matrix.
- Detect upstream schema and selector drift before it creates confidently wrong results.
- Make output publication, installed-data migration, and application updates transactional and
  recoverable.
- Keep the e-mailed installer small while allowing required and optional capabilities to be
  downloaded separately.
- Make the default test suite deterministic, offline, and incapable of calling
  `scoutingevent.com`.
- Support Windows and macOS without requiring a system Python.
- Add useful local diagnostics now and an OpenTelemetry-shaped seam for later, without making
  the application depend on connectivity or telemetry infrastructure.
- Leave the codebase easier to change through idiomatic Python packaging, typing, dependency
  locking, and test-first migration.

## NOT in scope

- Replacing or modifying `scoutingevent.com`; ScoutMB does not own that service.
- Replacing the current requirement inference rules during the structural refactor. Suspected
  defects are characterized first and fixed in separate behavior changes.
- Replacing the frontend with a JavaScript framework.
- Public distribution, multi-tenant operation, or support for troops other than the current
  internal users in this cycle.
- Launcher self-update. The application payload can update; launcher changes require a new
  installer download.
- Production OpenTelemetry export or a remote collector. This cycle supplies only the port,
  no-op implementation, privacy contract, and spool interface.
- Making Safari the default browser. Safari support remains experimental until a live,
  read-only compatibility smoke test proves the legacy site works through `safaridriver`.
- Signed update metadata, Developer ID signing, macOS notarization, key rotation, and signed
  downgrade or freeze protection. This is decision D23 and is intentionally deferred while the
  tool remains internal to the troop. Revisit it before broader distribution or a changed threat
  model.

## Constraints and invariants

1. **Python 3.12 is the shipped runtime.** Code, type checking, lint targets, and CI must reject
   accidental reliance on Python 3.13 or 3.14 APIs.
2. **No real Scout data enters git.** Names, attendee IDs, QR URLs, tokens, raw payloads,
   locally derived corpora, logs, and checkpoints containing real identifiers remain private.
3. **Default tests never call `scoutingevent.com`.** This is enforced, not documented as a
   convention.
4. **The launcher is for non-technical users.** Normal use is double-click, with no system
   Python, terminal, or manual dependency repair.
5. **The e-mailed installer remains small.** The compressed installer must be at most 18 MB.
   This leaves room for the roughly one-third MIME encoding expansion and message headers under a
   common 25 MB total-message limit. CI fails when the attachment artifact exceeds that budget.
6. **One installed copy contains irreplaceable user data.** Reinstalling application code is
   acceptable. Losing or silently replacing user data is not.
7. **The upstream service is unowned and may drift without notice.** Missing and explicit-null
   values are distinct at its boundary.
8. **Shareable artifacts contain no upstream attendee IDs or token-bearing QR URLs.** Private
   inputs, private acquisition checkpoints, and an explicitly requested sensitive export are
   separate classes of data.
9. **Every filesystem artifact is published atomically.** A failed write preserves the last
   complete artifact.
10. **Every installed application update preserves a known-good release.** No live environment
    is mutated in place.

## Architecture

### Architectural style

ScoutMB uses a small hexagonal architecture, also called ports and adapters, with a functional
core. Features remain organized as vertical slices inside the application layer. It does not
adopt the ceremony of a large Clean Architecture implementation.

```text
                     interfaces
               +-------------------+
               | CLI | Web | Desktop|
               +----------+--------+
                          |
                          v
               application features
      +---------+----------+-----------+----------+
      | ingest  | acquire  | inference | reporting|
      +---------+----------+-----------+----------+
                          |
                          v
                  pure domain core
          models | identity | rules | schemas
                          ^
                          |
                ports owned by the app
                          |
       +------------------+-------------------+
       |                  |                   |
       v                  v                   v
 ScoutingEvent       filesystem/PDF     observability
 browser adapter        adapters            adapter
```

Dependency rules:

- `core/` imports no browser, web, filesystem, environment, OpenTelemetry, PDF, or UI modules.
- `features/` may import `core/` and application-owned port protocols.
- `adapters/` implement ports and may import third-party frameworks.
- `interfaces/` construct dependencies at the outside and call feature services.
- CLI, web, and desktop interfaces call the same feature services and typed configuration.
- Protocols exist only at real I/O or nondeterminism seams. Internal pure functions do not get
  interface wrappers for symmetry.
- Optional PDF and telemetry packages cannot be imported by the core installation path.
- Architecture tests reject reverse imports and package cycles.

### Target package layout

The layout is a destination, not permission to create dozens of empty modules up front.
Modules are split when they own a coherent subject or create a tested seam.

```text
pyproject.toml
uv.lock
requirements-launcher.txt       # generated from uv.lock, pinned with hashes
src/scoutmb/
  __init__.py
  __main__.py
  config.py
  errors.py

  core/
    models.py
    identity.py
    requirement_rules.py
    output_schemas.py

  features/
    ingest/
    acquisition/
    inference/
    reporting/

  ports/
    scoutevent.py
    storage.py
    observability.py

  adapters/
    scoutevent/
      gateway.py
      playwright_session.py
      safari_session.py
      payloads.py
      schema_profiles.py
    files/
    pdf/
    telemetry/

  interfaces/
    cli/
    web/
    desktop.py

  resources/
    report.html
    report.css
    report.js

bootstrap/                       # standard library only; frozen separately
tests/
  unit/
  contract/
  integration/
  packaging/
  fixtures/                      # synthetic only
tools/
```

Avoid `utils.py`, `helpers.py`, and `common.py`. Merge tiny modules into their closest subject
when a seam does not justify a file.

### Application data flow

```text
private input
 PDF / CSV / JSON / XLSX / QR URL
                 |
                 v
       validate and canonicalize
                 |
                 +----> private acquisition checkpoint
                 |
                 v
       typed classes and requirements
                 |
                 v
        pure inference and grouping
                 |
                 v
       versioned external-output DTOs
                 |
                 v
      temp write -> fsync -> atomic replace
                 |
                 v
       completion manifest written last
```

## Core contracts

### Attendee identity and privacy

Identity has two deliberately different forms:

1. `UpstreamAttendeeId` is a typed sensitive identifier obtained from ScoutingEvent. It may
   exist only inside the upstream adapter, in-memory processing, and private resumable
   checkpoints. Its dataclass field uses `repr=False`. Missing upstream identity fails closed;
   there is no `unresolved` identity bucket.
2. `RunAttendeeId` is a full `uuid.uuid4()` value assigned once per attendee per run. It is
   persisted in the private run checkpoint so a resume uses the same value. A separate run
   assigns a new unrelated UUID.

All grouping and lookup operations use the typed upstream identity while it is held in memory.
All shareable DTOs and filenames use the run UUID. Display name is display data only.

Example filename:

```text
jane-doe-70ac7c2d-9f4d-49b5-aef0-54dbab722e4d.html
```

The full UUID is used. UUID prefixes, attendee-ID hashes, HMACs, and UUIDv7 are not used.
Tests inject an ID factory so golden output remains deterministic.

Sensitive data classes:

| Class | Examples | Allowed location |
| --- | --- | --- |
| Upstream secret | QR URL/token, upstream attendee ID, raw response | Adapter memory, private input, private checkpoint |
| Private local data | Scout name, source PDF path, diagnostic context | User data root, redacted logs where needed |
| Shareable output | Run UUID, requirement summaries, generated reports | User-selected output directory |
| Explicit sensitive export | Raw upstream IDs when operationally required | Separate command/flag with warning and restrictive filename |

Generated artifacts and logs are scanned for upstream IDs, QR URLs, and known token shapes.

### Typed configuration and path resolution

`argparse.Namespace` is confined to CLI parsing. Frozen, slotted dataclasses hold browser,
pacing, input, report, storage, and observability settings. Web and CLI code construct the same
configuration types and call the same services.

Production data-root precedence is exact:

1. Explicit constructor argument for tests or embedding.
2. `SCOUTMB_DATA_DIR`, interpreted as the exact data root.
3. `platformdirs` user-data directory.
4. `Path.cwd()` only when an explicit development flag is present.

No production data path is derived from `__file__` or an accidental working directory. The
launcher resolves settings once and passes the result into the application.

### Determinism

Inject only the collaborators a feature actually needs:

| Concern | Port or callable |
| --- | --- |
| Timestamps and deadlines | `Clock` |
| Run and operation IDs | `IdFactory` |
| Retry jitter | `RandomSource` |
| Waiting | `Sleeper` |
| Progress | `ProgressSink` |

There is no generic service bag. Output ordering, filenames, timestamps, random jitter, and
serialization are controlled in tests.

### Requirement inference

Inference is a pure typed boundary. It accepts canonical dataclasses and returns canonical
dataclasses. It performs no I/O and reads no clock or environment state.

The existing `id(item)` ancestor bookkeeping is replaced by explicit node indices. Before that
change, characterization tests pin leaf selection, ancestor inclusion, section-header exclusion,
the `(not used)` filter, duplicate numbers, repeated headers, empty paths, label rows, and both
HTML and email consumers.

Suspect legacy behavior is documented and preserved until a separate failing test demonstrates
the desired behavior. Structural movement and behavior correction do not share a change.

### ScoutingEvent gateway

The application owns a `ScoutEventGateway` port. The initial production adapter remains
Playwright-backed because the old PHP/jQuery UI flow may rely on browser session, cookie, CSRF,
or JavaScript behavior. Direct HTTP is allowed only after tests prove semantic equivalence.

The gateway returns an attendee-bound session instead of storing a mutable "current Scout":

```python
class ScoutSession(Protocol):
    async def fetch_schedule(self) -> object: ...
    async def fetch_requirements(self, class_p4_id: str) -> object: ...


class ScoutEventGateway(Protocol):
    def open_session(
        self, qr_url: str, fallback_name: str
    ) -> AsyncContextManager[ScoutSession]: ...
```

The `object` return type is intentional. The adapter must validate containers, fields, and types
before producing core models. An annotation such as `Mapping[str, Any]` would falsely imply that
the untrusted response is already a mapping.

Each attendee session owns its browser context and cookies. Sessions are closed through the
async context manager even on cancellation or parse failure.

### Timeout, retry, and checkpoint behavior

- Every external operation has connect/navigation and read/response timeouts plus a total
  deadline.
- Retry classification is explicit. Transient navigation failures, rate limits, and selected
  server errors may retry. Authentication, validation, and schema errors do not.
- Backoff is exponential with bounded jitter. `Retry-After` is honored only within the total
  deadline and a configured maximum.
- POST retries are allowed only for operations proven read-only or idempotent.
- Browser/session reuse is bounded. Concurrency stays conservative and rate-aware.
- Transport, clock, sleeper, and random source are injectable.
- Errors are typed, carry stable error codes, and redact URLs, tokens, attendee IDs, and cookies.

Acquired data is canonicalized immediately, then the remaining workflow runs locally. Private,
per-attendee checkpoints record completion and the run UUID mapping. Resume skips completed
attendees and never reuses identity from a different run.

### Schema and selector drift

The adapter maintains sanitized response fixture profiles and selector contracts. It validates:

- required containers and fields;
- absent fields separately from explicit `null`;
- field types and permitted flag values;
- required selectors, headings, and content types;
- cross-field invariants;
- a structural fingerprint that ignores volatile values.

Drift severity is explicit:

| Drift | Behavior |
| --- | --- |
| Missing identity, structure, or completion semantics | Fail the attendee or class; open the circuit for repeated systemic failures |
| Wrong type or impossible invariant | Fail closed and record a redacted diagnostic |
| Missing optional display value | Continue with a visible placeholder and warning |
| Unknown added field | Ignore for behavior; include only an aggregate drift count |

The application never updates parsers automatically. A separate, explicitly enabled, low-frequency,
read-only canary may call the real site in staging and alert on drift. It is not part of default
local or CI testing.

### External output schemas

External artifacts use dedicated DTOs. They do not serialize internal dataclasses through
`__dataclass_fields__` or `asdict()` as an accidental public schema.

- JSON and the run completion manifest contain `schema_version`.
- CSV headers have fixed spelling and order; their schema version is recorded in the run manifest.
- Writers emit only the current version.
- Readers accept the current version and explicitly supported prior versions.
- Future versions are rejected with a clear error.
- Compatibility goldens cover version upgrades and intentional differences.

The PDF-import CSV remains a private input artifact and preserves this exact seven-column order:

```text
Attendee Name
Registrant Type
QR Code Contents
Name as Printed
Source PDF
PDF Page
QR Decode Method
```

Its model fields remain `attendee_name`, `name_as_printed`, `registrant_type`, `qr_data`,
`source_pdf`, `pdf_page`, and `qr_decode_method`. Shareable reports replace any existing raw
`attendee_id` field with `run_attendee_id` in the next schema version.

### Atomic artifact publication

Every file writer follows one implementation-owned primitive:

1. Render and validate the complete content before touching the destination.
2. Create a unique temporary file in the destination directory.
3. Write, flush, and `fsync` the file.
4. Atomically publish with `os.replace`.
5. Clean the temporary file on every failure path.

Failure injection covers rendering, write, flush, fsync, and replace from inside the writer. A
failed operation leaves the prior artifact byte-for-byte intact.

For multi-file reports, individual artifacts are atomic and a versioned completion manifest is
published last. Consumers treat a directory without a valid completion manifest as incomplete.

### Report template contract

The large embedded template moves to package resources without adding Jinja2. Static placeholder
validation happens before data insertion:

1. Verify the template contains exactly the expected CSS, JavaScript, and data placeholders.
2. Substitute CSS and JavaScript.
3. Serialize and escape JSON for a script element.
4. Substitute data last.
5. Parse the embedded JSON from the finished HTML and assert round-trip equality.

Do not assert that no `__REPORT_` substring exists after data insertion; legitimate Scout data may
contain that text. Test `</script>`, `&`, U+2028, U+2029, and data containing each placeholder.

### Local diagnostics and future telemetry

Local diagnostics are useful without telemetry:

- structured, rotating local logs;
- run IDs and stable error codes;
- boundary context with automatic secret redaction;
- a user-created sanitized diagnostic bundle;
- no telemetry and no network export by default.

Application code depends on an `ObservabilityPort`. The default is `NoopObservability`. Core code
does not import OpenTelemetry. Event names and attributes are versioned and allowlisted; names,
paths, upstream IDs, run attendee IDs, QR data, URLs, cookies, and tokens are forbidden.

A `TelemetrySpool` protocol reserves the future offline-sync contract: bounded durable storage,
event IDs, at-least-once delivery with deduplication, consent and configuration gates, and a
non-blocking failure policy. A future optional capability may implement it with a SQLite outbox or
OpenTelemetry Collector storage. That implementation is not part of this refactor.

## Installed data and migration

### Migration scope

Migration safety is for the installed application's user data, not for moving source files around
the repository. The legacy source is the installed `app/` directory containing `scouts.csv`,
`pdf-uploads/`, and `runs/`. The destination is the resolved production data root.

### Transaction contract

```text
discover legacy data
        |
        v
hash source manifest (relative path, size, SHA-256)
        |
        v
copy into unique sibling staging paths
        |
        v
verify every staged byte and collision decision
        |
        v
atomic per-artifact promotion
        |
        v
write migration marker last
        |
        v
leave legacy originals untouched
```

Required behavior:

- Migration is copy-only. It never moves or deletes a legacy source.
- Every file is verified with SHA-256. Directory counts alone are insufficient.
- Staged files are flushed and `fsync`ed before verification and promotion; directory metadata is
  synchronized where the platform supports it.
- Existing unequal destinations are never overwritten. The imported copy receives the next unique
  suffix such as `.legacy-1`, `.legacy-2`, and is recorded in the marker.
- Staging paths are siblings of their final targets so `os.replace` stays on the same filesystem.
- The migration marker is the commit record and is written only after every promotion succeeds.
- Interrupted staging and promotion are safe to retry. Unique temp names prevent one run from
  adopting another run's partial file.
- The marker records source and destination roots, source hashes, final paths, collision names,
  application version, and timestamp.
- The old directory receives a small marker text file that explains the active data location and
  tells an operator not to continue editing the legacy copy.

### Post-cutover split-brain detection

Leaving the source in place creates a risk that an old launcher or a person writes new data there.
On every launch while the legacy directory exists:

1. Hash the legacy source and compare it with the cutover manifest.
2. If unchanged, continue.
3. If changed, copy the changed legacy state into a uniquely named private recovery snapshot.
4. Warn with the active data path and recovery snapshot path.
5. Never overwrite or automatically merge active data.
6. The application may block mutating operations until the user acknowledges the warning or chooses
   an explicit recovery action.

Tests cover changes before, during, and after cutover, including a legacy writer racing with the
migration. The real installation is manually backed up before the first production migration.

## Packaging, installation, and updates

### Python project and lock contract

- Use an explicit PEP 517 backend, initially Hatchling.
- `uv.lock` is the canonical dependency resolution and is committed.
- Development tools live in `[dependency-groups].dev`.
- CI uses `uv sync --locked` and fails if `pyproject.toml` and `uv.lock` disagree.
- `requirements-launcher.txt` is generated from the lock, pinned with hashes, and checked for drift.
- Pre-commit and repository instructions tell contributors when lock and export files must change.

The build contract is:

1. `uv build` creates both sdist and wheel.
2. Inspect both archives for expected package data and absence of `raw_data/`, private fixtures,
   tests, logs, tokens, and secrets.
3. Install the wheel in a clean temporary environment outside the repository.
4. Verify imports, entry points, resources, and a minimal command.
5. Build a wheel from the produced sdist and repeat the smoke test.

### Foundation launcher bridge

The foundation phase does not require replacing the current source-copy installer immediately.
`source_sync` must copy `src/scoutmb/` to `app/scoutmb/`, and `bootstrap/build.spec` must include
that package. A clean-root launcher health test proves the installed package imports and starts.

This bridge is temporary. Versioned wheel or release-payload installation replaces it in the
transactional release phase.

### Thin installer and capability downloads

The e-mailed installer contains only the launcher, standard-library bootstrap code, compact UI,
and metadata needed to obtain a release. It does not contain a complete wheelhouse, browser, or
PDF computer-vision stack.

| Capability | Contents | Install behavior |
| --- | --- | --- |
| Core application | UI, reporting, inference, CSV/JSON/XLSX support, `openpyxl` | Downloaded as immutable release payload on first install |
| ScoutingEvent acquisition | Playwright Python package and adapter | Downloaded when acquisition is enabled; required for the main online workflow |
| Browser fallback | Playwright Chromium binary | Downloaded only if a compatible system browser is unavailable or rejected |
| PDF import | PyMuPDF, OpenCV, NumPy, PDF extraction adapter | Optional, separate feature download |
| Telemetry | OpenTelemetry SDK/exporter and spool implementation | Future optional capability, not shipped now |

Downloads are immutable and versioned, support resume, verify size and SHA-256, and are cached.
Runtime installation never resolves dependencies from PyPI. A controlled release location
publishes the exact locked platform payload. After the first successful install, the last known-good
release and installed capabilities work offline. A larger separately distributed offline kit may
contain all payloads.

### Transactional application releases

```text
releases/
  <version>/                 immutable application environment
capabilities/
  browser/<version>/         version-scoped fallback browser
  pdf/<version>/             version-scoped optional feature
state/
  current.json               atomic pointer to active release
  last-known-good.json
  capability-references.json
cache/
data/                        user data, never inside a release
logs/
```

No symlink is required. `current.json` is a small checksummed pointer manifest written through the
atomic file primitive. Release installation is:

1. Download into a unique staging directory.
2. Verify names, sizes, SHA-256, archive paths, and platform metadata.
3. Construct a new versioned environment; never mutate the live release.
4. Run core health and capability readiness checks.
5. Atomically replace `current.json`.
6. Retain the previous acknowledged release and referenced capabilities.
7. Roll back the pointer if readiness or subsequent launch acknowledgement fails.

Capability artifacts are version-scoped and reference-counted. A new Playwright version cannot
silently replace the fallback browser required by the known-good release.

### Health and readiness

An import-only smoke test and "first HTTP request served" are insufficient. Release readiness has
two levels:

- **Core health:** import package, load serializers and templates, resolve and write the configured
  data root, create the FastAPI app, and exercise required local routes.
- **Capability readiness:** verify the selected ScoutingEvent browser engine and any enabled PDF
  capability with local fixtures.

The launcher uses a nonce-bearing, launcher-only local readiness probe rather than accepting any
ordinary request as acknowledgement. After a configured number of failed acknowledgements, it
restores the last-known-good pointer and reports the rollback.

Update checks have short deadlines, run no more than once per day, and never block offline startup.

### Browser selection

Browser selection is an adapter concern and is tested as a deterministic capability matrix.

```text
Windows: installed Edge (msedge)
             -> installed Chrome (chrome)
             -> downloaded Playwright Chromium

macOS:   installed Chrome
             -> downloaded Playwright Chromium
             -> experimental Safari adapter only by explicit override
```

Safari uses `safaridriver`; Playwright WebKit is not treated as Safari. The last successful engine
is remembered with operating-system, Playwright, and browser versions. An explicit user override
wins. Capability failures may fall back; authentication, validation, and schema failures may not be
hidden by trying another browser.

### Integrity without signing

For the current internal-troop distribution, release metadata and payloads use TLS, immutable names,
size allowlists, archive-path validation, and SHA-256 corruption checks. This detects accidental
damage but does not provide strong publisher authenticity when metadata and payload are compromised
together.

That authenticity gap is accepted temporarily under D23. The design must not call the manifest
"signed" or claim checksum verification prevents malicious substitution. Broader distribution or a
changed threat model reopens signing, notarization, key rotation, downgrade, and freeze protection.

## Testing strategy

### Gate 1 behavior contract matrix

Before production code moves, every legacy observable is named in a matrix with input, output,
error behavior, and test. At minimum it covers:

| Area | Contract examples |
| --- | --- |
| Loaders | Four formats, aliases, encoding, ordering, missing columns, invalid rows |
| PDF extraction | Discovery order, embedded and rendered QR, adult filtering, duplicates, strict mode, corrupt PDFs, stale error files |
| Browser orchestration | Navigation, discovery, form payloads, retry delays, dedup, error accumulation, exact status handling |
| Inference | All observed requirement paths and flag pairs, duplicate numbers, notes, empty paths, choice thresholds, both consumers |
| CLI and UI | Defaults, inversions, exit codes, invalid combinations, config parity, progress and quiet behavior |
| Outputs | Exact headers, encoding, ordering, filenames, JSON shapes, HTML embedded data, error text |
| Installer | First install, clean-root launch, offline launch, interrupted downloads, corrupt payload, rollback, capability selection |

Gate 1 stays closed until the matrix passes against the legacy implementation.

### Network policy

`pytest-socket --disable-socket` applies suite-wide by default. Loopback is enabled only for tests
that explicitly need a local fake site or HTTP server. No default test, local command, pre-commit
hook, or CI job calls `scoutingevent.com`.

Live service checks use a separate marker and staging job with all of these controls:

- explicit operator opt-in;
- a safe test account or approved test record;
- read-only operations only;
- low frequency and rate limit;
- no execution in normal local or pull-request CI;
- redacted retained diagnostics.

### Test layers

```text
many:      pure unit and property tests
           contract tests for legacy and new adapters
           synthetic fixture and schema-profile tests

some:      local fake ScoutingEvent through Playwright
           local HTTP downloader and release server
           packaging, migration, rollback, and failure injection

few:       opt-in staging smoke against the real service
           platform installer smoke on Windows and macOS
```

The Playwright fake must implement the actual call surface used by production code. In particular,
`FakePage` supports `set_default_timeout` and `on`; `FakeResponse.request.post_data` is present; and
fixture payloads use the live `CLASS_NAME_ONLY` and `HAS_REQ` fields. Loose mocks that accept any
attribute are forbidden at this boundary.

### Synthetic and private corpora

Committed fixtures are small, deterministic, and fully synthetic. They include deliberately leaky
values for privacy-tripwire tests, but never transformed real Scout data.

When local `raw_data/` exists, `pytest --corpus-dir raw_data` runs the complete synthetic suite and
then an extra private-corpus suite. Before use, a local manifest lock verifies every source file,
expected categories, schema versions, aggregate counts, and a tree hash. The command:

- parses every file;
- never modifies the source corpus;
- writes derived data only under a temporary or gitignored directory;
- compares normalized outputs and artifact-category counts;
- prints only redacted aggregates and diffs;
- skips clearly when the corpus is absent;
- requires an explicit manifest-update command when the corpus legitimately changes.

A local scrubber may create a convenient private derived corpus, but it is fail-closed, uses a
schema allowlist, scans all identifiers and filenames, and stages before promotion. Its output is
never committed.

### Legacy-to-new parity

Implementation-neutral contract tests run a legacy adapter and a new adapter over the same
synthetic inputs and, when enabled, the verified private corpus. Results are normalized for
injected clocks and run UUIDs. Every non-equal field must appear in a reviewed intentional-change
list. The legacy adapter is removed only after parity is green.

### Required focused coverage

- Same-named and slug-equivalent attendees remain isolated; missing upstream ID fails closed;
  resumes retain run UUIDs and independent runs do not.
- All observed `requirement_path` shapes and completion-flag pairs.
- Inference purity, duplicate handling, parent selection, and both output consumers.
- Schema drift, absent versus null, malformed containers, structural fingerprints, and circuit
  breaking.
- Retry attempt classification, exact delays under a fake clock, deadlines, cancellation, and
  `Retry-After` bounds.
- The exact seven PDF-import columns and exact external schema versions.
- Atomic write failures inside render, write, flush, fsync, and replace.
- Template placeholder validation before insertion and embedded JSON round-trip after insertion.
- FastAPI app isolation, task retention, cancellation, SSE reconnect, registry cleanup, malformed
  summaries, and worker errors.
- Source-copy launcher bridge, package contents, clean installs, release pointer switch, offline
  last-good startup, migration interruptions, split-brain detection, rollback, and capability
  reference counting.
- Redaction and diagnostic-bundle scans.

### Coverage policy

Branch coverage covers all first-party Python code from the first test phase. CI records the honest
baseline and rejects regressions. New pure core and payload-validation modules target at least 95%
branch coverage; new feature and file adapter code targets at least 90%. Platform/UI adapters may
start lower only with explicit uncovered-line justification and must rise as their test harnesses
land.

The behavior matrix, mutation/failure tests, and parity suite are correctness gates. A global
percentage never substitutes for them.

### Performance gate

Before thresholds are chosen, capture a reproducible baseline for:

- launcher and application startup;
- end-to-end synthetic and private-corpus runtime;
- ScoutingEvent request count per attendee and class;
- report generation;
- peak memory;
- output artifact sizes;
- capability download and install time;
- compressed installer size.

Request counts and algorithmic growth receive hard assertions. Wall-clock comparisons run in a
separate tolerant job on controlled runners and report trends before they become blocking. The plan
must name the baseline command, corpus, machine class, permitted variance, and regression threshold.

## Continuous integration

CI grows with the four execution phases but every introduced job is green when merged:

| Job | Purpose |
| --- | --- |
| `lint-format` | Ruff lint and format check |
| `types` | Python 3.12 mypy policy by package |
| `lock` | `uv sync --locked`; launcher export matches lock |
| `unit-contract` | Offline tests, branch coverage, synthetic fixtures, legacy/new parity |
| `local-playwright` | Local fake ScoutingEvent; no external network |
| `package` | sdist/wheel inspection and clean installation from wheel and sdist |
| `architecture` | Reverse-import and cycle checks |
| `launcher-windows` | Thin-installer size, clean-root start, release and rollback state machine |
| `launcher-macos` | Platform paths, Chrome/Chromium selection, clean-root start |
| `private-corpus` | Local developer command only; not hosted CI unless a private runner is approved |
| `live-smoke` | Manual/staging, read-only, explicitly opted in; never a required PR job |
| `performance` | Controlled, tolerant wall-time trend plus hard request-count checks |

## Execution phases and go/no-go gates

The specification owns why and behavioral contracts. The implementation plan owns file-by-file
execution order and commands. There is one plan with four phases, not several disconnected plans.

### Phase A: Tooling and complete characterization

Add packaging metadata, dependency locking, offline test enforcement, synthetic fixtures, optional
private-corpus verification, and the complete legacy behavior matrix. Production behavior is not
moved yet.

**Gate 1:** All named legacy observables pass, default tests prove external network is blocked, the
lock and package metadata are reproducible, and performance baselines are recorded.

### Phase B: Package boundaries, identity, and outputs

Introduce the `src/` package and compatibility shims incrementally. Establish the pure core,
ScoutingEvent port, attendee-session boundary, typed identity, versioned DTOs, and atomic artifact
writer. Run legacy and new adapters side by side.

**Gate 2:** Same-named attendees cannot merge or collide; missing IDs fail closed; no shareable
artifact leaks upstream identity or QR tokens; output failures preserve prior files; contract parity
is green except for reviewed intentional changes.

### Phase C: Storage, migration, and transactional releases

Resolve the installed data root, rehearse copy-only migration, add split-brain detection, create
versioned release directories, and switch releases through `current.json` with readiness and
rollback.

**Gate 3:** A throwaway copy of the live legacy layout migrates with byte hashes, interruption and
collision tests pass, old writes are detected and preserved, the original remains untouched, and a
failed release returns to the last known-good application.

### Phase D: Thin installer, capabilities, and operational hardening

Enforce the e-mail size budget, implement controlled payload downloads and caches, separate
ScoutingEvent, Chromium fallback, and PDF capabilities, finish browser selection, add local
diagnostics and telemetry stubs, and run platform and performance verification.

**Gate 4:** The installer satisfies the size budget, first install and offline restart work on
Windows and macOS, browser fallback is proven with local fixtures, optional capabilities are
isolated, diagnostics are redacted, and no default path contacts the real service.

### Plan task contract

Each plan task must have one observable outcome and include:

- symbol-based source anchors rather than brittle line numbers;
- inputs, outputs, invariants, and failure behavior;
- the RED test, implementation change, exact verification command, and expected result;
- privacy and compatibility impact;
- rollback or recovery path;
- acceptance criteria mapped one-to-one to named tests.

Mechanical movement and deliberate behavior changes are separate tasks. Each gate includes a
go/no-go checklist and stops execution when it is not satisfied.

## Acceptance criteria

The refactor is complete only when:

1. The legacy behavior matrix and new contract suite are green on fully synthetic data.
2. Local private-corpus verification, when available, runs in addition to synthetic tests and
   produces only redacted output.
3. Default tests demonstrably cannot call `scoutingevent.com`.
4. Two same-named attendees remain separate through acquisition, inference, reports, and resume.
5. Shareable artifacts and logs contain no upstream IDs or QR tokens.
6. All output writers survive injected failures without corrupting prior artifacts.
7. External schemas are versioned and compatibility-tested.
8. A clean sdist and wheel install outside the repository can run the CLI and local web app.
9. A copy of the legacy installed layout migrates without altering the source, handles collisions,
   and detects later legacy writes.
10. A bad application release or capability fails readiness and returns to the known-good version.
11. The e-mailed installer remains within the size budget and downloads immutable locked payloads
    without using PyPI at runtime.
12. Windows selects Edge, then Chrome, then downloaded Chromium; macOS selects Chrome, then
    downloaded Chromium; Safari remains an explicit experiment.
13. Local logs and diagnostic bundles are useful and redacted; telemetry remains off and no-op by
    default.
14. Performance and request-count gates show no unacceptable regression.
15. Repository architecture tests and documentation match the installed application.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Same-named attendees corrupt records | Typed upstream identity in memory; independent run UUID in outputs; fail closed on missing identity |
| Legacy and new code diverge during migration | Implementation-neutral parity suite and one plan with hard gates |
| Installed data is lost or split across roots | Explicit data root, copy-only hashed migration, originals retained, split-brain detection, manual backup |
| Upstream schema changes silently | Validated object boundary, fixture profiles, structural fingerprint, fail-closed drift policy, opt-in canary |
| Default tests leak data or hit the real site | Synthetic-only committed fixtures, `pytest-socket`, private local corpus, separate live marker |
| Output fails halfway | Render first, same-directory temp, fsync, atomic replace, completion manifest last |
| Thin installer becomes a hidden online dependency | Resumable controlled downloads, cached known-good payload, optional offline kit, offline restart tests |
| Update installs corrupt or incompatible application | Immutable versioned releases, integrity checks, readiness probe, atomic pointer, known-good rollback |
| Unsigned metadata is maliciously replaced | Accepted D23 risk for internal distribution; do not overclaim checksums; reopen signing before distribution expands |
| Playwright and browser versions drift | Version-scoped capabilities, readiness checks, remembered successful engine keyed by versions |
| Safari fails on the legacy site | Chrome is the macOS default; Safari adapter remains explicit and experimental |
| Optional PDF stack leaks into core installer | Capability package boundary and clean-core import tests |
| Architecture becomes ceremonial | Protocols only at real seams; vertical slices; merge unjustified tiny modules |
| Coverage creates false confidence | Behavior matrix, failure injection, parity, privacy scans, and request-count assertions remain separate gates |

## Decision appendix

All decisions below are locked unless a later design review explicitly supersedes one.

| ID | Decision | Consequence |
| --- | --- | --- |
| **D1** | Keep one execution plan with hard go/no-go gates. | Stop after characterization, identity/output, and migration/release rehearsal when a gate is red. |
| **D2** | Preserve the existing source-copy launcher bridge for the foundation. | Copy `src/scoutmb` into the installed app, include it in `build.spec`, and prove a clean-root launch; replace the bridge later with versioned payload installation. |
| **D3** | Treat the upstream attendee ID as sensitive typed identity and fail closed when absent. | No name-based or unresolved identity buckets. D25 defines the separate output identity. |
| **D4** | Make `uv.lock` canonical and derive the launcher's pinned, hashed requirements from it. | CI uses locked sync and fails on lock/export drift. |
| **D5** | Define migration safety for installed user data. | Stage, SHA-256 verify, preserve collisions uniquely, publish atomically, write the marker last, and never delete originals. |
| **D6** | Resolve production storage explicitly. | Constructor override, exact `SCOUTMB_DATA_DIR`, then `platformdirs`; working directory only in explicit development mode. |
| **D7** | Commit only deterministic fully synthetic fixtures. | Real corpus and any locally scrubbed derivative remain private and gitignored. |
| **D8** | Require a complete legacy behavior contract matrix before movement. | Gate 1 remains closed until all observable formats, flags, errors, delays, and output schemas are pinned. |
| **D9** | Never call `scoutingevent.com` outside an explicit integration or staging smoke test. | Suite-wide socket blocking; local fake services; separately marked, opted-in, read-only live smoke. |
| **D10** | Measure all first-party code from the start without using coverage as the correctness gate. | Honest baseline, no regression, high branch expectations for new core code, plus contract gates. |
| **D11** | Use one atomic artifact-publication contract. | Render first, unique same-directory temp, flush/fsync, `os.replace`, cleanup, and manifest last. |
| **D12** | Allow a verified private corpus to augment local tests. | `pytest --corpus-dir raw_data` always runs synthetic tests too, verifies a manifest lock, preserves originals, and emits redacted results. |
| **D13** | Compare legacy and new code through implementation-neutral adapters. | Normalize deterministic fields, review intentional changes, and remove legacy only after parity. |
| **D14** | Keep raw upstream identity and QR tokens out of shareable outputs. | Raw values remain at the upstream/private boundary; sensitive export is explicit and warned. |
| **D15** | Build a real Python distribution. | Explicit backend, sdist and wheel, archive inspection, clean install, and wheel rebuilt from sdist. |
| **D16** | Version external output schemas through dedicated DTOs. | Exact CSV order, JSON/run schema versions, current writer, supported readers, future-version rejection, and compatibility goldens. |
| **D17** | Install application releases transactionally. | Versioned immutable directories, whole-candidate staging, readiness, atomic `current.json`, known-good rollback, and version-scoped capabilities. |
| **D18** | Keep the e-mailed installer thin and move large capabilities to downloads. | Hard 18 MB attachment budget, no bundled wheelhouse/browser/PDF stack, cached controlled payloads, optional offline kit. |
| **D19** | Use hexagonal boundaries with a functional core and vertical feature slices. | Avoid Clean Architecture ceremony; construct adapters outside and pass them inward; enforce import direction. |
| **D20** | Add local diagnostics and an OpenTelemetry-shaped future seam. | No-op offline default, redacted event schema, bounded spool protocol, no OpenTelemetry import in core. |
| **D21** | Establish performance baselines before selecting time thresholds. | Hard request-count and complexity assertions; tolerant controlled wall-time job. |
| **D22** | Isolate the unowned legacy service behind an attendee-session gateway and drift detector. | Browser-backed initial adapter, validated `object` payloads, fail-closed schema policy, controlled retries, read-only canary, OS-specific browser fallback. |
| **D23** | Defer signing and notarization while use remains internal to the troop. | Keep corruption checks and integrity validation, document the authenticity gap, and revisit before broader distribution or threat-model change. |
| **D24** | Let the spec own contracts and the plan own execution order. | Rewrite the plan into four phases; each task has one observable outcome, RED test, commands, recovery, and named acceptance tests. |
| **D25** | Use a full UUIDv4 per attendee per run for output identity. | Persist it in the private run checkpoint for resume; generate an unrelated value for each independent run; no HMAC, hash, UUID prefix, or UUIDv7. |
| **D26** | Detect writes to the abandoned legacy data root after cutover. | Compare source hashes each launch, preserve changed state as a recovery snapshot, warn or block mutation, and never auto-merge or overwrite active data. |

## Open questions

None block rewriting the implementation plan. D23 is deferred, not unresolved. Suspected legacy
inference defects remain characterized behavior until separate fixes are proposed.
