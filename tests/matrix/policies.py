from __future__ import annotations

from dataclasses import dataclass

from tests.matrix.model import SurfaceClass


@dataclass(frozen=True, slots=True)
class SurfacePolicy:
    surface_id: str
    surface_class: SurfaceClass
    allowed_fields: frozenset[str]
    forbidden_sentinels: frozenset[str]


# Task 20: obviously-fake synthetic sentinel VALUES, never real data, used only in NEGATIVE
# assertions (proving a value never appears on a surface it should not reach). Kept together so
# every privacy test imports the same literal strings instead of hand-retyping them.
SENTINEL_DISPLAY_NAME = "Zzsentinel Displayname Example"
SENTINEL_UPSTREAM_ID = "zzsentinel-upstream-id-should-never-leak"
SENTINEL_QR_TOKEN = "zzsentinel-qr-bearer-token-should-never-leak"
SENTINEL_SESSION_ID = "zzsentinel-session-cookie-should-never-leak"
SENTINEL_PAYLOAD_FRAGMENT = "zzsentinel-raw-payload-fragment-should-never-leak"
SENTINEL_ABSOLUTE_PATH = "/zzsentinel/absolute/path/should/never/leak"

ALL_SENTINELS = frozenset(
    {
        SENTINEL_DISPLAY_NAME,
        SENTINEL_UPSTREAM_ID,
        SENTINEL_QR_TOKEN,
        SENTINEL_SESSION_ID,
        SENTINEL_PAYLOAD_FRAGMENT,
        SENTINEL_ABSOLUTE_PATH,
    }
)


# Task 19: the raw/ acquisition-audit filename surface. attendee_filename_stem builds
# "<name-slug>-<run-uuid-hex>" specifically so the bearer-token attendee_id never appears in a
# filename that might be shared for troubleshooting; this policy pins that contract so a future
# change cannot silently reintroduce the attendee_id into a filename.
_ACQUISITION_POLICIES: tuple[SurfacePolicy, ...] = (
    SurfacePolicy(
        surface_id="acq-raw-filename",
        surface_class=SurfaceClass.OPERATIONAL_PRIVATE,
        allowed_fields=frozenset({"scout_name_slug", "run_output_uuid", "class_number_slug"}),
        forbidden_sentinels=frozenset({"attendee_id"}),
    ),
)

# Task 20: the six SurfaceClass policy rows. Each pairs a surface with the fields it is allowed
# to carry and the sentinel values it must never emit. ADAPTER_PRIVATE is intentionally allowed
# to carry the upstream-id/session/payload sentinels -- that is the entire point of "adapter
# private": raw/ audit files are allowed to hold what a shareable surface must never repeat.
_SURFACE_CLASS_POLICIES: tuple[SurfacePolicy, ...] = (
    SurfacePolicy(
        surface_id="input-private",
        surface_class=SurfaceClass.INPUT_PRIVATE,
        allowed_fields=frozenset({"attendee_name", "qr_code_contents", "registrant_type"}),
        forbidden_sentinels=frozenset({SENTINEL_ABSOLUTE_PATH}),
    ),
    SurfacePolicy(
        surface_id="adapter-private",
        surface_class=SurfaceClass.ADAPTER_PRIVATE,
        allowed_fields=frozenset({"attendee_id", "session_id", "raw_payload"}),
        forbidden_sentinels=frozenset({SENTINEL_ABSOLUTE_PATH}),
    ),
    SurfacePolicy(
        surface_id="operational-private",
        surface_class=SurfaceClass.OPERATIONAL_PRIVATE,
        allowed_fields=frozenset({"scout_name_slug", "run_output_uuid", "class_number_slug"}),
        forbidden_sentinels=frozenset({SENTINEL_UPSTREAM_ID, SENTINEL_SESSION_ID}),
    ),
    SurfacePolicy(
        surface_id="audience-shareable",
        surface_class=SurfaceClass.AUDIENCE_SHAREABLE,
        allowed_fields=frozenset(
            {"scout_name", "merit_badge_name", "requirement_number", "description"}
        ),
        forbidden_sentinels=frozenset(
            {
                SENTINEL_UPSTREAM_ID,
                SENTINEL_QR_TOKEN,
                SENTINEL_SESSION_ID,
                SENTINEL_PAYLOAD_FRAGMENT,
                SENTINEL_ABSOLUTE_PATH,
            }
        ),
    ),
    SurfacePolicy(
        surface_id="local-ui",
        surface_class=SurfaceClass.LOCAL_UI,
        allowed_fields=frozenset({"scout_name", "run_summary"}),
        forbidden_sentinels=frozenset({SENTINEL_QR_TOKEN, SENTINEL_SESSION_ID}),
    ),
    SurfacePolicy(
        surface_id="diagnostic",
        surface_class=SurfaceClass.DIAGNOSTIC,
        allowed_fields=frozenset({"error_message", "scout_name", "class_number"}),
        forbidden_sentinels=frozenset({SENTINEL_QR_TOKEN, SENTINEL_SESSION_ID}),
    ),
)

# Populated by later slices; Task 16 ships the type only, Task 19 adds the raw-filename surface,
# Task 20 adds the six SurfaceClass policy rows.
POLICIES: tuple[SurfacePolicy, ...] = _ACQUISITION_POLICIES + _SURFACE_CLASS_POLICIES
