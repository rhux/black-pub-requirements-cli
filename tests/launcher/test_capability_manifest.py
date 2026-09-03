from __future__ import annotations

import json
import platform

from bootstrap.capability_manifest import CapabilityManifest, build_capability_manifest


def test_build_capability_manifest_captures_current_os_and_arch(tmp_path):
    payload = tmp_path / "python-embed.zip"
    payload.write_bytes(b"fake python zip contents")

    manifest = build_capability_manifest(
        payload_id="python-embed",
        version="3.12.7",
        source_url="https://example.invalid/python-3.12.7.zip",
        payload_path=payload,
    )

    assert manifest.os == platform.system()
    assert manifest.arch == platform.machine()
    assert manifest.size_bytes == payload.stat().st_size
    assert len(manifest.sha256) == 64  # hex digest


def test_capability_manifest_round_trips_through_json(tmp_path):
    payload = tmp_path / "chromium.zip"
    payload.write_bytes(b"fake chromium contents")
    manifest = build_capability_manifest(
        payload_id="chromium", version="130.0", source_url="https://example.invalid/c.zip",
        payload_path=payload,
    )

    restored = CapabilityManifest.from_json(json.loads(manifest.to_json()))

    assert restored == manifest
