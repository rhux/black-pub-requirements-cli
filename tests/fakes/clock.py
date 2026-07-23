"""A clock that records waits without ever sleeping (Task 19).

``StrictFakePage.wait_for_timeout`` (``tests/fakes/browser.py``) is the only place the real
acquisition code asks to wait -- both the retry backoff (``500 * attempt``) and the
per-class ``request_delay_ms`` gap go through it. ``FakeClock`` is the recorder that method
delegates to so tests can assert exact millisecond waits without a single real sleep call
anywhere in the suite.
"""

from __future__ import annotations


class FakeClock:
    """Records exact millisecond waits. Never calls ``time.sleep`` or ``asyncio.sleep``."""

    def __init__(self) -> None:
        self._waits_ms: list[int] = []

    def record(self, milliseconds: int) -> None:
        self._waits_ms.append(milliseconds)

    @property
    def waits_ms(self) -> tuple[int, ...]:
        return tuple(self._waits_ms)
