from __future__ import annotations

import hashlib
import http.server
import threading
from pathlib import Path

import pytest
from bootstrap.downloader import download


class _Handler(http.server.BaseHTTPRequestHandler):
    payload = b"hello-world-payload"

    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture()
def local_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/payload"
    server.shutdown()


def test_stream_hash_size_and_redirect_policy(tmp_path: Path, local_server: str) -> None:
    dest = tmp_path / "payload.bin"
    good_hash = hashlib.sha256(_Handler.payload).hexdigest()

    download(local_server, dest, expected_sha256=good_hash, expected_size=len(_Handler.payload))
    assert dest.read_bytes() == _Handler.payload

    dest.unlink()
    with pytest.raises(RuntimeError, match="sha256"):
        download(local_server, dest, expected_sha256="0" * 64, expected_size=len(_Handler.payload))
    assert not dest.exists()

    dest.unlink(missing_ok=True)
    with pytest.raises(RuntimeError, match="size"):
        download(local_server, dest, expected_sha256=good_hash, expected_size=999999)
    assert not dest.exists()
