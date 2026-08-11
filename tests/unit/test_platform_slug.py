"""Drives the real scoutmb.core.identity.safe_slug against every PLAT-MAC-*/PLAT-WIN-* raw
input in tests/matrix/cases/platform_cases.py -- structurally uniform (one input string -> one
safe_slug output assertion per case), so a single parametrized test using execution_params
binds every (case_id, context_id) pair to a real passing assertion, mirroring the pattern
tests/parity/test_acquisition_parity.py uses for ACQUISITION_CASES.

Each case's ``expected_collision_key`` was hand-traced (see platform_cases.py's module
docstring) from safe_slug's actual regex, so asserting the real function's output against it
is a genuine characterization, not a tautology -- and each case's ``expected_safe`` records a
real domain judgment (e.g. Windows-reserved-name / cross-normalization-form collision hazards)
about that output, asserted here too.
"""

from __future__ import annotations

import pytest
from tests.matrix.cases.platform_cases import PLATFORM_CASES, PlatformCase
from tests.matrix.pytest_support import execution_params

from scoutmb.core.identity import safe_slug

_RESERVED_WINDOWS_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul"} | {f"com{d}" for d in "123456789"} | {f"lpt{d}" for d in "123456789"}
)

# Members whose raw input carries a genuine collision/collapse hazard that survives into the
# plain slug (before attendee_filename_stem's per-run UUID suffix is appended) -- traced by
# hand in platform_cases.py's module docstring, matching each case's own expected_safe=False.
_UNSAFE_MEMBERS = frozenset({"reserved-device-name", "case-collision", "nfc-nfd-equivalence"})


@pytest.mark.parametrize(("case", "context_id"), execution_params(PLATFORM_CASES))
def test_safe_slug_matches_hand_traced_collision_key(case: PlatformCase, context_id: str) -> None:
    assert context_id == "slug"
    observed = safe_slug(case.raw)
    assert observed == case.expected_collision_key
    assert case.expected_reason  # every case documents WHY its expected_safe verdict holds
    assert case.expected_safe is (case.meta.member not in _UNSAFE_MEMBERS)

    if case.meta.member == "reserved-device-name":
        # PLAT-WIN-001: safe_slug only lowercases -- 'CON' -> 'con' is STILL the reserved
        # device name (Windows device-name matching is case-insensitive), so the sanitizer
        # alone provides no defense here.
        assert observed in _RESERVED_WINDOWS_DEVICE_NAMES
    elif case.meta.member == "nfc-nfd-equivalence":
        # PLAT-MAC-001: the NFD-encoded raw leaves its ASCII base letter behind ('cafe'), while
        # the canonically-equivalent NFC form of the SAME logical name would strip its single
        # non-ASCII code point entirely ('caf') -- two representations of one name diverging
        # into two different collision keys is the documented hazard.
        import unicodedata

        nfc_form = unicodedata.normalize("NFC", case.raw)
        assert nfc_form != case.raw  # genuinely two different code-point sequences
        assert safe_slug(nfc_form) != observed  # ...and they slugify to different results
    elif case.meta.member == "case-collision":
        # PLAT-WIN-003 / PLAT-MAC-002: safe_slug always lowercases, so any differently-cased
        # variant of the same letters collapses to the identical collision key.
        assert safe_slug(case.raw.upper()) == observed
        assert safe_slug(case.raw.lower()) == observed
