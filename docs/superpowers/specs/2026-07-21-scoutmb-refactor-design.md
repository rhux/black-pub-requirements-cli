# ScoutMB Software Foundation Design

**Date:** 2026-07-21
**Last updated:** 2026-07-22
**Status:** Engineering decisions locked; implementation plan regenerated and verified against this revision
**Supersedes:** `docs/refactor-plan.md` and the earlier revision of this specification
**Related plan:** `docs/superpowers/plans/2026-07-21-scoutmb-foundation.md`
**Review state:** Architecture, correctness, testing, performance, migration, distribution,
runtime-safety, local-security, and lifecycle decisions D1-D36 are recorded in the decision
appendix.

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
- Treat the loopback web server, browser subprocesses, downloaded archives, and durable state as
  explicit trust boundaries rather than assuming that local execution is inherently safe.
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
11. **Deadlines use monotonic time.** Persisted timestamps use timezone-aware UTC; wall-clock
    changes cannot extend or shorten retries, timeouts, or shutdown deadlines.
12. **One process owns each mutable installed resource.** Installation, migration, release-pointer
    changes, capability cleanup, and mutating application runs use OS-backed ownership rather than
    mtime-based lock stealing.
13. **The local web application is authenticated.** Loopback binding is necessary but not treated
    as authorization; API, event-stream, upload, and private-report access require a per-launch
    session.
14. **Rollback includes durable-state compatibility.** The last-known-good executable remains able
    to read the state that a candidate release is permitted to publish.

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
- `runtime/` owns application job supervision and may import `core/`, `features/`, and ports, but
  not concrete adapters.
- `adapters/` implement ports and may import third-party frameworks.
- `interfaces/` construct dependencies at the outside and call feature services.
- CLI, web, and desktop interfaces call the same feature services and typed configuration.
- Protocols exist only at real I/O or nondeterminism seams. Internal pure functions do not get
  interface wrappers for symmetry.
- Optional PDF and telemetry packages cannot be imported by the core installation path.
- Architecture tests reject reverse imports and package cycles.
- `core/`, `features/`, and `ports/` use strict mypy settings. Adapter exceptions for incomplete
  third-party typing are narrow, documented, and cannot introduce `Any` into core models.
- Broad `except Exception` is permitted only at process, request, job, or attendee isolation
  boundaries where it is converted into a typed stable error and redacted diagnostic.
  `BaseException` is never swallowed, and cancellation is re-raised after cleanup.

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
    run_state.py
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
    time.py
    ownership.py
    observability.py
    releases.py

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

  runtime/
    jobs.py

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
       generation manifest -> atomic pointer or terminal run commit
