"""Direct unit tests closing real scoped-coverage gaps found in Task 22 step 9.

These are NOT part of the typed matrix-case registry: each one pins one specific branch that
the existing domain catalogs (Tasks 17-21) legitimately never needed to exercise, discovered by
running real ``coverage --branch`` over the scoped Phase A areas (``tools/check_phase_a_coverage.py``
``COVERAGE_AREAS``). Every test here calls real production code directly with hand-built inputs
or small local fakes -- no new fake-infrastructure module, no network, no real Playwright/browser,
no real file access outside ``tmp_path``.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path

import pdf_to_scouts
import pytest
import run_app
import scout_schedule_cli as cli
from tests.factories.pdf_builder import build_pdf
from tests.matrix.cases.pdf_cases import PdfPageSpec

pytestmark = pytest.mark.filterwarnings("ignore")


# =================================================================================================
# scout_schedule_cli.py -- input loaders
# =================================================================================================


def test_load_csv_without_recognizable_headers_falls_back_to_load_text(tmp_path: Path) -> None:
    path = tmp_path / "no_headers.csv"
    path.write_text("foo,bar\nhttps://example.invalid/?t=X\n", encoding="utf-8")
    result = cli.load_csv(path)
    assert result == cli.load_text(path)
    assert len(result) == 2
    assert result[-1].url == "https://example.invalid/?t=X"


def test_load_csv_of_a_completely_empty_file_falls_back_to_load_text(tmp_path: Path) -> None:
    # csv.DictReader.fieldnames is None for a zero-byte file -- a different route to the same
    # load_text() fallback than "headers present but unrecognized".
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    assert cli.load_csv(path) == cli.load_text(path) == []


def test_days_from_class_name_without_separator_is_empty() -> None:
    assert cli.days_from_class_name("Chess") == ""


# =================================================================================================
# scout_schedule_cli.py -- discover_name / navigate_and_trigger_schedule selector fallbacks
#
# These two functions are always monkeypatched away in every other characterization test (see
# tests/characterization/test_process_scout.py's module docstring and tests/vertical's use of
# Task 19's strict fakes, which never need the DOM-selector fallback because the fake page's
# goto() always fires the schedule response immediately). The selector-driven fallback paths
# genuinely need a Page-like object with .locator() -- deliberately NOT part of
# tests/fakes/browser.py's StrictFakePage (whose docstring commits to only what process_scout's
# call chain used until now) -- so a small local fake lives here instead of growing that shared
# contract for a path nothing else drives.
# =================================================================================================


class _FakeLocator:
    def __init__(self, count: int, text: str = "", raises: bool = False) -> None:
        self._count = count
        self._text = text
        self._raises = raises
        self.clicked = False

    @property
    def first(self) -> _FakeLocator:
        return self

    async def count(self) -> int:
        if self._raises:
            raise RuntimeError("locator boom")
        return self._count

    async def inner_text(self) -> str:
        return self._text

    async def click(self, *, force: bool = False, timeout: int = 0) -> None:
        self.clicked = True


class _DiscoverPage:
    """Only implements what discover_name reads off a Page: .locator(selector)."""

    def __init__(self, locators: dict[str, _FakeLocator]) -> None:
        self._locators = locators

    def locator(self, selector: str) -> _FakeLocator:
        return self._locators[selector]


async def test_discover_name_returns_fallback_immediately_when_provided() -> None:
    page = _DiscoverPage({})
    assert await cli.discover_name(page, "Avery Archer") == "Avery Archer"


async def test_discover_name_selector_loop_recovers_from_exception_and_matches() -> None:
    selectors = [
        "#scoutPage h1",
        "#scoutPage .ui-title",
        ".ui-page-active .ui-title",
        "h1.ui-title",
    ]
    page = _DiscoverPage(
        {
            selectors[0]: _FakeLocator(0, raises=True),
            selectors[1]: _FakeLocator(1, text="Schedule"),  # excluded title -> keep looking
            selectors[2]: _FakeLocator(1, text="Avery Archer"),
            selectors[3]: _FakeLocator(0),
        }
    )
    assert await cli.discover_name(page, "") == "Avery Archer"


async def test_discover_name_exhausts_selectors_and_returns_unknown() -> None:
    selectors = [
        "#scoutPage h1",
        "#scoutPage .ui-title",
        ".ui-page-active .ui-title",
        "h1.ui-title",
    ]
    page = _DiscoverPage({selector: _FakeLocator(0) for selector in selectors})
    assert await cli.discover_name(page, "") == "Unknown Scout"


class _NavPage:
    """Only implements what navigate_and_trigger_schedule reads off a Page/Response."""

    def __init__(
        self, locators: dict[str, _FakeLocator] | None = None, evaluate_resolves: bool = False
    ) -> None:
        self._locators = locators or {}
        self._listeners: list = []
        self._evaluate_resolves = evaluate_resolves
        self.evaluated = False

    def on(self, event: str, callback) -> None:
        if event == "response":
            self._listeners.append(callback)

    def remove_listener(self, event: str, callback) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    async def goto(
        self, url: str, wait_until: str | None = None, timeout: int | None = None
    ) -> None:
        # A page can dispatch OTHER ajax responses before the schedule one -- is_schedule_response
        # must reject them (line 410's False branch) without resolving the future.
        self._fire(matching=False)

    async def wait_for_timeout(self, milliseconds: int) -> None:
        await asyncio.sleep(0)

    def locator(self, selector: str) -> _FakeLocator:
        return self._locators[selector]

    def _fire(self, *, matching: bool = True) -> None:
        class _Resp:
            url = (
                "https://scoutingevent.com/mobile/ajax_mobile.php"
                if matching
                else "https://scoutingevent.com/mobile/unrelated.php"
            )

            class request:
                post_data = "getUnitClass=true&attendeeID=1" if matching else "other=1"

        for callback in list(self._listeners):
            callback(_Resp())

    async def evaluate(self, script: str) -> None:
        self.evaluated = True
        if self._evaluate_resolves:
            self._fire()


async def test_navigate_selector_loop_recovers_from_exception_then_clicks() -> None:
    selectors = [
        'a[href="#scoutPage"]',
        'a[href$="event.html#scoutPage"]',
        'a:has-text("Schedule")',
    ]

    class _ClickingLocator(_FakeLocator):
        async def click(self, *, force: bool = False, timeout: int = 0) -> None:
            self.clicked = True
            page._fire()  # clicking the real schedule link is what triggers the AJAX call

    page = _NavPage(
        {
            selectors[0]: _FakeLocator(0, raises=True),
            selectors[1]: _ClickingLocator(1),
            selectors[2]: _FakeLocator(0),
        }
    )
    response = await cli.navigate_and_trigger_schedule(page, "https://example.invalid/?t=X", 5)
    assert response is not None
    assert page._locators[selectors[1]].clicked


async def test_navigate_no_selector_matches_falls_back_to_evaluate() -> None:
    selectors = [
        'a[href="#scoutPage"]',
        'a[href$="event.html#scoutPage"]',
        'a:has-text("Schedule")',
    ]
    page = _NavPage({selector: _FakeLocator(0) for selector in selectors}, evaluate_resolves=True)
    response = await cli.navigate_and_trigger_schedule(page, "https://example.invalid/?t=X", 5)
    assert response is not None
    assert page.evaluated


# =================================================================================================
# scout_schedule_cli.py -- post_requirement error branches
# =================================================================================================


class _PostRequirementPage:
    def __init__(self, result) -> None:
        self._result = result

    async def evaluate(self, script: str, arg) -> object:
        return self._result


async def test_post_requirement_raises_on_non_ok_http_status() -> None:
    page = _PostRequirementPage({"ok": False, "status": 500, "text": ""})
    with pytest.raises(RuntimeError, match="HTTP 500"):
        await cli.post_requirement(page, "1", "2")


async def test_post_requirement_raises_on_non_json_body() -> None:
    page = _PostRequirementPage({"ok": True, "status": 200, "text": "<html>not json</html>"})
    with pytest.raises(RuntimeError, match="was not JSON"):
        await cli.post_requirement(page, "1", "2")


# =================================================================================================
# scout_schedule_cli.py -- process_scout's block_dead_assets exception recovery (:507-508)
# =================================================================================================


class _BadRouteRequest:
    url = None  # a non-string url makes re.sub raise inside block_dead_assets


class _BadRoute:
    def __init__(self) -> None:
        self.request = _BadRouteRequest()
        self.continued = False

    async def continue_(self) -> None:
        self.continued = True

    async def abort(self) -> None:
        raise AssertionError("must never abort a route whose hostname could not be parsed")


class _RoutingPage:
    def set_default_timeout(self, milliseconds: int) -> None:
        return None

    def on(self, event: str, callback) -> None:
        return None


class _RoutingContext:
    def __init__(self) -> None:
        self.route_handler = None

    async def route(self, pattern: str, handler) -> None:
        self.route_handler = handler

    async def new_page(self) -> _RoutingPage:
        return _RoutingPage()

    async def close(self) -> None:
        return None


class _RoutingBrowser:
    def __init__(self) -> None:
        self.context = _RoutingContext()

    async def new_context(self, **kwargs) -> _RoutingContext:
        return self.context


async def test_block_dead_assets_recovers_when_url_is_unparseable(tmp_path: Path) -> None:
    browser = _RoutingBrowser()
    import argparse

    args = argparse.Namespace(allow_dead_assets=False, timeout=1, headed=False, channel=None)

    async def boom(page, url, t):
        raise RuntimeError("stop before touching the page")

    original_nav = cli.navigate_and_trigger_schedule
    cli.navigate_and_trigger_schedule = boom  # type: ignore[assignment]
    try:
        await cli.process_scout(browser, cli.ScoutInput(name="x", url="https://x"), args, tmp_path)
    finally:
        cli.navigate_and_trigger_schedule = original_nav  # type: ignore[assignment]

    assert browser.context.route_handler is not None
    route = _BadRoute()
    await browser.context.route_handler(route)
    assert route.continued is True


# =================================================================================================
# scout_schedule_cli.py -- requirement-tree gaps: header-stack pop, complete_check propagation,
# ancestor-walk break on an already-complete parent, is_not_used skip of an ancestor.
# =================================================================================================


def _row(requirement_number: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "scout_name": "Avery Example",
        "attendee_id": "90000001",
        "class_p4_id": "2000001",
        "class_number": "26MB1",
        "merit_badge_name": "Chess",
        "requirement_id": "r1",
        "requirement_type_id": "1",
        "requirement_number": requirement_number,
        "description": "Show your work.",
        "completed_requirement": False,
        "completed_class": False,
        "requirement_on_event": True,
        "present_days": "MoTuWeTh",
    }
    row.update(overrides)
    return row


def test_annotate_header_stack_pops_on_shallower_sibling_header() -> None:
    rows = [
        _row("1", requirement_type_id="3"),
        _row("1a"),
        _row("2", requirement_type_id="3"),
    ]
    annotated = cli.annotate_requirement_statuses(rows)
    by_number = {item["requirement_number"]: item for item in annotated}
    assert by_number["2"]["requirement_path"] == ["2"]


def test_annotate_parent_lookup_keeps_searching_shallower_candidates() -> None:
    """A 3-level number ("1a1") with its intermediate level ("1a") never listed as its own
    row: the parent-candidate loop's first try (depth 2, "1a") fails, so it must actually loop
    back (:772->776) and try depth 1 ("1") before finding a parent."""
    rows = [_row("1"), _row("1a1")]
    annotated = cli.annotate_requirement_statuses(rows)
    by_number = {item["requirement_number"]: item for item in annotated}
    assert by_number["1a1"]["parent_requirement_number"] == "1"


def test_annotate_header_stack_fallback_keeps_searching_shallower_headers() -> None:
    """ "2a" shares no path prefix at all with the prior rows, so the primary
    prior-path-index lookup (:772-776) finds nothing and falls through to the header-stack
    fallback (:781-785). That fallback must itself keep searching past the most-recently-pushed,
    too-deep header ("1a", depth 2) back to a shallower one ("1", depth 1) -- the :783->782
    back-edge."""
    rows = [
        _row("1", requirement_type_id="3"),
        _row("1a", requirement_type_id="3"),
        _row("2a"),
    ]
    annotated = cli.annotate_requirement_statuses(rows)
    by_number = {item["requirement_number"]: item for item in annotated}
    assert by_number["2a"]["parent_requirement_number"] == "1"


def test_annotate_parent_reports_complete_check_when_a_child_is_complete_check() -> None:
    rows = [
        _row("1"),
        _row("1a", description="Do TWO of the following"),
        _row("1a1", completed_requirement=True),
        _row("1a2", completed_requirement=True),
        _row("1a3", completed_requirement=False),
        _row("1b", completed_requirement=True),
    ]
    annotated = cli.annotate_requirement_statuses(rows)
    by_number = {item["requirement_number"]: item for item in annotated}
    assert by_number["1a"]["calculated_status"] == "complete_check"
    assert by_number["1"]["calculated_status"] == "complete_check"
    assert "at least one was inferred" in by_number["1"]["calculated_status_reason"]


def test_missing_requirements_ancestor_walk_stops_at_already_complete_parent() -> None:
    scouts = [
        {
            "name": "Avery Example",
            "attendee_id": "90000001",
            "classes": [],
            "requirements": [
                _row("1", completed_requirement=True),
                _row("1a", completed_requirement=False),
            ],
            "errors": [],
        }
    ]
    grouped = cli.build_missing_requirements(scouts)
    entries = grouped["90000001"]["badges"]["Chess"]
    numbers = {entry["requirement_number"] for entry in entries}
    assert numbers == {"1a"}


def test_missing_requirements_ancestor_walk_stops_naturally_at_an_already_visited_ancestor() -> (
    None
):
    """Two sibling leaves ("1a1", "1a2") share the same incomplete parent ("1a"). The first
    leaf's walk adds "1a" to ``selected`` and stops via the explicit ``break`` at :892 (no
    further parent). The second leaf's walk reaches that SAME already-``selected`` "1a" -- the
    ``while`` loop's own condition (``id(current) not in selected``) then goes false with no
    ``break`` at all, exiting back to the outer ``for`` loop (:887->882) rather than through one
    of the two explicit ``break`` statements."""
    scouts = [
        {
            "name": "Avery Example",
            "attendee_id": "90000001",
            "classes": [],
            "requirements": [
                _row("1a"),
                _row("1a1"),
                _row("1a2"),
            ],
            "errors": [],
        }
    ]
    grouped = cli.build_missing_requirements(scouts)
    entries = grouped["90000001"]["badges"]["Chess"]
    numbers = {entry["requirement_number"] for entry in entries}
    assert numbers == {"1a", "1a1", "1a2"}


def test_missing_requirements_skips_not_used_ancestor() -> None:
    scouts = [
        {
            "name": "Avery Example",
            "attendee_id": "90000001",
            "classes": [],
            "requirements": [
                _row("2", description="(Not Used)"),
                _row("2a", completed_requirement=False),
            ],
            "errors": [],
        }
    ]
    grouped = cli.build_missing_requirements(scouts)
    entries = grouped["90000001"]["badges"]["Chess"]
    numbers = {entry["requirement_number"] for entry in entries}
    assert numbers == {"2a"}


def test_render_email_text_marks_prereq_items() -> None:
    text = cli.render_email_text(
        "Avery Example",
        {
            "Chess": [
                {
                    "requirement_number": "1",
                    "description": "Do this (pre-req)",
                    "is_prereq": True,
                    "is_leaf": True,
                    "depth": 0,
                }
            ]
        },
    )
    assert "(complete before the event)" in text


# =================================================================================================
# scout_schedule_cli.py -- write_outputs appends ".html" to a custom name lacking the extension
# =================================================================================================


def test_write_outputs_appends_html_extension_when_missing(tmp_path: Path) -> None:
    out = tmp_path / "run"
    cli.write_outputs(out, [], generate_html=True, html_name="report")
    assert (out / "report.html").exists()


# =================================================================================================
# scout_schedule_cli.py -- async_main's real progress_callback / resume_event / inter-scout delay
# (every other characterization test monkeypatches async_main itself or calls it with neither a
# progress_callback nor a resume_event, so these branches are otherwise never taken for real).
# =================================================================================================


class _AsyncMainPage:
    async def evaluate(self, script: str, arg=None) -> object:
        return {"ok": True, "status": 200, "text": json.dumps({"data": []})}

    async def wait_for_timeout(self, milliseconds: int) -> None:
        return None

    def on(self, event: str, callback) -> None:
        return None

    def remove_listener(self, event: str, callback) -> None:
        return None

    def set_default_timeout(self, milliseconds: int) -> None:
        return None

    async def close(self) -> None:
        return None


class _AsyncMainContext:
    async def new_page(self) -> _AsyncMainPage:
        return _AsyncMainPage()

    async def route(self, pattern: str, handler) -> None:
        return None

    async def close(self) -> None:
        return None


class _AsyncMainBrowser:
    async def new_context(self, **kwargs) -> _AsyncMainContext:
        return _AsyncMainContext()

    async def close(self) -> None:
        return None


class _FakePlaywrightCM:
    class _Chromium:
        async def launch(self, **kwargs) -> _AsyncMainBrowser:
            return _AsyncMainBrowser()

    async def __aenter__(self) -> _FakePlaywrightCM:
        self.chromium = self._Chromium()
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


async def test_async_main_drives_progress_callback_resume_event_and_delay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_nav(page, url, timeout_seconds):
        raise RuntimeError("no attendeeID here on purpose")

    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", fake_nav)
    monkeypatch.setattr(cli, "async_playwright", lambda: _FakePlaywrightCM())

    events: list[dict] = []

    async def progress_callback(event: dict) -> None:
        events.append(event)

    resume_event = asyncio.Event()  # starts unset -> hits the "paused" branch

    import argparse

    args = argparse.Namespace(
        input=None,
        sheet=None,
        include_adults=False,
        output=tmp_path / "out",
        timeout=1,
        allow_dead_assets=True,
        headed=False,
        channel=None,
        scout_delay_ms=1,
        no_html=True,
        html_name="report.html",
        email_report=False,
    )
    monkeypatch.setattr(
        cli,
        "load_inputs",
        lambda *a, **k: [
            cli.ScoutInput(name="A", url="https://x"),
            cli.ScoutInput(name="B", url="https://y"),
        ],
    )

    async def set_resume_soon() -> None:
        await asyncio.sleep(0)
        resume_event.set()

    task = asyncio.ensure_future(set_resume_soon())
    result = await cli.async_main(
        args, progress_callback=progress_callback, resume_event=resume_event
    )
    await task

    assert result == 1  # both scouts failed (no attendeeID) -> nonzero
    types = [event["type"] for event in events]
    assert "batch_start" in types
    assert "paused" in types
    assert "resumed" in types
    assert "scout_start" in types
    assert "scout_done" in types


async def test_async_main_pause_resume_without_a_progress_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same pause/resume branches, but with progress_callback=None -- the "if progress_callback
    is not None" guards around the paused/resumed events (:1822->1824, :1825->1828) must be
    skipped, not just taken."""

    async def fake_nav(page, url, timeout_seconds):
        raise RuntimeError("no attendeeID here on purpose")

    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", fake_nav)
    monkeypatch.setattr(cli, "async_playwright", lambda: _FakePlaywrightCM())
    monkeypatch.setattr(
        cli, "load_inputs", lambda *a, **k: [cli.ScoutInput(name="A", url="https://x")]
    )

    import argparse

    args = argparse.Namespace(
        input=None,
        sheet=None,
        include_adults=False,
        output=tmp_path / "out",
        timeout=1,
        allow_dead_assets=True,
        headed=False,
        channel=None,
        scout_delay_ms=0,
        no_html=True,
        html_name="report.html",
        email_report=False,
    )
    resume_event = asyncio.Event()

    async def set_resume_soon() -> None:
        await asyncio.sleep(0)
        resume_event.set()

    task = asyncio.ensure_future(set_resume_soon())
    result = await cli.async_main(args, progress_callback=None, resume_event=resume_event)
    await task
    assert result == 1


