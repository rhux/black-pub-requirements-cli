"""Playwright-backed ScoutingEventGateway. Owns the Browser/Context/Page lifecycle so
features/acquisition never imports playwright.async_api (NET-WIRE-002).

Playwright's types are imported only under TYPE_CHECKING: every use in this module is duck-typed
(nothing does isinstance() against Browser/Page/Response, and Browser is always handed in from
outside -- async_main's own playwright.chromium.launch() call). `from __future__ import
annotations` defers every annotation to a string, so a TYPE_CHECKING-only import gives mypy the
real types with zero runtime import cost -- important because playwright is the `acquisition`
optional extra, and a bare module-scope import here would be an avoidable ImportError risk for
a build without it installed.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from scoutmb.network_policy import assert_egress_allowed
from scoutmb.ports.scoutevent import RequirementFetchResult, ScheduleFetchResult

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Response

DEAD_ASSET_HOSTS = {
    "mike.dev.admin.247scouting.com",
    "mike.dev.scoutingevent.com",
}


def form_values(post_data: str | None) -> dict[str, str]:
    from urllib.parse import parse_qs

    parsed = parse_qs(post_data or "", keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def is_schedule_response(response: Response) -> bool:
    if "ajax_mobile.php" not in response.url:
        return False
    return form_values(response.request.post_data).get("getUnitClass", "").lower() == "true"


async def discover_name(page: Page, fallback: str) -> str:
    """Exact mirror of scout_schedule_cli.discover_name (lines 227-245) -- moved here because
    the gateway is now what calls it, right after the attendee ID is known, matching
    process_scout's existing ordering."""
    if fallback:
        return fallback
    selectors = [
        "#scoutPage h1",
        "#scoutPage .ui-title",
        ".ui-page-active .ui-title",
        "h1.ui-title",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if await locator.count():
                text = (await locator.first.inner_text()).strip()
                if text and text.lower() not in {"schedule", "event", "menu"}:
                    return text
        except Exception:
            pass  # this selector didn't match/render -- try the next one, not a real failure
    return "Unknown Scout"


class _PlaywrightSession:
    def __init__(self, context: BrowserContext, page: Page) -> None:
        self._context = context
        self._page = page

    async def fetch_schedule(
        self, qr_url: str, timeout_seconds: int, fallback_name: str
    ) -> ScheduleFetchResult:
        response = await PlaywrightScoutingEventGateway._fetch_schedule_on_page(
            self._page, qr_url, timeout_seconds
        )
        values = form_values(response.request.post_data)
        attendee_id = values.get("attendeeID", "")
        payload = await response.json()
        display_name = await discover_name(self._page, fallback_name)
        return ScheduleFetchResult(attendee_id=attendee_id, display_name=display_name, payload=payload)

    async def fetch_requirements(self, attendee_id: str, class_p4_id: str) -> RequirementFetchResult:
        """Fetches AND validates in one step -- validate_requirement_row's import stays
        adapter-to-adapter (allowed), never reaching into features/acquisition/service.py, which
        only ever sees the already-validated result."""
        from scoutmb.adapters.scoutevent.http_gateway import fetch_requirement_payload
        from scoutmb.adapters.scoutevent.schema import (
            ScoutingEventSchemaDrift,
            validate_requirement_row,
        )

        payload = await fetch_requirement_payload(self._page, attendee_id, class_p4_id)
        validated_rows: list[dict[str, Any]] = []
        row_errors: list[str] = []
        for row in payload.get("data") or ():
            try:
                validated_rows.append(validate_requirement_row(dict(row)))
            except ScoutingEventSchemaDrift as exc:
                row_errors.append(str(exc))
        return RequirementFetchResult(
            payload=payload, validated_rows=tuple(validated_rows), row_errors=tuple(row_errors)
        )


class PlaywrightScoutingEventGateway:
    """ScoutingEventGateway over one already-launched Browser. One instance per run."""

    def __init__(self, browser: Browser, *, allow_dead_assets: bool = False) -> None:
        self._browser = browser
        self._allow_dead_assets = allow_dead_assets

    @staticmethod
    async def _fetch_schedule_on_page(page: Any, qr_url: str, timeout_seconds: int) -> Response:
        """The exact navigate_and_trigger_schedule body, with one addition: the egress check
        below runs before page.goto and nowhere else navigates. A staticmethod (not a bare
        module function) so the unit test can call it directly against a stub page with no real
        BrowserContext, while still reading naturally as "the gateway's schedule-fetch primitive"
        at the call site inside _PlaywrightSession.fetch_schedule above."""
        from urllib.parse import urlparse

        host = urlparse(qr_url).hostname or ""
        assert_egress_allowed(host)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()

        async def inspect_response(response: Any) -> None:
            if not future.done() and is_schedule_response(response):
                future.set_result(response)

        def on_response(response: Any) -> None:
            asyncio.create_task(inspect_response(response))

        page.on("response", on_response)
        try:
            await page.goto(qr_url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            await page.wait_for_timeout(1200)
            if not future.done():
                selectors = [
                    'a[href="#scoutPage"]',
                    'a[href$="event.html#scoutPage"]',
                    'a:has-text("Schedule")',
                ]
                clicked = False
                for selector in selectors:
                    locator = page.locator(selector)
                    try:
                        if await locator.count():
                            await locator.first.click(force=True, timeout=5000)
                            clicked = True
                            break
                    except Exception:
                        continue  # this selector didn't click -- try the next one
                if not clicked:
                    await page.evaluate(
                        """() => {
                            const link = document.querySelector('a[href="#scoutPage"]') ||
                                         [...document.querySelectorAll('a')].find(a =>
                                             (a.textContent || '').trim().toLowerCase() === 'schedule');
                            if (link) link.click();
                        }"""
                    )
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        finally:
            page.remove_listener("response", on_response)

    @asynccontextmanager
    async def open_session(self) -> AsyncIterator[_PlaywrightSession]:
        context = await self._browser.new_context(ignore_https_errors=True)
        if not self._allow_dead_assets:

            async def block_dead_assets(route: Any) -> None:
                try:
                    hostname = (
                        re.sub(r"^https?://", "", route.request.url).split("/", 1)[0].split(":", 1)[0]
                    )
                    if hostname in DEAD_ASSET_HOSTS:
                        await route.abort()
                    else:
                        await route.continue_()
                except Exception:
                    await route.continue_()  # fail-open: never block a request over our own bug

            await context.route("**/*", block_dead_assets)
        page = await context.new_page()
        try:
            yield _PlaywrightSession(context, page)
        finally:
            await context.close()
