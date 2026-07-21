# ScoutingEvent Schedule CLI

This package contains two Python command-line utilities:

1. **`pdf_to_scouts.py`** extracts attendee names, registrant types, and QR-code contents from class-schedule PDFs and creates the input CSV.
2. **`scout_schedule_cli.py`** uses those QR URLs to download schedules and class requirements and generate CSV, JSON, raw payloads, and an interactive HTML report.

The ScoutingEvent site currently returns valid JSON but can fail while rendering it because its jQuery Mobile code calls `listview("refresh")` before the list has initialized. The schedule CLI bypasses the broken renderer and reads the JSON responses directly.

## Install on Windows

From PowerShell in this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Install on macOS

From Terminal (bash/zsh) in this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

On Apple Silicon, every dependency (PyMuPDF, opencv-python-headless, and the PyObjC frameworks pywebview needs for its native window) publishes arm64/universal2 wheels, so no Rosetta or source builds are required.

Chromium is only needed by `scout_schedule_cli.py`; PDF extraction does not launch a browser.

## Step 1: Build `scouts.csv` from a PDF

```powershell
python .\pdf_to_scouts.py `
  ".\Class_Schedule_2026_07_06.pdf" `
  --output .\scouts.csv `
  --strict
```

macOS/Linux:

```bash
python pdf_to_scouts.py \
  "Class_Schedule_2026_07_06.pdf" \
  --output scouts.csv \
  --strict
```

By default, `Adult` and `Part-Time Adult` pages are excluded, producing a scout-only input file. Use `--include-adults` to retain them.

The CSV starts with the three columns consumed by the schedule downloader:

- `Attendee Name`
- `Registrant Type`
- `QR Code Contents`

It also adds source PDF, page number, printed name, and QR decode method for auditing. Extra columns are ignored by the schedule downloader.

### Multiple PDFs, folders, and wildcards

```powershell
python .\pdf_to_scouts.py `
  ".\pdfs\*.pdf" `
  --output .\scouts.csv
```

```powershell
python .\pdf_to_scouts.py `
  .\pdfs `
  --recursive `
  --output .\scouts.csv
```

macOS/Linux:

```bash
python pdf_to_scouts.py "pdfs/*.pdf" --output scouts.csv
python pdf_to_scouts.py pdfs --recursive --output scouts.csv
```

The extractor first decodes QR images embedded directly in the PDF. If a PDF stores the QR as vector content or an unusual image, it falls back to rendering the page at several resolutions.

### Useful PDF options

```text
--include-adults             Include adult registrations
--adult-type "Leader"        Treat another registrant type as adult/excluded
--keep-duplicates            Keep repeated QR values across PDFs
--scoutingevent-only         Exclude QR values that are not ScoutingEvent mobile URLs
--strict                     Return a failing exit code if any page is incomplete
--debug-dir .\qr-debug       Save rendered images for pages whose QR cannot be decoded
--render-dpi 300             Add/replace fallback render resolutions; repeat as needed
--no-normalize-obvious-case  Preserve obvious source capitalization errors such as MIles
```

When extraction warnings occur, the tool writes `<output-name>.errors.csv`.

## Step 2: Download schedules and requirements

```powershell
python .\scout_schedule_cli.py `
  --input .\scouts.csv `
  --output .\heritage-results
```

macOS/Linux:

```bash
python scout_schedule_cli.py \
  --input scouts.csv \
  --output heritage-results
```

For every scout, this utility:

1. Opens the QR URL in an isolated Chromium browser context so the PHP session cookie is established.
2. Clicks the **Schedule** link and captures the `getUnitClass=true` response.
3. Reads `attendeeID` from the captured POST body.
4. POSTs `getClassRequirement=true` for every returned `classP4ID` using the same browser session.
5. Exports normalized CSV and JSON files while retaining raw payloads.
6. Generates a self-contained HTML report with filtering, sorting, schedules, and expandable requirements.

### Useful schedule options

```text
--headed                  Show Chromium while the CLI runs
--timeout 90              Increase the per-scout timeout
--request-delay-ms 500    Slow down requirement requests
--allow-dead-assets       Let the two mike.dev.* JavaScript requests time out normally
--include-adults          Include adult registrations
--no-html                 Skip generation of the HTML report
--html-name schedule.html Change the HTML report filename
```

The known `mike.dev.admin.247scouting.com` and `mike.dev.scoutingevent.com` JavaScript requests are blocked by default because they currently time out. The JSON endpoints used by this tool do not depend on their rendered UI succeeding.

## Schedule output

- `report.html` — self-contained interactive report
  - filter by scout, class, block, day, location, completion status, or free text
  - view schedules grouped by scout with expandable class requirements
  - infer parent-requirement completion when all subrequirements are complete
  - mark choice requirements such as “Do TWO of the following” as **Completed, but double check** when enough alternatives appear complete
  - sort all-class and requirement tables by clicking column headings
- `scouts.json` — complete nested result
- `classes.csv` — one row per scheduled class
- `requirements.csv` — one row per requirement
- `errors.csv` — recoverable failures
- `summary.json` — totals
- `raw/` — unmodified schedule and requirement payloads

## Privacy

QR URLs and attendee IDs may act as private access tokens. Keep the PDFs, input CSV, and generated reports private, and do not commit them to a public repository.
