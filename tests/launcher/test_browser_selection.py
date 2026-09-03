from __future__ import annotations

from bootstrap import browser_setup


def test_macos_tries_chrome_before_falling_back_to_chromium(monkeypatch, tmp_path):
    monkeypatch.setattr(browser_setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_setup, "probe_chrome_macos", lambda paths: True)
    calls: list[str] = []
    monkeypatch.setattr(
        browser_setup, "install_chromium_capability", lambda *a, **k: calls.append("fallback")
    )

    channel = browser_setup.resolve_browser_channel(paths=object(), release_version="1.0.0")

    assert channel == "chrome"
    assert calls == []  # fallback never invoked when the Chrome probe succeeds


def test_macos_falls_back_to_chromium_when_chrome_probe_fails(monkeypatch):
    monkeypatch.setattr(browser_setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_setup, "probe_chrome_macos", lambda paths: False)
    calls: list[str] = []
    monkeypatch.setattr(
        browser_setup, "install_chromium_capability", lambda *a, **k: calls.append("fallback")
    )

    channel = browser_setup.resolve_browser_channel(paths=object(), release_version="1.0.0")

    assert channel is None  # None == bundled Chromium, same contract as the Windows path
    assert calls == ["fallback"]


def test_safari_is_never_returned_by_the_normal_resolve_path(monkeypatch):
    monkeypatch.setattr(browser_setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_setup, "probe_chrome_macos", lambda paths: False)
    monkeypatch.setattr(browser_setup, "install_chromium_capability", lambda *a, **k: None)

    channel = browser_setup.resolve_browser_channel(paths=object(), release_version="1.0.0")

    assert channel != "safari"


def test_windows_path_is_unaffected_by_the_macos_dispatch(monkeypatch):
    monkeypatch.setattr(browser_setup.platform, "system", lambda: "Windows")
    monkeypatch.setattr(browser_setup, "probe_msedge_channel", lambda paths: True)

    def fail_if_called(*_a, **_k):
        raise AssertionError("macOS-only probe must never run on Windows")

    monkeypatch.setattr(browser_setup, "probe_chrome_macos", fail_if_called)

    channel = browser_setup.resolve_browser_channel(paths=object(), release_version="1.0.0")

    assert channel == "msedge"


def test_experimental_safari_path_returns_a_truthful_warning():
    channel, warning = browser_setup.resolve_experimental_safari()

    assert channel == "safari"
    assert "experimental" in warning.lower()


def test_force_chromium_fallback_env_var_works_identically_on_the_macos_probe(monkeypatch):
    monkeypatch.setenv("SCOUTMB_FORCE_CHROMIUM_FALLBACK", "1")

    assert browser_setup.probe_chrome_macos(paths=object()) is False  # never even shells out