# =================================================================================================
# pdf_to_scouts.py -- expand_pdf_inputs: a glob pattern that matches a directory
# =================================================================================================


def test_expand_pdf_inputs_glob_matching_a_directory_recurses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two glob matches that are BOTH directories, so the `for match in matches:` loop returns to
    # its top (:161->157) after taking the directory branch at least once, regardless of the
    # filesystem's own (unspecified) glob match ordering.
    suba = tmp_path / "suba"
    subb = tmp_path / "subb"
    suba.mkdir()
    subb.mkdir()
    (suba / "a.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    (subb / "b.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    monkeypatch.chdir(tmp_path)
    result = pdf_to_scouts.expand_pdf_inputs(["sub*"], recursive=False)
    assert sorted(p.name for p in result) == ["a.pdf", "b.pdf"]


def test_value_after_label_skips_blank_candidates_and_headers_without_a_value() -> None:
    # All lines after the label are blank -- the inner loop exhausts every candidate (:185->183)
    # and the outer loop keeps scanning past the label line itself (:183->180) without a match.
    lines = ["Attendee Information", "  ", " "]
    assert pdf_to_scouts.value_after_label(lines, "Attendee Information") == ""


# =================================================================================================
# pdf_to_scouts.py -- add_quiet_zone / decode_variants pure-function edge branches
# =================================================================================================


def test_add_quiet_zone_converts_a_3_channel_image_to_grayscale_first() -> None:
    import numpy as np

    image = np.zeros((40, 40, 3), dtype=np.uint8)
    result = pdf_to_scouts.add_quiet_zone(image)
    assert result.ndim == 2


def test_decode_variants_returns_empty_for_a_none_image() -> None:
    detector = pdf_to_scouts.cv2.QRCodeDetector()
    assert pdf_to_scouts.decode_variants(None, detector) == []


def test_decode_variants_returns_empty_for_an_empty_image() -> None:
    import numpy as np

    detector = pdf_to_scouts.cv2.QRCodeDetector()
    assert pdf_to_scouts.decode_variants(np.zeros((0, 0), dtype=np.uint8), detector) == []


def test_decode_variants_recovers_from_otsu_threshold_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    def boom(*args: object, **kwargs: object):
        raise pdf_to_scouts.cv2.error("otsu boom")

    monkeypatch.setattr(pdf_to_scouts.cv2, "threshold", boom)
    detector = pdf_to_scouts.cv2.QRCodeDetector()
    image = np.zeros((40, 40), dtype=np.uint8)
    assert pdf_to_scouts.decode_variants(image, detector) == []


class _BoomingDetector:
    def detectAndDecode(self, image):
        raise pdf_to_scouts.cv2.error("decode boom")

    def detectAndDecodeMulti(self, image):
        raise ValueError("multi boom")


def test_decode_variants_recovers_from_detector_errors() -> None:
    import numpy as np

    image = np.zeros((40, 40), dtype=np.uint8)
    assert pdf_to_scouts.decode_variants(image, _BoomingDetector()) == []


# =================================================================================================
# pdf_to_scouts.py -- decode_embedded_qr: duplicate xref skip and non-square/oversize filtering
# =================================================================================================


class _FakeDocument:
    def __init__(self, images: dict[int, bytes] | None = None) -> None:
        self._images = images or {}

    def extract_image(self, xref: int):
        return {"image": self._images[xref]}  # KeyError for any xref not seeded


class _FakePage:
    def __init__(self, images: list[tuple]) -> None:
        self._images = images

    def get_images(self, full: bool = True) -> list[tuple]:
        return self._images


def test_decode_embedded_qr_tries_the_next_candidate_when_one_decodes_to_nothing() -> None:
    """A real (blank, no-QR) image for one candidate must not stop the search: :334's
    ``if selected:`` false branch has to loop back (:334->324) and try the next candidate."""
    import numpy as np

    blank = np.full((100, 100), 255, dtype=np.uint8)
    ok, encoded = pdf_to_scouts.cv2.imencode(".png", blank)
    assert ok
    images = [
        (1, 0, 100, 100, 8, "", "", "", "", 0),  # decodes cleanly but has no QR -> :334 false
        (5, 0, 120, 120, 8, "", "", "", "", 0),  # never seeded -> KeyError -> also continues
    ]
    page = _FakePage(images)
    detector = pdf_to_scouts.cv2.QRCodeDetector()
    document = _FakeDocument({1: encoded.tobytes()})
    value, method = pdf_to_scouts.decode_embedded_qr(document, page, detector)
    assert (value, method) == ("", "")


def test_decode_embedded_qr_skips_duplicate_xrefs_and_bad_sizes() -> None:
    # image_info tuple format (PyMuPDF's Page.get_images(full=True)): (xref, smask, width,
    # height, bpc, colorspace, ...) -- decode_embedded_qr reads width from index 2, height from
    # index 3.
    images = [
        (1, 0, 100, 100, 8, "", "", "", "", 0),  # square, real size -> a real candidate
        (1, 0, 100, 100, 8, "", "", "", "", 0),  # duplicate xref -> must be skipped (line 311)
        (2, 0, 20, 20, 8, "", "", "", "", 0),  # too small -> filtered (line 316)
        (3, 0, 2600, 2600, 8, "", "", "", "", 0),  # too large -> filtered (line 316)
        (4, 0, 100, 400, 8, "", "", "", "", 0),  # not square enough -> filtered (line 318)
    ]
    page = _FakePage(images)
    detector = pdf_to_scouts.cv2.QRCodeDetector()
    # xref 1 remains a real candidate; force its extraction to fail cleanly so this stays a pure
    # unit test of the filtering/dedup logic, not a real-image decode.
    document = _FakeDocument()
    value, method = pdf_to_scouts.decode_embedded_qr(document, page, detector)
    assert (value, method) == ("", "")


# =================================================================================================
# pdf_to_scouts.py -- render_page's pixmap-channel-count branches
# =================================================================================================


class _FakePixmap:
    def __init__(self, n: int) -> None:
        self.n = n
        self.width = 4
        self.height = 4
        self.samples = bytes(4 * 4 * n)


class _FakeRenderPage:
    def __init__(self, n: int) -> None:
        self._n = n

    def get_pixmap(self, dpi: int, alpha: bool = False):
        return _FakePixmap(self._n)


def test_render_page_converts_rgba_pixmap_to_bgr() -> None:
    image = pdf_to_scouts.render_page(_FakeRenderPage(4), 144)
    assert image.shape == (4, 4, 3)


def test_render_page_returns_grayscale_pixmap_unchanged() -> None:
    image = pdf_to_scouts.render_page(_FakeRenderPage(1), 144)
    assert image.shape == (4, 4, 1) or image.shape == (4, 4)


# =================================================================================================
# pdf_to_scouts.py -- extract_pdf renders a debug PNG using max(dpis) when decode_rendered_qr's own
# render never ran (an empty dpis sequence).
# =================================================================================================


def test_extract_pdf_debug_render_fallback_requires_a_non_empty_dpis(tmp_path: Path) -> None:
    """Characterizes the actual current behavior: with an empty ``dpis`` sequence,
    ``decode_rendered_qr`` never renders anything (so its own ``last_render`` stays ``None``),
    and the debug-PNG fallback at :430 then calls ``max(())``, which raises. The real CLI never
    passes an empty ``dpis`` (``parse_args`` defaults to 4 values and validates any override is
    non-empty via ``nargs="+"``), so this is reachable only through direct programmatic misuse --
    but reaching :430 (line coverage counts a statement as covered once execution starts it, even
    if it then raises) is exactly what closes this gap, so the honest fix is to pin the raise
    rather than to paper over it with a friendlier scenario that never actually exercises :430.
    """
    pdf_path = build_pdf(tmp_path / "one.pdf", (PdfPageSpec("Avery Archer", "Youth", "", "none"),))
    debug_dir = tmp_path / "debug"
    with pytest.raises(ValueError, match="empty"):
        pdf_to_scouts.extract_pdf(pdf_path, dpis=(), normalize_case=True, debug_dir=debug_dir)
    assert debug_dir.is_dir()  # mkdir at :428 ran before the :430 crash


# =================================================================================================
# pdf_to_scouts.py -- main()'s progress_callback
# =================================================================================================


def test_pdf_main_invokes_progress_callback(tmp_path: Path) -> None:
    pdf_path = build_pdf(tmp_path / "one.pdf", (PdfPageSpec("Avery Archer", "Youth", "", "none"),))
    calls: list[tuple[int, int, Path]] = []

    def progress_callback(index: int, total: int, path: Path) -> None:
        calls.append((index, total, path))

    output = tmp_path / "scouts.csv"
    # A single small --render-dpi keeps this fast: the page has no QR at all, so without an
    # explicit override extract_pdf would try every one of the default 4 DPIs (up to 400) across
    # all 5 page regions and every decode_variants scale/threshold combination.
    pdf_to_scouts.main(
        [str(pdf_path), "-o", str(output), "--quiet", "--render-dpi", "100"],
        progress_callback=progress_callback,
    )
    assert calls == [(1, 1, pdf_path)]


# =================================================================================================
# bootstrap/paths.py -- ensure_dirs and get_paths, never directly called by the resolve_root-only
# BOOT-PATH catalog.
# =================================================================================================


def test_bootstrap_paths_ensure_dirs_creates_expected_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bootstrap.paths import AppPaths

    root = tmp_path / "app-root"
    paths = AppPaths(
        root=root,
        python_dir=root / "python",
        app_dir=root / "app",
        state_dir=root / "state",
        logs_dir=root / "logs",
        marker_path=root / "state" / "marker.json",
        lock_path=root / "state" / "lock",
        browser_channel_path=root / "state" / "channel.json",
        data_dir=root / "data",
    )
    paths.ensure_dirs()
    assert paths.root.is_dir()
    assert paths.python_dir.is_dir()
    assert paths.app_dir.is_dir()
    assert paths.state_dir.is_dir()
    assert paths.logs_dir.is_dir()


def test_bootstrap_paths_get_paths_builds_from_resolve_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bootstrap.paths import get_paths

    monkeypatch.setenv("SCOUTMB_BOOTSTRAP_ROOT", str(tmp_path / "app-root"))
    paths = get_paths()
    assert paths.root == tmp_path / "app-root"
    assert paths.state_dir == paths.root / "state"
    assert paths.marker_path == paths.state_dir / "bootstrap_marker.json"


# =================================================================================================
# bootstrap/marker.py -- write_marker, never directly called by the is_environment_valid-only
# BOOT-MARK catalog.
# =================================================================================================


def test_bootstrap_marker_write_marker_writes_a_valid_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bootstrap.marker import read_marker, write_marker
    from bootstrap.paths import get_paths

    monkeypatch.setenv("SCOUTMB_BOOTSTRAP_ROOT", str(tmp_path / "app-root"))
    paths = get_paths()
    paths.ensure_dirs()
    write_marker(paths, requirements_hash="abc123", browser_channel="chrome")
    marker = read_marker(paths)
    assert marker is not None
    assert marker["requirements_hash"] == "abc123"
    assert marker["browser_channel"] == "chrome"


# =================================================================================================
# run_app.py -- start_server_on_free_port actually starting a real (loopback-only) uvicorn
# server, never exercised for real by the DESK-MODE catalog (which always monkeypatches
# start_server_on_free_port to a no-op so main()'s dispatch logic can be pinned without touching
# a real socket/thread). B9.1 merged the old free_port()/start_server(port) two-step dance into
# one race-free start_server_on_free_port() seam; this test's own assertion (a real server
# becomes reachable) is unchanged, only the call shape.
# =================================================================================================


def test_start_server_actually_serves_the_real_health_route() -> None:
    _thread, port = run_app.start_server_on_free_port()
    try:
        run_app.wait_until_ready(f"http://127.0.0.1:{port}/api/health", timeout_seconds=5.0)
    finally:
        pass  # the server thread is a daemon; it is reaped at interpreter exit, not here


# =================================================================================================
# ui/server.py -- the sys.path.insert(0, ...) import-time guard's true branch, never exercised
# because the repo root is already on sys.path by the time every other test imports ui.server.
# =================================================================================================


def test_ui_server_inserts_repo_root_onto_sys_path_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ui.server as server_module

    repo_root = str(server_module.REPO_ROOT)
    had_it = repo_root in sys.path
    if had_it:
        monkeypatch.setattr(sys, "path", [p for p in sys.path if p != repo_root])
    try:
        importlib.reload(server_module)
        assert repo_root in sys.path
    finally:
        importlib.reload(server_module)  # restore normal module state for later tests


# =================================================================================================
# ui/server.py -- _safe_run_id's SECOND check, new_run_id's real collision loop, an empty file
# list reaching start_pdf_extract's own guard (HTTP validation rejects it first, so only a direct
# call reaches this line), the stale-uploads cleanup branch, and the warnings-count branch --
# none of which the existing UI-ROUTE/RUN-ID catalog needed for its own contract.
# =================================================================================================


async def test_safe_run_id_rejects_a_bare_dot_via_the_resolved_parent_check(tmp_path: Path) -> None:
    """ "." contains none of '/', '\\\\', '..' (the first guard), but RUNS_DIR/"." resolves to
    RUNS_DIR itself, whose parent is RUNS_DIR's parent, not RUNS_DIR -- exactly the mismatch the
    second check (:106-107) exists to catch."""
    from tests.harnesses.legacy import load_legacy_ui

    async with load_legacy_ui(tmp_path) as module:
        with pytest.raises(module.HTTPException) as excinfo:
            module._safe_run_id(".")
        assert excinfo.value.status_code == 400


async def test_new_run_id_appends_a_numeric_suffix_on_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.harnesses.legacy import load_legacy_ui

    async with load_legacy_ui(tmp_path) as module:
        fixed = "2026-07-24_1200"
        # monkeypatch (not a raw attribute assignment) so the ORIGINAL strftime is captured and
        # restored automatically -- module.time IS the real global time module singleton, so a
        # bare reassignment without saving the true original first would permanently corrupt
        # time.strftime for every other test in the session.
        monkeypatch.setattr(module.time, "strftime", lambda fmt: fixed)
        (module.RUNS_DIR / fixed).mkdir(parents=True)
        assert module.new_run_id() == f"{fixed}-2"
        (module.RUNS_DIR / f"{fixed}-2").mkdir(parents=True)
        assert module.new_run_id() == f"{fixed}-3"


async def test_start_pdf_extract_rejects_an_empty_file_list_directly(tmp_path: Path) -> None:
    """FastAPI's own validation rejects a request with the 'files' field omitted entirely
    before the route body ever runs (see UI-ROUTE-006's docstring) -- reaching the route's own
    "if not files" guard (:157) requires calling the function directly with files=[]."""
    from tests.harnesses.legacy import load_legacy_ui

    async with load_legacy_ui(tmp_path) as module:
        with pytest.raises(module.HTTPException) as excinfo:
            await module.start_pdf_extract(files=[])
        assert excinfo.value.status_code == 400


class _FakeUpload:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


async def test_start_pdf_extract_cleans_stale_uploads_and_counts_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-seeds PDF_UPLOADS_DIR with a stale file from a prior run (:166-168's cleanup branch)
    and makes pdf_to_scouts.main write an errors CSV so the worker's warnings count (:196-198)
    is exercised, not just its errors.exists()-is-False path."""
    from tests.harnesses.legacy import load_legacy_ui

    async with load_legacy_ui(tmp_path) as module:
        module.PDF_UPLOADS_DIR.mkdir(parents=True)
        stale = module.PDF_UPLOADS_DIR / "old-upload.pdf"
        stale.write_bytes(b"stale")

        def fake_main(argv: list[str], *, progress_callback=None) -> int:
            out_path = Path(argv[argv.index("-o") + 1])
            out_path.write_text(
                "Attendee Name,Registrant Type,QR Code Contents\r\n"
                "Avery Archer,Youth,https://scoutingevent.com/mobile/x\r\n",
                encoding="utf-8-sig",
            )
            errors_csv = out_path.with_name(f"{out_path.stem}.errors.csv")
            errors_csv.write_text(
                "scout_name,attendee_id,error\r\nSomeone,123,boom\r\n", encoding="utf-8-sig"
            )
            return 1

        monkeypatch.setattr(module.pdf_to_scouts, "main", fake_main)
        response = await module.start_pdf_extract(files=[_FakeUpload("a.pdf", b"%PDF-1.4")])
        operation_id = json.loads(response.body)["operation_id"]
        queue = module.operations[operation_id]

        events = []
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=5)
            if event is None:
                break
            events.append(event)
        del module.operations[operation_id]

        assert not stale.exists()  # the stale upload was cleaned up before the new one was saved
        batch_done = next(event for event in events if event["type"] == "batch_done")
        assert batch_done["warnings"] == 1


# ui/server.py:387 (open_emails_folder's success `return {"opened": True}`) is NOT closed with a
# test here. UI-ROUTE-023 (tests/matrix/cases/interface_cases.py) already pins the CURRENT real
# behavior of this route on a non-Windows host: os.startfile does not exist on macOS/Linux, so
# the real route raises AttributeError (surfaced as an unhandled 500) whenever emails_dir exists
# -- :387 is only reachable on real Windows, and that gap is an intentional-change already
# deferred to Slice 2 ("dispatch on sys.platform"). Monkeypatching os.startfile here would pin
# behavior this codebase does not actually have on this platform, which is exactly what
# UI-ROUTE-023 already documents; see tests/matrix/boundaries.py's EXCLUSIONS for the honest
# coverage exclusion instead.
