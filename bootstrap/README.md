# Building the installer exe

This produces a single small `.exe` you can email to someone with no Python
installed. It contains only a stdlib-only Python bootstrapper (tkinter for
the setup window, urllib/zipfile/subprocess for installing things) plus a
copy of this app's own source. On first run it downloads an isolated,
portable Python 3.12 and this app's dependencies into
`%LOCALAPPDATA%\ScoutingMeritBadges\` on the recipient's machine — nothing
global, nothing that touches any other Python install. Subsequent runs skip
straight to launching the app.

## Build

From the repo root, using any Python (this does not need to match the
Python 3.12 the bootstrapper installs at runtime — 3.13/3.14 both work):

```powershell
python -m pip install -r bootstrap\requirements-bootstrap-build.txt
python -m PyInstaller --noconfirm bootstrap\build.spec
```

Output: `dist\ScoutingMeritBadgesSetup.exe` (roughly 10-15MB — small enough
to email directly).

## Updating the app for someone who already has it installed

Just rebuild and re-send the exe. The app's Python *source* is always
refreshed on every launch; only the expensive parts (the Python runtime,
pip dependencies, browser) are skipped when nothing relevant changed —
bump `PYTHON_VERSION` in `bootstrap/config.py` or edit `requirements.txt`
and a fresh full setup will run automatically on their next launch.

## Bumping the embedded Python version

Edit `PYTHON_VERSION` in `bootstrap/config.py` to a newer 3.12.x patch
release (must be an amd64 "embeddable" build listed at
https://www.python.org/downloads/windows/).

## What to tell the friend before sending

- First launch takes a few minutes and needs an internet connection — it's
  downloading a private copy of Python and this app's dependencies just for
  this app, not installing anything system-wide.
- Windows will likely show a blue "Windows protected your PC" SmartScreen
  warning — click "More info" then "Run anyway". This is expected: the exe
  isn't signed with a paid certificate, not a sign of it being unsafe.
- A second, separate "Do you want to allow this app to make changes to your
  device" prompt may appear while it installs a small Microsoft component
  (WebView2 Runtime, required to show the app's window) — click Yes.

## Manual verification checklist (see the project plan for full detail)

Point `SCOUTMB_BOOTSTRAP_ROOT` at a scratch directory to simulate a clean
machine without touching the real `%LOCALAPPDATA%\ScoutingMeritBadges` or
this dev machine's own `.venv`:

```powershell
$env:SCOUTMB_BOOTSTRAP_ROOT = "C:\temp\scoutmb-test1"
python -m bootstrap.entry          # fast iteration, unfrozen
# or, after building:
dist\ScoutingMeritBadgesSetup.exe  # exercises the real packaged exe
```

- First run: full setup sequence, app launches at the end.
- Second run (same root): skips straight to launching.
- Corrupt the environment (delete a package folder under
  `python\Lib\site-packages\`, or edit `state\bootstrap_marker.json`) and
  re-run: should detect invalidity and rebuild cleanly.
- Disconnect networking and run against a fresh root: should show a
  friendly error dialog, not a crash.
