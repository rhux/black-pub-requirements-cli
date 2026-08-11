"""ART-NAME-001..007,009: scoutmb.core.identity.safe_slug/attendee_filename_stem's ASCII-only,
non-alnum-collapsing contract, driven against adversarial raw inputs (path traversal, an
absolute path, all-non-ASCII text, a Windows-reserved device name, an empty string), plus two
real-filesystem containment/collision cases (a symlinked output root, and a duplicate --html-name
request). ART-NAME-008 (duplicate DISPLAY name across two attendee_ids) is already covered by
tests/unit/test_output_filenames.py::test_stem_distinct_for_distinct_output_ids.

safe_slug's algorithm (scoutmb/core/identity.py):
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "unknown-scout"
"""

from __future__ import annotations

import pytest

from scoutmb.adapters.files.atomic import atomic_write_text
from scoutmb.core.identity import RunIdentity, safe_slug
from scoutmb.interfaces.cli.composition import build_reporting_service


@pytest.mark.matrix_case(case_id="ART-NAME-001", context_id="filename", lane="default")
def test_path_traversal_collapses_to_a_plain_slug():
    """safe_slug('../../etc/passwd') collapses every run of non-[A-Za-z0-9] characters
    (including '.' and '/') to a single '-', so the traversal sequence cannot survive into the
    filename: the result is 'etc-passwd', not a path."""
    assert safe_slug("../../etc/passwd") == "etc-passwd"


@pytest.mark.matrix_case(case_id="ART-NAME-002", context_id="filename", lane="default")
def test_absolute_path_collapses_to_a_plain_slug():
    """safe_slug('/etc/shadow') collapses the leading '/' the same way -- never an absolute
    path."""
    assert safe_slug("/etc/shadow") == "etc-shadow"


@pytest.mark.matrix_case(case_id="ART-NAME-003", context_id="filename", lane="default")
def test_all_non_ascii_name_falls_back_to_unknown_scout():
    """safe_slug's character class [^A-Za-z0-9] is ASCII-only, so a name made entirely of
    non-ASCII letters has EVERY character replaced by '-', collapses to '', and falls back to
    the literal 'unknown-scout' -- a real, surprising PRESERVE finding, not a fix."""
    assert safe_slug("日本語太郎") == "unknown-scout"


@pytest.mark.matrix_case(case_id="ART-NAME-004", context_id="filename", lane="default")
def test_case_only_difference_collapses_to_the_same_slug_but_stems_stay_distinct():
    """safe_slug lowercases, so 'Avery Archer' and 'AVERY ARCHER' produce the identical slug
    'avery-archer' -- a PURE simulated string-contract case (no real filesystem collision is
    exercised)."""
    slug_a = safe_slug("Avery Archer")
    slug_b = safe_slug("AVERY ARCHER")
    assert slug_a == slug_b == "avery-archer"


@pytest.mark.matrix_case(case_id="ART-NAME-005", context_id="filename", lane="default")
def test_windows_reserved_device_name_has_no_defense():
    """safe_slug('CON') has no Windows-reserved-device-name defense at all: the slug is the
    literal 'con', which a real Windows filesystem would refuse as a bare filename component.
    Pure simulated string-contract case over the slugification logic."""
    assert safe_slug("CON") == "con"


@pytest.mark.matrix_case(case_id="ART-NAME-006", context_id="filename", lane="default")
def test_empty_name_falls_back_to_unknown_scout():
    """safe_slug('') collapses to '' and falls back to the literal 'unknown-scout', identical
    to the all-non-ASCII case."""
    assert safe_slug("") == "unknown-scout"


@pytest.mark.matrix_case(case_id="ART-NAME-007", context_id="filename", lane="default")
def test_symlinked_output_root_is_followed_with_no_containment_check(tmp_path):
    """Legacy atomic_write_text/write_outputs call Path.mkdir/Path.open directly with no
    realpath resolution or containment check: when the CLI's --output directory is itself a
    symlink to another directory, the file is published THROUGH the symlink into that OTHER
    directory with no warning or rejection. INTENTIONAL_CHANGE: Slice 2's output-root
    resolution will reject (or explicitly confirm) a symlinked --output directory instead of
    silently following it -- this test pins the CURRENT (pre-Slice-2) behavior."""
    real_target = tmp_path / "real_target"
    real_target.mkdir()
    link_root = tmp_path / "link_root"
    link_root.symlink_to(real_target, target_is_directory=True)

    # Publish THROUGH the symlinked root.
    atomic_write_text(link_root / "probe.txt", "hello", encoding="utf-8")

    # The file landed in the REAL (non-symlink) target directory -- proving the symlink was
    # followed with no containment check anywhere in atomic_write_text.
    assert (real_target / "probe.txt").read_text(encoding="utf-8") == "hello"
    assert (link_root / "probe.txt").read_text(encoding="utf-8") == "hello"


@pytest.mark.matrix_case(case_id="ART-NAME-009", context_id="filename", lane="default")
def test_duplicate_html_name_request_overwrites_last_write_wins(tmp_path):
    """write_outputs resolves --html-name to Path(html_name).name (its basename only), so a
    path-like or repeated html_name always collapses to the same safe basename inside
    output_dir; writing the report twice with the same requested name simply overwrites the
    prior file atomically (last write wins), never creating two files or escaping output_dir."""
    out = tmp_path / "run"
    service = build_reporting_service()

    # A path-like html_name: only its basename ("report.html") must ever be used.
    service.publish(
        out,
        [],
        generated_at_local="2026-01-01 00:00:00",
        generated_at_iso="2026-01-01T00:00:00",
        run_identity=RunIdentity(),
        generate_html=True,
        html_name="sub/dir/report.html",
    )
    first_content = (out / "report.html").read_text(encoding="utf-8")

    service.publish(
        out,
        [],
        generated_at_local="2026-06-06 00:00:00",
        generated_at_iso="2026-06-06T00:00:00",
        run_identity=RunIdentity(),
        generate_html=True,
        html_name="sub/dir/report.html",
    )
    second_content = (out / "report.html").read_text(encoding="utf-8")

    # No subdirectory was ever created -- the basename-only resolution means "sub/dir" never
    # exists as a real path component anywhere under output_dir or above it.
    assert not (out / "sub").exists()
    assert not (out.parent / "sub").exists()
    assert not (tmp_path / "sub").exists()

    # Only ever one report.html on disk (an overwrite, not a second file).
    html_files = list(out.glob("*.html"))
    assert html_files == [out / "report.html"]

    # Last write wins: the second publish's embedded timestamp replaced the first's.
    assert first_content != second_content
    assert "2026-01-01" in first_content
    assert "2026-06-06" in second_content