```

### Trust model

The signed-in troop operator is trusted to start acquisitions and choose input/output locations.
ScoutMB treats all of the following as untrusted until validated: QR contents, uploaded files,
filenames, upstream pages and payloads, redirects, report data, release archives, capability
metadata, existing on-disk state, environment overrides, and requests arriving at the loopback
server. A hostile public web page is assumed able to attempt connections to loopback.

The design protects confidentiality and integrity against malformed input, cross-origin web
requests, accidental corruption, interrupted work, upstream drift, and unintended network access
from tests. It does not claim to defend against an administrator or malicious process already
running as the same operating-system user, physical disk access without full-disk encryption, or a
release host and metadata source compromised together. The last case remains the explicitly
accepted D23 authenticity gap.

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

### Sensitive-data lifecycle

The application does not claim cryptographic erasure or application-level encryption. It relies on
the signed-in operating-system account and recommends full-disk encryption, while still applying
least-privilege local storage:

- On POSIX systems, private directories are created as `0700` and private files as `0600`, subject
  to a restrictive umask. On Windows, the storage adapter applies an ACL for the current user and
  required system principals rather than assuming POSIX mode bits are effective.
- Private data, caches, logs, release state, and shareable output use separate directories. A file
  is never made shareable merely by moving or renaming a private checkpoint.
- Diagnostic bundles are generated into a new sanitized staging directory, scanned for forbidden
  values, and published only after validation.
- A user-visible data-management command and UI show the active data root, category sizes,
  retention dates, and explicit deletion actions. Deletion is best-effort filesystem deletion; the
  application does not claim secure wipe on SSDs or removal from external backups.
- A private backup command acquires the data-root ownership lock, snapshots only a validated
  generation, writes a versioned hash manifest, and clearly labels the result sensitive and not a
  diagnostic bundle. Restore runs while the application is quiescent, validates every schema and
  byte in staging, preserves the current state as a recovery generation, and then atomically
  activates the restored generation. It never merges or overwrites active state in place.

Retention defaults are:

| Data class | Default retention |
| --- | --- |
| Generated reports and user-selected shareable exports | Until explicit deletion |
| Private uploads, raw responses, checkpoints, and run working data for a terminal run | 120 days after terminal completion |
| Active, interrupted, or resumable run state | Until terminal completion or explicit reviewed deletion |
| Structured application and launcher logs | 45 days |
| Failed downloads, abandoned staging directories, and temporary files | 7 days |
| Split-brain recovery snapshots | Until explicit reviewed deletion |
| Verified private `raw_data/` corpus | Never modified or pruned by the application |

Automatic cleanup never removes active or resumable work, the current or last-known-good release,
referenced capabilities, migration evidence, user-selected exports, or recovery snapshots. Under
storage pressure, the application prunes only eligible cache and expired staging data, then warns
and refuses a new space-consuming operation instead of deleting generated reports, protected data,
or recovery state.

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

Mutable installed state must reside on a supported local filesystem with working exclusive create,
advisory locking, same-filesystem replace, and required permission semantics. Startup health probes
those behaviors inside an operation-owned temporary directory. Network shares and removable media
are unsupported for the active data root; user-selected exports may target them but receive only the
durability guarantees the destination can provide. Cloud-synchronized folders are not recommended
for active state because a sync client can violate ownership assumptions.

### Local web trust boundary

The web application binds its own socket to port `0` on `127.0.0.1` and obtains the assigned port
from the bound socket; the launcher never selects a “free” port by binding and closing a probe socket.
It does not bind to all interfaces and does not trust `localhost` DNS resolution. The launcher
creates a random per-launch bootstrap token with at least 128 bits of CSPRNG entropy, passes it to
the child without command-line exposure, and opens the UI with the token in the URL fragment rather
than the query string. The static bootstrap page exchanges the token once for an in-memory session
and removes the fragment from browser history.

The server then issues a process-lifetime session cookie with `HttpOnly`, `SameSite=Strict`, and a
restricted path. A separate same-origin CSRF value is required in a custom header for every
state-changing request. API, SSE, upload, private-report, and data-management routes require the
session. The server validates the exact `Host` and expected loopback `Origin`, sends no permissive
CORS headers, never places tokens in logs, and invalidates every session when the process exits.
The launcher-only readiness nonce is separate from this user session and cannot authorize API use.
Error responses contain a stable code and redacted user-facing text; raw exception strings,
filenames, URLs, tokens, and tracebacks are never returned to browser JavaScript.

Uploads are treated as untrusted input:

- Request count, compressed bytes, expanded bytes, PDF pages, image dimensions, parse time, worker
  memory, and concurrent parses have versioned configurable limits with conservative release
  defaults established from the synthetic and private corpora.
- Files are streamed into a private staging directory under generated names. The original basename
  is display-only, length-limited, and never used as a storage path.
- Extension, content signature, parser result, containment, and regular-file status are validated;
  symlinks, hard links, devices, FIFOs, reparse points, and path traversal are rejected.
- A failure cleans only operation-owned staging paths. It never iterates a shared directory and
  unlinks unknown entries.
- Generated reports use a restrictive Content Security Policy and contain no remote scripts,
  styles, fonts, images, frames, or other network resources.

Tests attempt cross-origin form submissions, forged `Host` and `Origin` headers, missing and stale
sessions, CSRF bypass, oversized and truncated files, duplicate names, malicious paths, parser
timeouts, and symlink/reparse-point replacement.

### Determinism, clocks, and structured concurrency

Inject only the collaborators a feature actually needs:

| Concern | Port or callable |
| --- | --- |
| Persisted timestamps | `WallClock` returning timezone-aware UTC |
| Durations and deadlines | `MonotonicClock` or the running event loop's monotonic clock |
| Run and operation IDs | `IdFactory` |
| Retry jitter | `RandomSource` |
| Waiting | `Sleeper` |
| Progress | `ProgressSink` |

There is no generic service bag. Output ordering, filenames, timestamps, random jitter, and
serialization are controlled in tests.

Wall-clock values are never used for elapsed-time comparisons. Total deadlines use one monotonic
absolute deadline that is passed inward; nested retries and `Retry-After` handling consume that
same budget rather than starting new independent timers.

All background work has an owner:

- The FastAPI lifespan owns a `JobSupervisor`; request handlers register work with it instead of
  creating unreferenced tasks.
- A job may use `asyncio.TaskGroup` for related child operations. The supervisor keeps a strong
  reference to every job until it is awaited and removed.
- Cancellation runs cleanup in `try/finally`, closes browser contexts and files, terminates owned
  child processes, and re-raises `CancelledError` after cleanup.
- Blocking PDF and image work uses a bounded executor or worker process with cooperative
  cancellation and a hard shutdown deadline. New work is rejected while shutdown is in progress.
- Concurrency limits are explicit for jobs, attendees, browser contexts, PDF workers, and file
  publication. No unbounded task, thread, process, or queue creation is permitted.

### Run state machine

Durable runs use a versioned state machine rather than independent `busy` flags:

```text
pending -> running <-> paused
              |
              +-> cancelling -> cancelled
              +-> partial
              +-> succeeded
              +-> failed
