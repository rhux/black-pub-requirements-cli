# ScoutingEvent Schedule CLI

This command-line utility downloads each scout's schedule and every class-requirement payload from the ScoutingEvent mobile site.

The site currently returns valid JSON but can fail while rendering it because its jQuery Mobile code calls `listview("refresh")` before the list has been initialized. The CLI does not depend on that renderer:

1. It opens each QR URL in an isolated Chromium browser context so the PHP session cookie is established.
2. It clicks the **Schedule** link and captures the `getUnitClass=true` response.
3. It reads `attendeeID` from the captured POST body.
4. It POSTs `getClassRequirement=true` for every returned `classP4ID` using the same browser session.
5. It exports normalized CSV and JSON files while retaining raw payloads.
6. It generates a self-contained HTML report with filtering, sorting, scout schedules, class tables, and expandable requirements.

## Install on Windows

From PowerShell in this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Run with the previously generated workbook

```powershell
python .\scout_schedule_cli.py `
  --input .\Heritage_2026_Attendee_QR_Codes.xlsx `
  --sheet "Scouts Only" `
  --output .\heritage-results
```

The workbook can contain these columns:

- `Attendee Name`
- `Registrant Type`
- `QR Code Contents`

By default, rows whose registrant type is `Adult` or `Part-Time Adult` are skipped. Add `--include-adults` to retain them.

## Other supported input files

### CSV

```csv
Name,URL
First Last,https://scoutingevent.com/mobile/?hash=...
```

### Text

One URL per line, or `Name,URL` per line.

### JSON

```json
[
  {"name": "First Last", "url": "https://scoutingevent.com/mobile/?hash=..."}
]
```

## Useful options

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

## Output

- `report.html` — self-contained interactive report; open it directly in a browser
  - filter by scout, class, block, day, location, completion status, or free-text search
  - view schedules grouped by scout with expandable class requirements
  - sort the all-classes and requirements tables by clicking column headings
  - no web server or external JavaScript libraries are required
- `scouts.json` — complete nested result
- `classes.csv` — one row per scheduled class
- `requirements.csv` — one row per requirement
- `errors.csv` — recoverable failures
- `summary.json` — totals
- `raw/` — unmodified schedule and requirement payloads

## Privacy

QR URLs and attendee IDs may act as private access tokens. Keep the input and output files private and do not commit them to a public repository.
