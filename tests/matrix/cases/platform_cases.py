"""Platform-scoped filename/path characterization catalog (Task 21).

Every row is ``preserve``: it pins the *current* behavior of ``scout_schedule_cli.safe_slug``
(the real, only, path-sanitization/collision-detection logic in this codebase -- see
``scout_schedule_cli.py:635-637``) against Windows- and macOS-shaped raw inputs. This module
holds only frozen data -- it never imports ``scout_schedule_cli`` or any optional third-party
package. The runner in ``tests/characterization/test_platform_matrix.py`` performs the real
import and drives the real ``safe_slug`` function.

These are PURE simulated observations over strings and ``pathlib.PureWindowsPath`` /
``pathlib.PurePosixPath`` / ``unicodedata``. They never monkeypatch ``sys.platform`` and never
claim a real OS/filesystem/installer result -- ``PureWindowsPath`` performs no I/O and works
identically on every host OS, which is exactly why it is safe to use here to derive
``expected_components`` (a plain string-decomposition fact about ``raw``, independent of the
sanitizer under test) without ever calling ``safe_slug`` to produce its own expected value.

``safe_slug``'s algorithm, traced by hand from ``scout_schedule_cli.py:636``::

    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "unknown-scout"

Every run of one-or-more non-ASCII-alphanumeric characters (including plain ASCII separators
like ``/`` ``\\`` ``:`` ``.`` ``space``, AND any non-ASCII letter such as an accented Latin
character) collapses to a single ``-``; leading/trailing dashes are then stripped, and the whole
thing is lowercased. ``expected_collision_key`` below is that output, traced by hand for each
``raw`` (verified offline against the real function while authoring this catalog, never derived
by calling it from a test at runtime to build its own expectation).

``expected_safe`` is an independent domain judgment -- computed from ``raw`` and the traced
``expected_collision_key`` together, never by calling ``safe_slug`` to decide the answer -- about
whether the CURRENT sanitized output is free of the specific hazard each case's ``raw`` carries.
Two genuine (not hypothetical) findings fall out of tracing the real regex by hand:

* Windows reserved device names (``CON``, ``PRN``, ``AUX``, ``NUL``, ``COM1``-``COM9``,
  ``LPT1``-``LPT9``) are NOT special-cased: ``safe_slug`` only lowercases them, so ``"CON"`` ->
  ``"con"`` is STILL the reserved device name (Windows device-name matching is
  case-insensitive). The per-run UUID suffix appended by ``attendee_filename_stem`` (Task
  19/20's ``ART-B-FILENAME`` boundary) is the only thing that currently prevents this from ever
  reaching a real collision -- this catalog pins the raw slug alone, before that suffix.
* The regex is ASCII-only (``[A-Za-z0-9]``): an NFC-precomposed accented letter (one non-ASCII
  code point) is stripped entirely, while the SAME logical character in NFD form (an ASCII base
  letter plus a separate non-ASCII combining mark) leaves its ASCII base letter behind. The two
  normalization forms of an identical Unicode string can therefore produce DIFFERENT slugs --
  ``safe_slug`` never Unicode-normalizes its input first.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.matrix.model import CaseMetadata, Classification, Domain, EvidenceKind

_EVIDENCE_SLUG = "scout_schedule_cli.py:635-637 safe_slug"


@dataclass(frozen=True, slots=True)
class PlatformCase:
    meta: CaseMetadata
    raw: str
    expected_components: tuple[str, ...]
    expected_collision_key: str
    expected_safe: bool
    expected_reason: str


def _meta(
    case_id: str,
    axis_id: str,
    member: str,
    rationale: str,
) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id=axis_id,
        member=member,
        domain=Domain.PLATFORM,
        classification=Classification.PRESERVE,
        evidence=EvidenceKind.CURRENT_BRANCH,
        rationale=rationale,
        contexts=("slug",),
        evidence_reference=_EVIDENCE_SLUG,
    )


# ==================================================================================================
# PLAT-WIN-001..008 -- pure PureWindowsPath-shaped raw inputs. expected_components come from
# PureWindowsPath(raw).parts (a stdlib pure-parse fact, no I/O, no real Windows involved).
# ==================================================================================================
PLATFORM_CASES_WIN: tuple[PlatformCase, ...] = (
    PlatformCase(
        meta=_meta(
            "PLAT-WIN-001",
            "PLAT-WIN",
            "reserved-device-name",
            "'CON' is a Windows-reserved device name. safe_slug only lowercases "
            "('con'), which is STILL the reserved name (Windows device matching is "
            "case-insensitive) -- the sanitizer provides no defense against this on its own.",
        ),
        raw="CON",
        expected_components=("CON",),
        expected_collision_key="con",
        expected_safe=False,
        expected_reason=(
            "safe_slug output 'con' collides with the reserved device name CON "
            "(case-insensitive); only the caller's appended per-run UUID suffix "
            "(attendee_filename_stem) prevents a real collision downstream."
        ),
    ),
    PlatformCase(
        meta=_meta(
            "PLAT-WIN-002",
            "PLAT-WIN",
            "trailing-dot-space",
            "A trailing '. ' (dot then space) is significant on real Windows (both are "
            "silently stripped by the OS). safe_slug's regex treats both as non-alnum runs, "
            "collapsing and then stripping them via .strip('-'), so no trailing artifact "
            "survives into the sanitized output.",
        ),
        raw="trailing. ",
        expected_components=("trailing. ",),
        expected_collision_key="trailing",
        expected_safe=True,
        expected_reason=(
            "The trailing dot and space both fall in the non-alnum regex class, collapse to "
            "a dash, and that dash is then stripped by .strip('-'), leaving a clean 'trailing' "
            "with no residual trailing-dot/space hazard."
        ),
    ),
    PlatformCase(
        meta=_meta(
            "PLAT-WIN-003",
            "PLAT-WIN",
            "case-collision",
            "'MixedCase' and 'MIXEDCASE' are visually distinct raw names, but safe_slug always "
            "lowercases, so both collapse to the identical collision key 'mixedcase' -- this "
            "pins that the CURRENT slug alone does not distinguish them (only the per-run UUID "
            "suffix appended by the caller keeps their eventual filenames distinct).",
        ),
        raw="MixedCase",
        expected_components=("MixedCase",),
        expected_collision_key="mixedcase",
        expected_safe=False,
        expected_reason=(
            "safe_slug forces lowercase, so 'MixedCase' and any differently-cased variant of "
            "the same letters (e.g. 'MIXEDCASE') produce the SAME collision key; the slug alone "
            "cannot disambiguate them."
        ),
    ),
    PlatformCase(
        meta=_meta(
            "PLAT-WIN-004",
            "PLAT-WIN",
            "slash-backslash",
            "A raw value mixing '/' and '\\\\' as if it were an OS path: PureWindowsPath treats "
            "both as separators, and safe_slug's regex treats both as non-alnum, so every "
            "separator (of either kind) collapses to a single '-' with no path structure "
            "surviving into the sanitized output.",
        ),
        raw="a/b\\c",
        expected_components=("a", "b", "c"),
        expected_collision_key="a-b-c",
        expected_safe=True,
        expected_reason=(
            "Both separator characters fall in the non-alnum regex class and collapse to '-'; "
            "the sanitized output carries no path-separator semantics at all."
        ),
    ),
    PlatformCase(
        meta=_meta(
            "PLAT-WIN-005",
            "PLAT-WIN",
            "drive-letter",
            "A raw value shaped like an absolute drive-letter path: PureWindowsPath parses the "
            "leading 'C:\\\\' as its own anchor component; safe_slug's regex has no concept of a "
            "drive anchor and simply collapses the colon and backslashes like any other "
            "non-alnum run.",
        ),
        raw="C:\\Users\\Scout",
        expected_components=("C:\\", "Users", "Scout"),
        expected_collision_key="c-users-scout",
        expected_safe=True,
        expected_reason=(
            "The drive letter, colon, and both backslashes all fall in the non-alnum regex "
            "class; no drive-anchor semantics survive into the sanitized output."
        ),
    ),
    PlatformCase(
        meta=_meta(
            "PLAT-WIN-006",
            "PLAT-WIN",
            "unc-path",
            "A raw value shaped like a UNC network path: PureWindowsPath folds the "
            "'\\\\\\\\server\\\\share\\\\' prefix into a single anchor component; safe_slug again has "
            "no notion of a UNC prefix and collapses every backslash run identically to any "
            "other separator.",
        ),
        raw="\\\\server\\share\\file",
        expected_components=("\\\\server\\share\\", "file"),
        expected_collision_key="server-share-file",
        expected_safe=True,
        expected_reason=(
            "Every backslash run (including the doubled UNC prefix) falls in the non-alnum "
            "regex class and collapses to '-'; no UNC-prefix semantics survive."
        ),
    ),
    PlatformCase(
        meta=_meta(
            "PLAT-WIN-007",
            "PLAT-WIN",
            "extended-length-path",
            "A raw value carrying the Windows extended-length prefix '\\\\\\\\?\\\\': "
            "PureWindowsPath folds the prefix plus drive into a single anchor component; "
            "safe_slug collapses it the same as any other non-alnum run, indistinguishable "
            "from the plain drive-letter case (PLAT-WIN-005) once sanitized.",
        ),
        raw="\\\\?\\C:\\Users\\Scout",
        expected_components=("\\\\?\\C:\\", "Users", "Scout"),
        expected_collision_key="c-users-scout",
        expected_safe=True,
        expected_reason=(
            "The '\\\\?\\' extended-length marker, drive letter, colon, and every backslash all "
            "fall in the non-alnum regex class; the sanitized output is IDENTICAL to the plain "
            "drive-letter case, so the extended-length marker leaves no distinguishing trace."
        ),
    ),
    PlatformCase(
        meta=_meta(
            "PLAT-WIN-008",
            "PLAT-WIN",
            "traversal",
            "A raw value containing '..' traversal segments: PureWindowsPath preserves them as "
            "literal path parts (no I/O, no resolution); safe_slug's regex has no notion of a "
            "traversal segment and collapses the dots the same as any other non-alnum run, so "
            "no '..' segment survives into the sanitized output.",
        ),
        raw="..\\..\\etc\\passwd",
        expected_components=("..", "..", "etc", "passwd"),
        expected_collision_key="etc-passwd",
        expected_safe=True,
        expected_reason=(
            "Every '.' and '\\\\' falls in the non-alnum regex class and collapses to '-'; no "
            "'..' traversal segment survives into the sanitized output."
        ),
    ),
)


# ==================================================================================================
# PLAT-MAC-001..005 -- pure NFC-normalize + PurePosixPath-shaped raw inputs.
# ==================================================================================================
PLATFORM_CASES_MAC: tuple[PlatformCase, ...] = (
    PlatformCase(
        meta=_meta(
            "PLAT-MAC-001",
            "PLAT-MAC",
            "nfc-nfd-equivalence",
            "The SAME logical name 'Café' in NFD form (ASCII 'e' + a separate U+0301 COMBINING "
            "ACUTE ACCENT mark, as HFS+/APFS historically store it) vs. its NFC form (a single "
            "precomposed U+00E9 'e' code point) are Unicode-canonically-equivalent, but "
            "safe_slug's regex is ASCII-only and never normalizes first: the NFD form's ASCII "
            "base letter 'e' survives ('cafe'), while the NFC form's single non-ASCII code "
            "point is stripped entirely ('caf') -- verified by hand-tracing both through the "
            "regex, not by calling safe_slug to decide which is 'right'.",
        ),
        raw="Cafe\u0301",
        expected_components=("Café",),
        expected_collision_key="cafe",
        expected_safe=False,
        expected_reason=(
            "safe_slug never Unicode-normalizes its input, so this NFD-encoded name produces "
            "'cafe' while the canonically-equivalent NFC form of the identical logical string "
            "produces 'caf' -- the two representations of one name diverge into two different "
            "collision keys under the current algorithm."
        ),
    ),
    PlatformCase(
        meta=_meta(
            "PLAT-MAC-002",
            "PLAT-MAC",
            "case-collision",
            "APFS/HFS+ are case-insensitive-by-default (though case-PRESERVING) on a stock "
            "macOS install; 'ScoutName' and 'SCOUTNAME' would already collide as real files "
            "there even before considering safe_slug -- and safe_slug's own forced lowercasing "
            "collapses them to the identical collision key regardless, so this is preserve "
            "under either lens.",
        ),
        raw="ScoutName",
        expected_components=("ScoutName",),
        expected_collision_key="scoutname",
        expected_safe=False,
        expected_reason=(
            "safe_slug forces lowercase, so 'ScoutName' and any differently-cased variant of "
            "the same letters (e.g. 'SCOUTNAME') produce the SAME collision key -- consistent "
            "with (not caused by) a case-insensitive-by-default APFS/HFS+ volume."
        ),
    ),
    PlatformCase(
        meta=_meta(
            "PLAT-MAC-003",
            "PLAT-MAC",
            "volume-root",
            "A raw value shaped like an absolute path rooted at a mounted external volume "
            "('/Volumes/Data/...'): PurePosixPath parses it as an ordinary rooted path with no "
            "special volume-anchor concept (POSIX paths do not distinguish a mounted-volume "
            "root from any other directory); safe_slug again collapses every '/' identically "
            "to any other non-alnum run.",
        ),
        raw="/Volumes/Data/Scout",
        expected_components=("Volumes", "Data", "Scout"),
        expected_collision_key="volumes-data-scout",
        expected_safe=True,
        expected_reason=(
            "Every '/' falls in the non-alnum regex class and collapses to '-'; no "
            "volume-mount-root semantics survive into the sanitized output."
        ),
    ),
    PlatformCase(
        meta=_meta(
            "PLAT-MAC-004",
            "PLAT-MAC",
            "spaces-and-unicode",
            "A raw value with leading/trailing/doubled spaces AND accented Unicode letters "
            "(both very ordinary in a real macOS display name): value.strip() removes only the "
            "outer whitespace; every remaining space and every non-ASCII letter then falls in "
            "the non-alnum regex class and collapses to a single '-' per run.",
        ),
        raw=" Zoë  Pérez ",
        expected_components=(" Zoë  Pérez ",),
        expected_collision_key="zo-p-rez",
        expected_safe=True,
        expected_reason=(
            "The outer spaces are removed by .strip() before the regex runs; the interior "
            "doubled space and both accented letters (ë, é -- non-ASCII) fall in the non-alnum "
            "regex class and collapse to single dashes, leaving a stable ASCII-only slug with "
            "no whitespace artifact."
        ),
    ),
    PlatformCase(
        meta=_meta(
            "PLAT-MAC-005",
            "PLAT-MAC",
            "traversal",
            "A raw value containing POSIX '../' traversal segments: PurePosixPath preserves "
            "them as literal path parts (no I/O, no resolution); safe_slug's regex has no "
            "notion of a traversal segment and collapses the dots the same as any other "
            "non-alnum run, so no '..' segment survives into the sanitized output.",
        ),
        raw="../../etc/passwd",
        expected_components=("..", "..", "etc", "passwd"),
        expected_collision_key="etc-passwd",
        expected_safe=True,
        expected_reason=(
            "Every '.' and '/' falls in the non-alnum regex class and collapses to '-'; no "
            "'..' traversal segment survives into the sanitized output."
        ),
    ),
)


PLATFORM_CASES: tuple[PlatformCase, ...] = PLATFORM_CASES_WIN + PLATFORM_CASES_MAC

ALL_PLATFORM_METADATA: tuple[CaseMetadata, ...] = tuple(case.meta for case in PLATFORM_CASES)
