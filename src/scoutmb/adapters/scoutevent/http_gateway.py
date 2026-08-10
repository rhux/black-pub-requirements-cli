"""The 'HTTP' seam (D22, NET-WIRE-001) -- so named because it is a single request/response
round trip, even though it is issued via Playwright's in-page fetch() rather than a Python HTTP
client. That stays true to how the site's session cookie works: the request must originate from
the authenticated page context, so there is no seam for a separate Python HTTP client here.

Returns the FULL requirement envelope (status + data), unmodified -- process_scout today checks
requirement_payload["status"]["status"] independently of what's inside data
(scout_schedule_cli.py:441) and writes the complete envelope to raw/ (line 437). Stripping this
down to just `data` would silently drop both behaviors; the CALLER (AcquisitionService) owns
interpreting status and validating each row, matching today's split.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from scoutmb.network_policy import assert_egress_allowed

AJAX_URL = "https://scoutingevent.com/mobile/inc/ajax_mobile.php"


async def fetch_requirement_payload(
    page: Any, attendee_id: str, class_p4_id: str
) -> dict[str, Any]:
    assert_egress_allowed(urlparse(AJAX_URL).hostname or "")

    result = await page.evaluate(
        """async ({url, attendeeId, classP4Id}) => {
            const body = new URLSearchParams({
                getClassRequirement: 'true',
                classP4ID: classP4Id,
                attendeeID: attendeeId,
                TimeStamp: new Date().toString()
            });
            const response = await fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: body.toString()
            });
            return { ok: response.ok, status: response.status, text: await response.text() };
        }""",
        {"url": AJAX_URL, "attendeeId": attendee_id, "classP4Id": class_p4_id},
    )
    if not result["ok"]:
        raise RuntimeError(f"Requirement request returned HTTP {result['status']}")
    try:
        return json.loads(result["text"])
    except json.JSONDecodeError as exc:
        preview = result["text"][:300].replace("\n", " ")
        raise RuntimeError(f"Requirement response was not JSON: {preview}") from exc