```

Only acquisition may enter `paused`. `partial` means at least one attendee completed and at least
one failed; it is a terminal state with an explicit error summary. `succeeded`, `partial`,
`cancelled`, and `failed` are terminal. Unknown states and illegal transitions fail closed.

Every transition is atomically persisted with a monotonic sequence number, state-schema version,
application version, run UUID, timestamps, and the input and effective-configuration fingerprints.
Only `succeeded` and `partial` may publish a completion manifest. Cancellation preserves a private
resume checkpoint but never publishes a successful completion manifest.

For `succeeded` or `partial`, the output generation is rendered and validated first. The terminal
state record is the run commit record and contains the output generation ID and manifest hash. If
that state transition fails, the generation is an unreferenced recoverable artifact rather than a
falsely completed run; later ownership-protected cleanup may quarantine it.

At shutdown the supervisor stops accepting work, requests cancellation, checkpoints at safe
boundaries, closes browser contexts, waits for a bounded grace period, and force-terminates only
child processes it owns. On restart, `running`, `paused`, or `cancelling` is recovered as
`interrupted`; it may resume only when its checkpoint schema and fingerprints are compatible.

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

The QR entry URL is parsed at the adapter boundary into a sensitive `ScoutingEventEntryUrl`; core
and interface code do not carry a general-purpose URL string. Production accepts only HTTPS, the
configured exact host and port, known entry-path shapes, bounded length, and the token-bearing
components required by the legacy workflow. It rejects userinfo, fragments, local or private
addresses, alternate ports, look-alike hosts, and redirects outside the adapter's versioned origin
allowlist. Test construction replaces that allowlist with the exact loopback fake origin.

The production browser context also limits requests to the first-party origin and any separately
documented static-asset origins actually required by the legacy page. New origins fail closed with
a redacted drift diagnostic; they are not learned automatically. This prevents a changed page from
sending QR credentials or attendee data to an unexpected endpoint.

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
3. Open it with exclusive creation, write, flush, `fsync`, and close it. In particular, do not
   depend on reopening a still-open named temporary file on Windows.
4. Atomically publish with `os.replace` and synchronize the parent directory where the platform
   supports it.
5. Clean only the operation-owned temporary file on every failure path.

Failure injection covers rendering, write, flush, file fsync, close, replace, and directory fsync
from inside the writer. A failed operation leaves the prior artifact byte-for-byte intact or, when
the platform reports a post-replace directory-fsync failure, reports an indeterminate durability
result without overwriting a second time.

A replaceable multi-file bundle uses immutable generations rather than replacing files underneath
an older manifest:

```text
<bundle-root>/
  generations/
    <generation-id>/
      <artifacts>
      manifest.json
  current.json
```

All artifacts are written into a unique generation directory. Its versioned manifest records the
generation ID, schema versions, relative path, byte size, and SHA-256 for every file and is written
last. After re-reading and validating the complete generation, the writer atomically replaces
`current.json`. Consumers resolve the pointer once, validate the named manifest and all referenced
paths, and read only that immutable generation. A missing, malformed, future-version, escaping, or
hash-mismatched generation is incomplete and never blended with another generation.

Unique one-shot run directories may omit `current.json`, but still publish their completion
manifest last and must not reuse an existing run directory. Garbage collection never removes a
generation referenced by a current reader lease, the active pointer, recovery state, or a retained
known-good application. Failure injection covers every artifact, manifest, and pointer boundary.

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

### Cross-process ownership

Installation, installed-data migration, release-pointer changes, capability reference updates,
cache pruning, and mutable run publication require named OS-backed locks held for the complete
critical section. A lock is released by the operating system when its owning process exits. A
small metadata file may record owner PID, process start identity, operation ID, application version,
and start time for diagnostics, but elapsed time or mtime alone never authorizes stealing a live
lock.

The lock order is fixed: installation/update, then migration/data-root, then application run, then
artifact generation. Code may acquire only from left to right and releases in reverse order.
Timeouts use monotonic time. A process that cannot acquire ownership reports the current operation
and takes no mutating action.

Second-launch behavior is:

- A desktop launch discovers the authenticated rendezvous information for the existing same-user
  instance, asks that instance to activate and bring its existing window to the foreground, and
  exits. The second launcher never creates another application process or local server.
- Foreground activation is best effort because Windows and macOS may refuse forced focus. If the
  operating system refuses, the existing instance requests user attention and exposes its existing
  window through the platform-supported mechanism. The second launcher still exits and reports
  that ScoutMB is already running; it never falls back to a duplicate instance.
- If the OS lock proves an instance exists but its rendezvous endpoint cannot be reached, the second
  launcher reports that the existing instance is unresponsive and exits. It does not delete the
  lock, kill the instance, or start another copy.
- Read-only CLI commands may run concurrently against a validated immutable snapshot. A mutating
  CLI command must acquire the corresponding ownership lock or fail with a stable `busy` code.
- A stale rendezvous file without a live OS lock is quarantined and rebuilt. PID reuse alone is not
  proof that an instance is alive.

Multi-process tests cover two simultaneous launchers, a deliberately slow installation, process
crash, PID reuse metadata, an abandoned rendezvous file, antivirus-delayed filesystem operations,
and concurrent read-only versus mutating commands.

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

### Durable internal-state compatibility

External output schema versions do not cover private operational state. Each checkpoint, run-state
record, release pointer, last-known-good pointer, capability reference set, migration marker,
retention record, and instance rendezvous file has its own `schema_version` and checksum. Readers
declare an inclusive supported range; writers emit only their current version and reject unknown
future versions.

The current and last-known-good releases must share at least one readable durable-state version.
State evolution uses expand/contract rules for that compatibility window. When an irreversible
conversion is unavoidable, the candidate writes a new immutable state generation and atomically
switches a versioned pointer; it does not rewrite the old generation in place. The old generation
and reader-compatible capability references remain until that release is no longer the retained
known-good release.

A candidate release may not publish an incompatible state generation before readiness and launch
acknowledgement. Rollback validates the retained activation tuple and atomically restores its single
`current.json` pointer to the executable, state generation, and capability set. If compatible
rollback is impossible, the update is rejected before activation; the launcher never starts an
older release against state it cannot read.

Checkpoint resume additionally requires matching input and effective-configuration fingerprints.
A mismatch offers a new run and preserves the old checkpoint for explicit recovery rather than
silently continuing with different semantics. Compatibility tests write every durable state type
with release N, exercise N+1, then roll back to N and verify byte-preserving recovery.

## Packaging, installation, and updates

### Python project and lock contract

- Use an explicit PEP 517 backend, initially Hatchling.
- `uv.lock` is the canonical dependency resolution and is committed.
- Development tools live in `[dependency-groups].dev`.
- Distributable runtime capabilities use `[project.optional-dependencies]` or their own explicit
  distribution metadata. Development dependency groups are never used as runtime feature flags.
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

`project.version` in `pyproject.toml` is the one authoritative application version. Release and
bootstrap manifests receive that value through generated build metadata; source files do not carry
independently editable version strings.

### Dependency and supply-chain maintenance

Signing remains deferred under D23, but dependency hygiene is independent of publisher
authenticity. Every controlled release:

- scans the exact locked runtime and launcher dependency sets against a maintained vulnerability
  database and fails on an unexpired unapproved finding;
- produces a machine-readable SBOM for the core and each platform capability payload;
- records package name, version, source, hash, license expression, and platform tag;
- checks licenses against a documented allow/deny/review policy;
- builds from a clean checkout with locked dependencies and without undeclared local sources;
- stores the lock digest, SBOM digest, build-tool versions, and source commit in release metadata;
- performs an archive-content and secret scan before publication.

SBOMs and build evidence live with release records; they are not bundled into the e-mailed thin
installer unless needed at runtime.

Exceptions name an owner, justification, compensating control, and expiry date. Dependency updates
are reviewed at least monthly and immediately when a relevant actively exploited vulnerability is
identified. This contract does not call the resulting artifacts signed or authentic.

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

Each capability manifest declares `capability_schema_version`, capability name and version,
application-version range, Python ABI, operating system, architecture, dependency-lock digest,
required companion capabilities, compressed and expanded sizes, entry count, and every artifact
hash. Resolution happens before download. An incompatible capability is not downloaded, enabled,
or used as a fallback.

Capability enablement is an atomic reference update. Removal is reference-counted and cannot delete
anything required by the current release, retained known-good release, an active run, or an offline
rollback. The UI distinguishes unavailable, downloading, staged, ready, incompatible, corrupt, and
disabled states and always provides a core-only recovery path.

### Supported platform matrix

The initial platform matrix is:

| Platform | Version | Architecture | Support level |
| --- | --- | --- | --- |
| Windows | Windows 11 | x86-64 | Supported |
| macOS | macOS 14 or newer | Apple silicon (`arm64`) | Supported |
| Windows | Windows 10 22H2 | x86-64 | Best-effort compatibility when the Windows 11 x64 payload works without a separate payload or material platform-specific code |
| Windows | Any | ARM64 | Unsupported initially |
| macOS | Any | Intel (`x86_64`) | Unsupported initially |

The release manifest and launcher enforce this matrix before download. “Supported” means the core,
system-browser path, downloaded-browser fallback, migration, update, rollback, and enabled optional
capabilities pass on that platform. CI jobs and manual release evidence identify exact OS builds;
an untested platform is not silently treated as supported. Windows 10 compatibility is non-blocking:
it may reuse the Windows x64 payload and receive a troop-device smoke test, but it does not justify
a separate dependency graph, installer, capability payload, substantial workaround, or delayed
security update. A compatibility failure produces a clear unsupported-platform result without
blocking the supported Windows 11 release. This is application compatibility only and does not
claim that an out-of-support Windows installation is secure or vendor-supported. The matrix is
reviewed whenever Python, Playwright, browser, or operating-system vendor support changes.

### Transactional application releases

```text
releases/
  <version>/                 immutable application environment
