"""Bootstrap characterization catalog (Task 21): ``bootstrap/paths.py``'s ``resolve_root``,
``bootstrap/marker.py``'s ``read_marker``/``is_environment_valid``, and
``bootstrap/source_sync.py``'s ``sync_app_source``/``_source_root``.

Domain choice (documented, not left implicit): reuses ``Domain.PLATFORM`` for the same reason
``desktop_cases.py`` does -- ``bootstrap/*`` is this codebase's own platform-specific installer
machinery (Windows app-local environment layout, marker validation, source re-sync), not the
``ui/server.py`` FastAPI surface ``Domain.INTERFACE`` already owns, and ``Domain`` is a Task-16
locked contract this task must not add a new member to.

This module holds only frozen data -- it never imports ``bootstrap.*`` at module level. The
runner in ``tests/characterization/test_bootstrap_matrix.py`` performs the real imports and
drives the real ``resolve_root``/``is_environment_valid``/``sync_app_source`` functions. Every
path used at runtime is built entirely under pytest's ``tmp_path`` -- this catalog never touches
the real user's actual application-data directory, and every literal constant it embeds below
(``MARKER_SCHEMA_VERSION == 1``, ``PYTHON_VERSION == "3.12.8"``) was copied by hand while reading
``bootstrap/config.py``, not imported, to keep this file free of any legacy/production import.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.matrix.model import CaseMetadata, Classification, Domain, EvidenceKind

_EVIDENCE_PATH = "bootstrap/paths.py:28-32 resolve_root"
_EVIDENCE_MARKER = "bootstrap/marker.py:41-51 is_environment_valid"
_EVIDENCE_SYNC = "bootstrap/source_sync.py:26-58 sync_app_source / _source_root"

# Copied by hand from bootstrap/config.py -- never imported into this data-only module.
_REAL_MARKER_SCHEMA_VERSION = 1
_REAL_PYTHON_VERSION = "3.12.8"


def _meta(case_id: str, axis_id: str, member: str, rationale: str, evidence: str) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id=axis_id,
        member=member,
        domain=Domain.PLATFORM,
        classification=Classification.PRESERVE,
        evidence=EvidenceKind.CURRENT_BRANCH,
        rationale=rationale,
        contexts=(axis_id.lower(),),
        evidence_reference=evidence,
    )


@dataclass(frozen=True, slots=True)
class BootstrapPathCase:
    meta: CaseMetadata
    override_leaf: (
        str | None
    )  # subdir name under tmp_path used as SCOUTMB_BOOTSTRAP_ROOT; None => omit the override entirely
    localappdata_leaf: str  # subdir name under tmp_path used as LOCALAPPDATA (consulted only when override_leaf is None)


@dataclass(frozen=True, slots=True)
class BootstrapMarkerCase:
    meta: CaseMetadata
    write_marker: bool  # False => no marker file at all ("missing marker")
    corrupt_marker_text: (
        str | None
    )  # if set, this literal text is written instead of a JSON payload
    schema_version_override: int | None  # None => embed the real current schema version
    python_version_override: str | None  # None => embed the real current Python version
    requirements_hash_override: (
        str | None
    )  # None => embed the real sha256 of the requirements bytes
    smoke_test_result: bool  # the patched bootstrap.marker.smoke_test return value
    expected_valid: bool


@dataclass(frozen=True, slots=True)
class BootstrapSyncCase:
    meta: CaseMetadata
    scenario: (
        str  # "single-file" | "whole-directory" | "missing-source-raises" | "frozen-vs-unfrozen"
    )


# ==================================================================================================
# BOOT-PATH-001..004 -- resolve_root's override-vs-default fallback. Every path is built
# entirely under tmp_path; SCOUTMB_BOOTSTRAP_ROOT / LOCALAPPDATA are the only env vars touched,
# and both are set (never left pointing at a real user directory) for every case, including the
# "default" one.
# ==================================================================================================
BOOTSTRAP_PATH_CASES: tuple[BootstrapPathCase, ...] = (
    BootstrapPathCase(
        meta=_meta(
            "BOOT-PATH-001",
            "BOOT-PATH",
            "override",
            "When SCOUTMB_BOOTSTRAP_ROOT is set, resolve_root returns exactly Path(override) -- "
            "LOCALAPPDATA and APP_NAME are never consulted at all, even though LOCALAPPDATA is "
            "also set in this case (to prove the override truly short-circuits the fallback "
            "branch rather than merely happening to agree with it).",
            _EVIDENCE_PATH,
        ),
        override_leaf="explicit-bootstrap-root",
        localappdata_leaf="localappdata-should-be-ignored",
    ),
    BootstrapPathCase(
        meta=_meta(
            "BOOT-PATH-002",
            "BOOT-PATH",
            "default",
            "With SCOUTMB_BOOTSTRAP_ROOT unset (the env var is absent, not merely empty), "
            "resolve_root falls back to Path(LOCALAPPDATA) / APP_NAME -- the real default "
            "resolution logic, exercised end to end against a fake LOCALAPPDATA rooted under "
            "tmp_path.",
            _EVIDENCE_PATH,
        ),
        override_leaf=None,
        localappdata_leaf="localappdata",
    ),
    BootstrapPathCase(
        meta=_meta(
            "BOOT-PATH-003",
            "BOOT-PATH",
            "spaces-in-path",
            "resolve_root performs no validation or quoting of its own -- an override value "
            "containing embedded spaces is returned as an unmodified Path, spaces and all, "
            "exactly as os.environ handed it over.",
            _EVIDENCE_PATH,
        ),
        override_leaf="Program Files Style Root With Spaces",
        localappdata_leaf="localappdata-should-be-ignored",
    ),
    BootstrapPathCase(
        meta=_meta(
            "BOOT-PATH-004",
            "BOOT-PATH",
            "unicode-in-path",
            "resolve_root performs no ASCII/encoding normalization of its own -- an override "
            "value containing non-ASCII Unicode characters is returned as an unmodified Path, "
            "exactly as os.environ (a str-valued mapping) handed it over.",
            _EVIDENCE_PATH,
        ),
        override_leaf="Scoutmb-Ünïcödé-Root-café-安装",
        localappdata_leaf="localappdata-should-be-ignored",
    ),
)


# ==================================================================================================
# BOOT-MARK-001..006 -- is_environment_valid's real validation chain: marker missing -> corrupt
# JSON -> schema mismatch -> python-version mismatch -> requirements-hash mismatch -> (only then)
# the smoke_test call. bootstrap.marker.smoke_test is patched in every case (its own real
# subprocess/exe-existence logic is out of this catalog's scope) so that ONLY the marker-field
# comparisons under test determine the outcome for every case except -001 (missing) and -003
# (corrupt), where smoke_test is never even reached.
# ==================================================================================================
BOOTSTRAP_MARKER_CASES: tuple[BootstrapMarkerCase, ...] = (
    BootstrapMarkerCase(
        meta=_meta(
            "BOOT-MARK-001",
            "BOOT-MARK",
            "missing",
            "No marker file exists at all: read_marker's own try/except catches the resulting "
            "OSError (file not found) and returns None, so is_environment_valid's "
            "`if marker is None: return False` fires immediately -- smoke_test is never called.",
            _EVIDENCE_MARKER,
        ),
        write_marker=False,
        corrupt_marker_text=None,
        schema_version_override=None,
        python_version_override=None,
        requirements_hash_override=None,
        smoke_test_result=True,
        expected_valid=False,
    ),
    BootstrapMarkerCase(
        meta=_meta(
            "BOOT-MARK-002",
            "BOOT-MARK",
            "valid",
            "A marker whose schema_version, python_version, and requirements_hash all match the "
            "current environment, combined with a smoke_test that reports success, makes "
            "is_environment_valid return True -- the one case where every one of its four "
            "sequential checks passes.",
            _EVIDENCE_MARKER,
        ),
        write_marker=True,
        corrupt_marker_text=None,
        schema_version_override=None,
        python_version_override=None,
        requirements_hash_override=None,
        smoke_test_result=True,
        expected_valid=True,
    ),
    BootstrapMarkerCase(
        meta=_meta(
            "BOOT-MARK-003",
            "BOOT-MARK",
            "corrupt-json",
            "The marker file exists but its bytes are not valid JSON: read_marker's "
            "json.loads(...) raises json.JSONDecodeError, which its own except clause catches "
            "(alongside OSError) and turns into a None return, so is_environment_valid again "
            "takes the `marker is None` branch and never reaches smoke_test.",
            _EVIDENCE_MARKER,
        ),
        write_marker=True,
        corrupt_marker_text="{ this is not valid json at all ]]]",
        schema_version_override=None,
        python_version_override=None,
        requirements_hash_override=None,
        smoke_test_result=True,
        expected_valid=False,
    ),
    BootstrapMarkerCase(
        meta=_meta(
            "BOOT-MARK-004",
            "BOOT-MARK",
            "schema-version-mismatch",
            "The marker parses as valid JSON with every other field correct, but its "
            "schema_version does not equal the current MARKER_SCHEMA_VERSION: "
            'is_environment_valid\'s second check (`marker.get("schema_version") != '
            "MARKER_SCHEMA_VERSION`) fires and returns False before python_version or the "
            "requirements hash are ever compared.",
            _EVIDENCE_MARKER,
        ),
        write_marker=True,
        corrupt_marker_text=None,
        schema_version_override=_REAL_MARKER_SCHEMA_VERSION + 1,
        python_version_override=None,
        requirements_hash_override=None,
        smoke_test_result=True,
        expected_valid=False,
    ),
    BootstrapMarkerCase(
        meta=_meta(
            "BOOT-MARK-005",
            "BOOT-MARK",
            "python-version-mismatch",
            "The marker's schema_version is correct but its recorded python_version does not "
            "equal the current PYTHON_VERSION constant: is_environment_valid's third check "
            "fires and returns False before the requirements hash is compared.",
            _EVIDENCE_MARKER,
        ),
        write_marker=True,
        corrupt_marker_text=None,
        schema_version_override=None,
        python_version_override="9.9.9-not-the-real-embedded-build",
        requirements_hash_override=None,
        smoke_test_result=True,
        expected_valid=False,
    ),
    BootstrapMarkerCase(
        meta=_meta(
            "BOOT-MARK-006",
            "BOOT-MARK",
            "requirements-hash-mismatch",
            "schema_version and python_version both match, but the marker's recorded "
            "requirements_hash does not equal compute_requirements_hash's real sha256 of the "
            "current requirements.txt bytes: is_environment_valid's fourth check fires and "
            "returns False -- smoke_test is never called even though every earlier field agreed.",
            _EVIDENCE_MARKER,
        ),
        write_marker=True,
        corrupt_marker_text=None,
        schema_version_override=None,
        python_version_override=None,
        requirements_hash_override="0" * 64,
        smoke_test_result=True,
        expected_valid=False,
    ),
)


# ==================================================================================================
# BOOT-SYNC-001..004 -- sync_app_source's real _FILES/_DIRS allowlist copy and _source_root's
# frozen-vs-unfrozen resolution. Every synthetic source tree is constructed entirely under
# tmp_path, mirroring (never inventing) the real _FILES/_DIRS entries read from
# bootstrap/source_sync.py.
# ==================================================================================================
BOOTSTRAP_SYNC_CASES: tuple[BootstrapSyncCase, ...] = (
    BootstrapSyncCase(
        meta=_meta(
            "BOOT-SYNC-001",
            "BOOT-SYNC",
            "single-file",
            'One _FILES entry ("requirements.txt") copied via shutil.copy2 lands at '
            "paths.app_dir/requirements.txt with byte-for-byte identical content to the "
            "synthetic source file this test itself wrote -- compared as real filesystem state "
            "after running the real sync_app_source, never derived from sync_app_source's own "
            "output.",
            _EVIDENCE_SYNC,
        ),
        scenario="single-file",
    ),
    BootstrapSyncCase(
        meta=_meta(
            "BOOT-SYNC-002",
            "BOOT-SYNC",
            "whole-directory",
            'The one _DIRS entry ("ui/static") copied via shutil.copytree(dirs_exist_ok=True) '
            "recursively lands every file of a synthetic nested tree (including a subdirectory) "
            "at the matching relative path under paths.app_dir/ui/static, each with identical "
            "bytes to what this test wrote into the synthetic source tree.",
            _EVIDENCE_SYNC,
        ),
        scenario="whole-directory",
    ),
    BootstrapSyncCase(
        meta=_meta(
            "BOOT-SYNC-003",
            "BOOT-SYNC",
            "missing-source-raises",
            "Honest deviation from a graceful-skip assumption: reading source_sync.py's real "
            "body shows every _FILES/_DIRS entry (and the probe_msedge.py support file) is "
            "copied UNCONDITIONALLY via shutil.copy2/copytree -- there is no try/except or "
            "existence check anywhere in sync_app_source guarding a missing source path. This "
            "case pins the ACTUAL current behavior: when a declared _FILES entry is absent from "
            "the source root, sync_app_source raises FileNotFoundError uncaught rather than "
            "skipping that entry cleanly.",
            _EVIDENCE_SYNC,
        ),
        scenario="missing-source-raises",
    ),
    BootstrapSyncCase(
        meta=_meta(
            "BOOT-SYNC-004",
            "BOOT-SYNC",
            "frozen-vs-unfrozen-source-root",
            "_source_root reads sys.frozen: when true it resolves to "
            'Path(sys._MEIPASS)/"app_src" (PyInstaller\'s bundled temp extraction dir); when '
            "false (or absent) it resolves to Path(__file__).resolve().parent.parent (the real "
            "repo root two levels up from bootstrap/source_sync.py). This case drives "
            "sync_app_source once with sys.frozen patched True against a synthetic ..._MEIPASS/"
            "app_src tree and once with it patched False against a synthetic repo-shaped tree "
            "(via a patched module __file__), and pins that the correct startup files (a "
            "_FILES entry and the _DIRS entry) are copied from whichever root is active in "
            "each of the two runs.",
            _EVIDENCE_SYNC,
        ),
        scenario="frozen-vs-unfrozen",
    ),
)


ALL_BOOTSTRAP_METADATA: tuple[CaseMetadata, ...] = (
    tuple(case.meta for case in BOOTSTRAP_PATH_CASES)
    + tuple(case.meta for case in BOOTSTRAP_MARKER_CASES)
    + tuple(case.meta for case in BOOTSTRAP_SYNC_CASES)
)
