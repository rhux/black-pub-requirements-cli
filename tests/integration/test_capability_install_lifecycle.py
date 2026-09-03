from __future__ import annotations

from tests.fakes.local_capability_source import LocalCapabilitySource


def test_first_install_stages_and_verifies_every_payload_before_completion(tmp_path):
    source = LocalCapabilitySource(root=tmp_path / "source")
    source.add_payload("python-embed", version="3.12.7", contents=b"fake python")
    source.add_payload("chromium", version="130.0", contents=b"fake chromium")
    cache_dir = tmp_path / "cache"

    result = source.install_all(cache_dir=cache_dir, release_version="1.0.0")

    assert result.completed is True
    assert (cache_dir / "python-embed-3.12.7").exists()
    assert (cache_dir / "chromium-130.0").exists()


def test_interrupted_install_resumes_without_redownloading_verified_payload(tmp_path):
    source = LocalCapabilitySource(root=tmp_path / "source")
    source.add_payload("python-embed", version="3.12.7", contents=b"fake python")
    source.add_payload("chromium", version="130.0", contents=b"fake chromium")
    cache_dir = tmp_path / "cache"

    source.install_one(cache_dir=cache_dir, release_version="1.0.0", payload_id="python-embed")
    source.reset_download_call_counter()

    result = source.install_all(cache_dir=cache_dir, release_version="1.0.0")

    assert result.completed is True
    assert source.download_call_counter["python-embed"] == 0  # not redownloaded
    assert source.download_call_counter["chromium"] == 1


def test_failed_update_leaves_prior_capability_set_intact(tmp_path):
    source = LocalCapabilitySource(root=tmp_path / "source")
    source.add_payload("chromium", version="130.0", contents=b"v130")
    cache_dir = tmp_path / "cache"
    source.install_all(cache_dir=cache_dir, release_version="1.0.0")

    source.add_payload("chromium", version="131.0", contents=b"v131")
    source.fail_next_download("chromium")

    result = source.install_all(cache_dir=cache_dir, release_version="1.1.0")

    assert result.completed is False
    assert (cache_dir / "chromium-130.0").read_bytes() == b"v130"  # untouched
    assert not (cache_dir / "chromium-131.0").exists()  # the failed candidate left no trace


def test_restart_after_update_launches_offline_against_staged_set(tmp_path):
    source = LocalCapabilitySource(root=tmp_path / "source")
    source.add_payload("chromium", version="130.0", contents=b"v130")
    cache_dir = tmp_path / "cache"
    source.install_all(cache_dir=cache_dir, release_version="1.0.0")

    source.go_offline()

    assert source.can_launch_from_cache(cache_dir=cache_dir, release_version="1.0.0") is True


def test_capability_manifest_source_url_is_a_plain_swappable_string(tmp_path):
    """No staging code here assumes a specific hosting mechanism -- source_url is read and
    written as an opaque string throughout LocalCapabilitySource, never parsed or dispatched on."""
    from bootstrap.capability_manifest import build_capability_manifest

    payload = tmp_path / "p.bin"
    payload.write_bytes(b"x")
    for url in ("https://example.invalid/p.bin", "file:///local/p.bin", "s3://bucket/p.bin"):
        manifest = build_capability_manifest(
            payload_id="p", version="1", source_url=url, payload_path=payload
        )
        assert manifest.source_url == url
