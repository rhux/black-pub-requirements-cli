# Troop 349 Summer Camp Command Program

A `uv`-managed Python package (`scoutmb`) that pulls Scout merit-badge class schedules and
requirement completion off `scoutingevent.com`, in two stages:

1. **PDF extraction** (`troop349-pdf`) — pulls attendee name, registrant type, and QR-code
   contents from printed class-schedule PDFs into a `scouts.csv`.
2. **Schedule acquisition** (`troop349-schedule`) — drives a real browser to each attendee's QR
   URL to obtain a session, then pulls schedule/requirement JSON directly from the site's AJAX
   endpoint and generates CSV/JSON/HTML output.

A third entry point, **`troop349`**, launches both stages behind a local native window (or the
system browser, with `--browser`) instead of the command line.

`scoutingevent.com`'s mobile UI runs jQuery Mobile code that throws before its schedule list
finishes initializing, so the rendered page is broken. `troop349-schedule` uses a real Chromium
context only to establish the session cookie and trigger the initial schedule AJAX call, then
reads the raw JSON response directly instead of relying on the DOM.

## Setup

Requires `uv`. From the repo root:

```bash
uv sync --locked --all-extras
uv run playwright install chromium   # only needed for troop349-schedule / troop349
```

`--all-extras` pulls in both optional dependency groups: `pdf` (PyMuPDF, opencv-python-headless
— needed by `troop349-pdf`) and `acquisition` (Playwright — needed by `troop349-schedule` and
`troop349`). Installing only one extra (`uv sync --extra pdf`, say) works if you only need that
stage.

Every dependency, including PyMuPDF, opencv-python-headless, and pywebview's PyObjC frameworks,
publishes native arm64/universal2 wheels on Apple Silicon — nothing needs Rosetta or a source
build. On Windows, `troop349`'s native window needs the Microsoft Edge WebView2 Runtime (present
on any up-to-date Windows 10/11 install; the packaged installer provisions it automatically).

## Step 1: build `scouts.csv` from a PDF

```bash
uv run troop349-pdf "Class_Schedule_2026_07_06.pdf" --output scouts.csv --strict
```

By default, `Adult` and `Part-Time Adult` pages are excluded, producing a scout-only input file.
Use `--include-adults` to retain them. The extractor first decodes QR images embedded directly
in the PDF; if a PDF stores the QR as vector content or an unusual image, it falls back to
rendering the page at several resolutions (`--render-dpi`, repeatable).

The output CSV's first three columns — `Attendee Name`, `Registrant Type`, `QR Code Contents` —
are the exact contract `troop349-schedule` expects; the remaining columns (source PDF, page,
decode method) are for auditing only.

### Multiple PDFs, folders, and wildcards

```bash
uv run troop349-pdf "pdfs/*.pdf" --output scouts.csv
uv run troop349-pdf pdfs --recursive --output scouts.csv
```

### Useful PDF options

```text
--include-adults             Include adult registrations
--adult-type "Leader"        Treat another registrant type as adult/excluded
--keep-duplicates            Keep repeated QR values across PDFs
--scoutingevent-only         Exclude QR values that are not ScoutingEvent mobile URLs
--strict                     Return a failing exit code if any page is incomplete
--debug-dir qr-debug         Save rendered images for pages whose QR cannot be decoded
--render-dpi 300             Add/replace fallback render resolutions; repeat as needed
--no-normalize-obvious-case  Preserve obvious source capitalization errors such as MIles
```

`uv run troop349-pdf --help` lists every option. When extraction warnings occur, the tool
writes `<output-name>.errors.csv`.

## Step 2: download schedules and requirements

```bash
uv run troop349-schedule --input scouts.csv --output heritage-results
```

For every scout, this:

1. Opens the QR URL in an isolated Chromium browser context so the PHP session cookie is
   established.
2. Clicks the **Schedule** link and captures the `getUnitClass=true` response.
3. Reads `attendeeID` from the captured POST body.
4. POSTs `getClassRequirement=true` for every returned `classP4ID` using the same session.
5. Exports normalized CSV and JSON files while retaining raw payloads.
6. Generates a self-contained HTML report with filtering, sorting, schedules, and expandable
   requirements.

### Useful schedule options

```text
--headed                      Show Chromium while the CLI runs
--channel msedge               Use a specific Playwright browser channel
--timeout 90                  Increase the per-scout timeout
--request-delay-ms 500        Slow down requirement requests
--scout-delay-ms 750          Fixed delay between scouts (default: random 500-2000ms)
--allow-dead-assets           Let the two known mike.dev.* JavaScript requests time out normally
--include-adults              Include adult registrations
--no-html                     Skip generation of the HTML report
--html-name schedule.html     Change the HTML report filename
--email-report                Also generate per-scout missing-requirement emails
--breaker-threshold 5         Consecutive scout-fetch failures before the batch stops
```

`uv run troop349-schedule --help` lists every option. The known
`mike.dev.admin.247scouting.com` and `mike.dev.scoutingevent.com` JavaScript requests are
blocked by default because they currently time out — the JSON endpoints this tool relies on
don't depend on their rendered UI succeeding.

## Schedule output

- `report.html` — self-contained interactive report
  - filter by scout, class, block, day, location, completion status, or free text
  - view schedules grouped by scout with expandable class requirements
  - infer parent-requirement completion when all subrequirements are complete
  - mark choice requirements such as "Do TWO of the following" as **Completed, but double
    check** when enough alternatives appear complete
  - sort all-class and requirement tables by clicking column headings
- `scouts.json` — complete nested result
- `classes.csv` — one row per scheduled class
- `requirements.csv` — one row per requirement
- `errors.csv` — recoverable failures
- `summary.json` — totals
- `raw/` — unmodified schedule and requirement payloads
- `emails/` — per-scout missing-requirement emails, when `--email-report` is passed

## Verifying changes

```bash
uv run pytest -q
```

There is no `raw_data/`-backed private corpus in a fresh checkout, so the default lane
(everything except `live_service`/`playwright`/`release`, all deselected unless explicitly
requested) runs standalone. See `CLAUDE.md` for the full test/CI layout.

## Privacy

QR URLs and attendee IDs act as bearer access tokens for real scouts' data. `.gitignore`
excludes generated output directories, input files, and local data roots — keep it that way and
don't commit real PDFs, CSVs, or generated reports.