capabilities/
  browser/<version>/         version-scoped fallback browser
  pdf/<version>/             version-scoped optional feature
state/
  current.json               atomic activation tuple: release, state generation, capabilities
  last-known-good.json        prior acknowledged activation tuple
  generations/<id>/           immutable versioned internal state
  capability-references.json  checksummed reference inventory; not an activation pointer
cache/
data/                        user data, never inside a release
logs/
```

No symlink is required. `current.json` is a small checksummed activation manifest written through
the atomic file primitive. One replacement chooses the application release, compatible internal
state generation, and exact capability set together, so rollback cannot expose a new state format
to an old executable. Release installation is:

1. Download into a unique staging directory.
2. Verify names, compressed sizes, SHA-256, archive metadata, capability compatibility, and available
   disk space before extraction.
3. Inspect every archive member before writing: reject absolute and parent-traversal paths,
   symlinks, hard links, devices, FIFOs, reparse points, encrypted or unsupported members, duplicate
   normalized paths, case-colliding paths, excessive entry counts, and any declared-versus-actual
   size mismatch.
4. Extract member-by-member into a newly created operation-owned staging directory while enforcing
   per-entry, total-expanded-byte, entry-count, path-length, and compression-ratio limits. Never use
   an unchecked bulk `extractall` operation.
5. Re-hash the extracted tree and compare it with the manifest.
6. Construct a new versioned environment; never mutate the live release.
7. Run core health, durable-state compatibility, and capability readiness checks.
8. Atomically replace `current.json` under the update lock.
9. Retain the previous acknowledged release, compatible state generation, and referenced
   capabilities.
10. Roll back by atomically restoring the complete last-known-good activation tuple if readiness or
    subsequent launch acknowledgement fails.

Capability artifacts are version-scoped and reference-counted. A new Playwright version cannot
silently replace the fallback browser required by the known-good release.

Every download advertises exact compressed and expanded sizes. Preflight requires enough space for
the download, complete staging expansion, rollback retention, and an additional safety reserve.
Cache cleanup removes only unreferenced least-recently-used immutable payloads under the ownership
lock. Disk-full injection covers download, extraction, environment construction, state migration,
artifact publication, pointer replacement, logging, and cleanup; protected data is never deleted to
make an operation appear successful.

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
| Installer | First install, clean-root launch, offline launch, ownership contention, interrupted downloads, hostile archives, disk full, durable-state rollback, capability selection |
| Local web boundary | Session bootstrap, Host/Origin/CSRF checks, SSE authorization, upload limits, generated filenames, parser exhaustion, report CSP |
| Run lifecycle | Legal transitions, pause/resume, partial success, cancellation, shutdown, interruption recovery, incompatible checkpoint |

Gate 1 stays closed until the matrix passes against the legacy implementation.

### Network policy

The installed application may contact the configured ScoutingEvent origin only when a user
explicitly starts the online acquisition workflow. Automated tests, development verification
commands, pre-commit hooks, packaging checks, and ordinary CI never contact the real service.

The test guarantee is defense in depth:

1. `pytest-socket --disable-socket` applies suite-wide and blocks Python socket calls. Loopback is
   enabled only for a test that names its local fake hosts.
2. Application construction receives a `NetworkPolicy`. Test mode denies every non-loopback origin
   before selecting or invoking a production transport. Fakes are injected; tests do not monkeypatch
   only a low-level HTTP call while leaving the real gateway constructible.
3. Every Playwright test context sets `service_workers="block"`, installs context-wide routing before
   the first page is created, records every request, permits only the exact fake origin, and aborts
   everything else. Popups and child frames remain inside that guarded context.
4. Browser tests launch with background networking disabled and run in a deny-by-default egress
   sandbox or runner firewall in CI. The browser subprocess cannot bypass the Python socket guard.
5. A sentinel test deliberately requests an external HTTPS URL from page JavaScript, a popup, a
   child frame, and a worker; all attempts must be blocked and recorded. The job asserts zero
   non-loopback connections, not merely zero successful responses.

The live adapter cannot be selected in a test process unless the test has the `live_scoutevent`
marker, the operator supplies a separate explicit opt-in, approved read-only credentials are
present, and the configured origin exactly matches the live allowlist. Removing any one gate makes
construction fail before browser launch.

Live service checks use a separate marker and staging job with all of these controls:

- explicit operator opt-in;
- a safe test account or approved test record;
- read-only operations only;
- low frequency and rate limit;
- no execution in normal local or pull-request CI;
- redacted retained diagnostics.

Tests also prove that similarly named hosts, redirects away from the allowlist, alternate ports,
DNS rebinding, WebSockets, service workers, and direct IP addresses do not bypass the policy.

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
  `Retry-After` bounds, including wall-clock jumps that do not affect monotonic deadlines.
- The exact seven PDF-import columns and exact external schema versions.
- Atomic write failures inside render, write, flush, file fsync, close, replace, directory fsync,
  generation-manifest publication, and pointer replacement.
- Template placeholder validation before insertion and embedded JSON round-trip after insertion.
- FastAPI app isolation, authenticated loopback sessions, Host/Origin/CSRF rejection, bounded upload
  handling, task ownership, structured cancellation, SSE reconnect, registry cleanup, malformed
  summaries, and worker errors.
- Every legal and illegal run-state transition, partial success, process shutdown, browser and PDF
  child cleanup, incompatible resume, and interrupted-run recovery.
- Source-copy launcher bridge, package contents, clean installs, release pointer switch, offline
  last-good startup, multi-process ownership, migration interruptions, split-brain detection,
  N-to-N+1-to-N durable-state rollback, hostile archives, disk exhaustion, capability compatibility,
  reference counting, second-launch foreground activation, OS-denied-focus fallback, and
  unresponsive-instance handling.
- Retention, permissions/ACLs, protected-data pruning rules, redaction, deletion, private backup and
  staged restore, and diagnostic-bundle scans.
- Browser-subprocess egress attempts through page JavaScript, redirects, popup, frame, worker,
  WebSocket, alternate port, direct IP, and similarly named host.
- SBOM contents, vulnerability and license policy, clean locked build, secret scan, authoritative
  version, and release-metadata digests.

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
- upload streaming memory, PDF page/image processing, archive expansion, shutdown grace, retention
  cleanup, and peak installed disk footprint including rollback reserve.

Request counts and algorithmic growth receive hard assertions. Wall-clock comparisons run in a
separate tolerant job on controlled runners and report trends before they become blocking. The plan
must name the baseline command, corpus, machine class, permitted variance, and regression threshold.

The plan also records exact release defaults for upload count and bytes, PDF pages and image
dimensions, parse time and memory, archive entry and expanded-byte limits, concurrent jobs/workers,
queue depth, shutdown grace, cache budget, and disk safety reserve. Final acceptance cannot complete
with unbounded values or placeholders. Limits derive from measured synthetic and private-corpus needs
plus documented headroom and are independently configurable only within a tested safe range.

## Continuous integration

CI grows with the four execution phases but every introduced job is green when merged:

| Job | Purpose |
| --- | --- |
| `lint-format` | Ruff lint and format check |
| `types` | Python 3.12 mypy policy by package |
| `lock` | `uv sync --locked`; launcher export matches lock |
| `supply-chain` | Locked vulnerability scan, license policy, SBOM, clean-build and release-metadata checks |
| `unit-contract` | Offline tests, branch coverage, synthetic fixtures, legacy/new parity |
| `local-playwright` | Local fake ScoutingEvent; route guard, blocked service workers, external-request sentinels |
| `egress-denied` | Playwright/browser job inside a deny-by-default network sandbox; zero non-loopback connections |
| `local-web-security` | Session, Host/Origin/CSRF, upload limits, containment, parser budgets, and report CSP |
| `package` | sdist/wheel inspection and clean installation from wheel and sdist |
| `architecture` | Reverse-import and cycle checks |
| `launcher-windows` | Supported Windows matrix, thin-installer size, ownership, hostile archives, clean-root start, durable-state rollback |
| `launcher-macos` | Supported macOS matrix, ACL/path behavior, ownership, Chrome/Chromium selection, clean-root start, durable-state rollback |
| `private-corpus` | Local developer command only; not hosted CI unless a private runner is approved |
| `live-smoke` | Manual/staging, read-only, explicitly opted in; never a required PR job |
| `performance` | Controlled, tolerant wall-time trend plus hard request-count checks |

## Execution phases and go/no-go gates

The specification owns why and behavioral contracts. The implementation plan owns file-by-file
execution order and commands. There is one plan with four phases and three blocking go/no-go gates,
not several disconnected plans.

### Phase A: Tooling and complete characterization

Add packaging metadata, dependency locking, offline test enforcement, synthetic fixtures, optional
private-corpus verification, supply-chain checks, supported-platform metadata, and the complete
legacy behavior matrix. The offline harness includes Python socket blocking, application network
policy, guarded Playwright contexts, external-request sentinels, and the egress-denied CI job.
Production behavior is not moved yet.

**Gate 1:** All named legacy observables pass, default tests prove external network is blocked, the
lock and package metadata are reproducible, SBOM and dependency policies pass, platform assumptions
are explicit, and performance baselines are recorded.

### Phase B: Package boundaries, identity, and outputs

Introduce the `src/` package and compatibility shims incrementally. Establish the pure core,
ScoutingEvent port, attendee-session boundary, typed identity, versioned DTOs, and atomic artifact
writer. Add separate wall and monotonic clocks, the durable run-state machine, lifespan-owned job
supervision, and the authenticated local-web boundary. Run legacy and new adapters side by side.

**Gate 2:** Same-named attendees cannot merge or collide; missing IDs fail closed; no shareable
artifact leaks upstream identity or QR tokens; output failures preserve prior files; contract parity
is green except for reviewed intentional changes; illegal run transitions fail closed; cancellation
owns and closes all child resources; cross-origin and unauthenticated local requests are rejected.

### Phase C: Storage, migration, and transactional releases

Resolve the installed data root, rehearse copy-only migration, add split-brain detection, create
versioned release directories, and switch releases through `current.json` with readiness and
rollback. Add OS-backed ownership, data permissions and retention, versioned internal state,
generation-based multi-file publication, private backup/staged restore, cache protection, and
executable-plus-state rollback.

**Gate 3:** A throwaway copy of the live legacy layout migrates with byte hashes, interruption and
collision tests pass, old writes are detected and preserved, the original remains untouched, and a
failed release returns to the last-known-good application and a state generation it can read.
Simultaneous launchers and disk-full failures cannot corrupt, steal, or delete protected data.

### Phase D: Thin installer, capabilities, and operational hardening

Enforce the e-mail size budget, implement controlled payload downloads and caches, separate
ScoutingEvent, Chromium fallback, and PDF capabilities, finish browser selection, add local
diagnostics and telemetry stubs, enforce archive and capability compatibility limits, and run the
supported-platform, resource-exhaustion, and performance verification.

**Final acceptance:** After all three earlier gates are green, the installer satisfies the size
budget, first install and offline restart work on Windows and macOS, browser fallback is proven with
local fixtures, optional capabilities are isolated and version-compatible, hostile archives and
oversized uploads fail safely, diagnostics are redacted, retention is enforceable, and no automated
default path contacts the real service. This is the completion criterion for Phase D, not a fourth
go/no-go gate.

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
3. Default tests demonstrably cannot call `scoutingevent.com`: Python sockets, application gateway
   construction, Playwright requests, browser subprocess egress, redirects, workers, frames,
   popups, and WebSockets are all covered.
4. Two same-named attendees remain separate through acquisition, inference, reports, and resume.
5. Shareable artifacts and logs contain no upstream IDs or QR tokens.
6. All output writers survive injected failures without corrupting prior artifacts or mixing
   generations; consumers validate the manifest and hashes before reading a bundle.
7. External schemas are versioned and compatibility-tested.
8. A clean sdist and wheel install outside the repository can run the CLI and local web app.
9. A copy of the legacy installed layout migrates without altering the source, handles collisions,
   and detects later legacy writes.
10. A bad application release or capability fails readiness and returns to the known-good
    executable and a compatible durable-state generation after N-to-N+1-to-N testing.
11. The e-mailed installer remains within the size budget and downloads immutable locked payloads
    without using PyPI at runtime.
12. Windows selects Edge, then Chrome, then downloaded Chromium; macOS selects Chrome, then
    downloaded Chromium; Safari remains an explicit experiment.
13. Local logs and diagnostic bundles are useful and redacted; telemetry remains off and no-op by
    default.
14. Performance and request-count gates show no unacceptable regression.
15. Repository architecture tests and documentation match the installed application.
16. Two simultaneous launchers cannot mutate the installation concurrently; a second desktop
    launch starts no duplicate app or server, requests foreground activation or user attention from
    the existing instance, and exits. Mutating CLI commands return a stable busy result.
17. Every run follows the versioned state machine; shutdown, cancellation, interruption, partial
    success, and resume close or recover all owned resources without a false completion manifest.
18. The local server binds only to `127.0.0.1`, authenticates API/SSE/private-report access, rejects
    forged Host/Origin/CSRF requests, and applies bounded streamed upload handling.
19. Private directories and files have platform-appropriate current-user permissions; retention,
    protected-data rules, explicit deletion, private backup/staged restore, and disk-pressure
    behavior pass on supported systems.
20. Hostile or oversized archives, case collisions, links, traversal, unsupported members, and
    expanded-size exhaustion are rejected before activation without modifying a live release.
21. Capability manifests enforce application, Python ABI, OS, architecture, dependency-lock, and
    companion-capability compatibility before download and enablement.
22. The supported platform matrix is enforced by the launcher and proven by exact CI or release
    evidence; unsupported architectures fail before downloading a payload.
23. Every release produces passing vulnerability and license checks, per-payload SBOMs, clean locked
    build evidence, secret-scan results, and metadata tied to the authoritative application version.
24. Wall-clock jumps do not affect retry, timeout, ownership, or shutdown deadlines; durable
    timestamps are timezone-aware UTC.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Same-named attendees corrupt records | Typed upstream identity in memory; independent run UUID in outputs; fail closed on missing identity |
| Legacy and new code diverge during migration | Implementation-neutral parity suite and one plan with hard gates |
| Installed data is lost or split across roots | Explicit data root, copy-only hashed migration, originals retained, split-brain detection, manual backup |
| Upstream schema changes silently | Validated object boundary, fixture profiles, structural fingerprint, fail-closed drift policy, opt-in canary |
| Default tests or browser subprocesses leak data or hit the real site | Synthetic-only fixtures, Python socket guard, injected network policy, guarded browser contexts, egress-denied CI, multi-gate live smoke |
| Output fails halfway or readers mix generations | Render first, same-directory temp, fsync, immutable generation, hashed manifest, atomic pointer |
| Thin installer becomes a hidden online dependency | Resumable controlled downloads, cached known-good payload, optional offline kit, offline restart tests |
| Update installs corrupt code or state the old release cannot read | Immutable code and state generations, compatibility window, hostile-archive checks, readiness, atomic pointers, N-to-N+1-to-N rollback |
| Unsigned metadata is maliciously replaced | Accepted D23 risk for internal distribution; do not overclaim checksums; reopen signing before distribution expands |
| Playwright and browser versions drift | Version-scoped capabilities, readiness checks, remembered successful engine keyed by versions |
| Safari fails on the legacy site | Chrome is the macOS default; Safari adapter remains explicit and experimental |
| Optional PDF stack leaks into core installer | Capability package boundary and clean-core import tests |
| Architecture becomes ceremonial | Protocols only at real seams; vertical slices; merge unjustified tiny modules |
| Coverage creates false confidence | Behavior matrix, failure injection, parity, privacy scans, and request-count assertions remain separate gates |
| A slow process loses an mtime lock to another launcher | OS-backed process-held locks, fixed lock order, diagnostic metadata only, multi-process crash and delay tests |
| A hostile website drives the loopback application | Per-launch authenticated session, exact Host/Origin, CSRF protection, no permissive CORS, private-route authorization |
| Malformed or oversized PDF/archive exhausts resources or escapes staging | Streamed generated-name upload, containment checks, parser budgets, member-by-member extraction, expanded-size and entry limits |
| Private Scout data accumulates indefinitely or becomes broadly readable | Current-user permissions/ACLs, category retention, protected-data rules, explicit deletion, bounded logs and staging |
| Background jobs disappear or survive shutdown incorrectly | Lifespan-owned supervisor, strong task references, structured cancellation, bounded children and durable run states |
| Wall-clock change corrupts deadline behavior | Separate UTC wall clock and monotonic deadline source; injected clock-jump tests |
| Vulnerable or disallowed dependency ships unnoticed | Exact-lock vulnerability and license policy, SBOM per payload, exception expiry, monthly maintenance |

## Decision appendix

Decisions below are locked unless a later design review explicitly supersedes one.

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
| **D9** | Automated tests and verification never call `scoutingevent.com` outside an explicit integration or staging smoke test. | Python socket blocking, injected deny policy, guarded Playwright contexts, browser-process egress denial, sentinel attempts, and separately marked opted-in read-only live smoke. The installed user-initiated acquisition workflow remains the intended production call path. |
| **D10** | Measure all first-party code from the start without using coverage as the correctness gate. | Honest baseline, no regression, high branch expectations for new core code, plus contract gates. |
| **D11** | Use one atomic artifact-publication contract. | Render first, exclusive same-directory temp, flush/fsync/close, `os.replace`, parent synchronization, cleanup, and immutable generations with hashed manifest and atomic pointer for replaceable bundles. |
| **D12** | Allow a verified private corpus to augment local tests. | `pytest --corpus-dir raw_data` always runs synthetic tests too, verifies a manifest lock, preserves originals, and emits redacted results. |
| **D13** | Compare legacy and new code through implementation-neutral adapters. | Normalize deterministic fields, review intentional changes, and remove legacy only after parity. |
| **D14** | Keep raw upstream identity and QR tokens out of shareable outputs. | Raw values remain at the upstream/private boundary; sensitive export is explicit and warned. |
| **D15** | Build a real Python distribution. | Explicit backend, sdist and wheel, archive inspection, clean install, and wheel rebuilt from sdist. |
| **D16** | Version external output schemas through dedicated DTOs. | Exact CSV order, JSON/run schema versions, current writer, supported readers, future-version rejection, and compatibility goldens. |
| **D17** | Install application releases transactionally. | Versioned immutable code and state generations, whole-candidate staging, compatibility/readiness, atomic pointers, known-good executable-plus-state rollback, and version-scoped capabilities. |
| **D18** | Keep the e-mailed installer thin and move large capabilities to downloads. | Hard 18 MB attachment budget, no bundled wheelhouse/browser/PDF stack, cached controlled payloads, optional offline kit. |
| **D19** | Use hexagonal boundaries with a functional core and vertical feature slices. | Avoid Clean Architecture ceremony; construct adapters outside and pass them inward; enforce import direction. |
| **D20** | Add local diagnostics and an OpenTelemetry-shaped future seam. | No-op offline default, redacted event schema, bounded spool protocol, no OpenTelemetry import in core. |
| **D21** | Establish performance baselines before selecting time thresholds. | Hard request-count and complexity assertions; tolerant controlled wall-time job. |
| **D22** | Isolate the unowned legacy service behind an attendee-session gateway and drift detector. | Browser-backed initial adapter, validated `object` payloads, fail-closed schema policy, controlled retries, read-only canary, OS-specific browser fallback. |
| **D23** | Defer signing and notarization while use remains internal to the troop. | Keep corruption checks and integrity validation, document the authenticity gap, and revisit before broader distribution or threat-model change. |
| **D24** | Let the spec own contracts and the plan own execution order. | Rewrite the plan into four phases; each task has one observable outcome, RED test, commands, recovery, and named acceptance tests. |
| **D25** | Use a full UUIDv4 per attendee per run for output identity. | Persist it in the private run checkpoint for resume; generate an unrelated value for each independent run; no HMAC, hash, UUID prefix, or UUIDv7. |
| **D26** | Detect writes to the abandoned legacy data root after cutover. | Compare source hashes each launch, preserve changed state as a recovery snapshot, warn or block mutation, and never auto-merge or overwrite active data. |
| **D27** | Enforce the offline-test guarantee across Python and browser process boundaries. | A Playwright browser is not protected by `pytest-socket`; use application policy, context routing with service workers blocked, hostile-request sentinels, and deny-by-default CI egress. |
| **D28** | Version every durable internal state and make rollback data-compatible. | Maintain an N/N-1 read window or immutable state generations; reject activation when the retained release could not recover; test N-to-N+1-to-N after every state type is written. |
| **D29** | Use OS-backed ownership and single-instance desktop behavior. | Never steal a live lock by age; fixed lock order and stable busy errors. A second desktop launch requests foreground activation of the existing instance and exits without starting another app or server; OS-denied focus requests attention instead. Compatible read-only CLI commands may coexist. |
| **D30** | Treat the loopback FastAPI server and file uploads as security boundaries. | Per-launch authenticated session, exact Host/Origin, CSRF defense, no permissive CORS, private-route authorization, streamed generated-name uploads, containment and resource limits, report CSP. |
| **D31** | Apply explicit sensitive-data permissions, retention, and deletion. | Current-user ACLs/modes, category-aware cleanup, protected resumable artifacts, visible storage management, no secure-wipe claim. Retain terminal private-run data for 120 days, logs for 45 days, and staging for 7 days; keep resumable work until completion or explicit deletion and keep recovery snapshots and generated reports until explicit deletion. |
| **D32** | Separate UTC wall time from monotonic deadlines and require owned structured concurrency. | Clock changes cannot affect deadlines; the lifespan supervisor retains and awaits work, child tasks/resources are bounded, and cancellation cleans then propagates. |
| **D33** | Persist a versioned run-state machine. | Legal transitions, partial success, publication eligibility, shutdown, interruption, resume compatibility, and recovery are explicit and testable instead of spread across `busy` flags. |
| **D34** | Enforce a release-level platform and capability compatibility matrix. | Manifests bind app version, Python ABI, OS, architecture, lock digest, and companion capabilities. Support Windows 11 x64 and macOS 14+ Apple silicon; allow non-blocking Windows 10 x64 compatibility only when the same payload works with little overhead. |
| **D35** | Bound archive extraction, downloads, disk use, and parser resources. | Inspect members before extraction, reject links/traversal/collisions, enforce expanded-size and worker budgets, preflight disk, prune only unreferenced cache, and fail safely under exhaustion. |
| **D36** | Add supply-chain maintenance without reopening D23. | Exact-lock vulnerability and license policy, per-payload SBOMs, clean builds, secret scans, authoritative version, release metadata, exception expiry, and monthly updates do not imply signing. |

## Open questions

None block regenerating the implementation plan. D23 remains deferred, not unresolved. Suspected
legacy inference defects remain characterized behavior until separate fixes are proposed.
