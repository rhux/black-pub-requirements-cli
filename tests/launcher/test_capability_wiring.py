from __future__ import annotations

from pathlib import Path

import pytest
from bootstrap import browser_setup, capability_cache
from bootstrap.paths import AppPaths


def _paths(tmp_path: Path) -> AppPaths:
    root = tmp_path / "root"
    state_dir = root / "state"
    paths = AppPaths(
        root=root,
        python_dir=root / "python",
        app_dir=root / "app",
        state_dir=state_dir,
        logs_dir=root / "logs",
        marker_path=state_dir / "bootstrap_marker.json",
        lock_path=state_dir / "bootstrap.lock",
        browser_channel_path=state_dir / "browser_channel.json",
        data_dir=root / "data",
    )
    paths.ensure_dirs()
    return paths


# --- Python embeddable zip: hash-pinned, cache-referenced ------------------------------------


def test_python_zip_download_is_hash_validated_and_cache_referenced(tmp_path, monkeypatch):
    from bootstrap import python_env

    monkeypatch.setattr(python_env.platform, "system", lambda: "Windows")
    calls: dict[str, object] = {}

    def fake_download(url, dest, *, expected_sha256=None, expected_size=None, **_kwargs):
        calls["url"] = url
        calls["expected_sha256"] = expected_sha256
        calls["expected_size"] = expected_size
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake-python-zip")

    monkeypatch.setattr(python_env, "download", fake_download)
    monkeypatch.setattr(python_env, "safe_extract_zip", lambda *a, **k: None)

    paths = _paths(tmp_path)
    python_env._download_and_extract_python(paths, log=None, release_version="1.0.0")

    assert calls["url"] == python_env.PYTHON_EMBED_URL
    assert calls["expected_sha256"] == python_env.PYTHON_EMBED_SHA256
    assert calls["expected_size"] == python_env.PYTHON_EMBED_SIZE_BYTES

    cache = capability_cache.load(paths.capability_cache_dir)
    assert "1.0.0" in cache.entries["python-embed"]


def test_python_zip_download_is_never_attempted_off_windows(tmp_path, monkeypatch):
    from bootstrap import python_env

    monkeypatch.setattr(python_env.platform, "system", lambda: "Darwin")

    def fail_if_called(*_a, **_k):
        raise AssertionError("download should never be attempted on a platform mismatch")

    monkeypatch.setattr(python_env, "download", fail_if_called)

    paths = _paths(tmp_path)
    with pytest.raises(RuntimeError, match="platform mismatch"):
        python_env._download_and_extract_python(paths, log=None, release_version="1.0.0")


# --- Chromium: platform-gated, revision-tracked (NOT hash-pinned -- acquired via Playwright's
# own installer, which manages its own download; see plan Task 1 correction) -----------------


def test_chromium_install_is_platform_gated_before_invoking_playwright(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_setup.platform, "system", lambda: "PlayStation")

    def fail_if_called(*_a, **_k):
        raise AssertionError(
            "install_chromium_fallback should never be invoked for an unsupported platform"
        )

    monkeypatch.setattr(browser_setup, "install_chromium_fallback", fail_if_called)

    paths = _paths(tmp_path)
    with pytest.raises(RuntimeError, match="platform mismatch"):
        browser_setup.install_chromium_capability(paths, release_version="1.0.0")


def test_chromium_install_records_the_playwright_revision_as_a_cache_reference(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(browser_setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_setup, "install_chromium_fallback", lambda *a, **k: None)

    cache_root = tmp_path / "ms-playwright"
    (cache_root / "chromium-1105").mkdir(parents=True)
    (cache_root / "chromium-1180").mkdir(
        parents=True
    )  # highest revision -- the one that should win
    monkeypatch.setattr(browser_setup, "_ms_playwright_cache_dir", lambda: cache_root)

    paths = _paths(tmp_path)
    browser_setup.install_chromium_capability(paths, release_version="1.0.0")

    cache = capability_cache.load(paths.capability_cache_dir)
    assert "1.0.0" in cache.entries["chromium"]


def test_chromium_install_fails_loudly_if_playwright_left_no_discoverable_revision(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(browser_setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_setup, "install_chromium_fallback", lambda *a, **k: None)

    empty_cache_root = tmp_path / "ms-playwright"
    empty_cache_root.mkdir()
    monkeypatch.setattr(browser_setup, "_ms_playwright_cache_dir", lambda: empty_cache_root)

    paths = _paths(tmp_path)
    with pytest.raises(RuntimeError, match="chromium"):
        browser_setup.install_chromium_capability(paths, release_version="1.0.0")


def test_discover_chromium_revision_sorts_numerically_not_lexicographically(tmp_path, monkeypatch):
    """Regression: a naive string sort ranks "999" above "1180" (since '9' > '1' as the first
    character), picking a stale revision as if it were the newest whenever revision numbers span
    a digit-count boundary."""
    cache_root = tmp_path / "ms-playwright"
    (cache_root / "chromium-999").mkdir(parents=True)
    (cache_root / "chromium-1180").mkdir(parents=True)
    monkeypatch.setattr(browser_setup, "_ms_playwright_cache_dir", lambda: cache_root)

    assert browser_setup._discover_chromium_revision() == "1180"
