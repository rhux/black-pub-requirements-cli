"""B9: binding directly to port 0 and reading the assigned port back from the SAME live socket
removes the race a separate probe-then-close-then-rebind has -- a socket can be reused by
another process the instant it closes, and run_app.py's old free_port()/start_server()
two-step dance (deleted in B10.3) had exactly that gap. This test proves the merged bind never
contends with itself across many rapid iterations, which is the only way a TOCTOU race actually
shows up."""

from __future__ import annotations

import asyncio

import pytest
import uvicorn

from scoutmb.config import UiSettings
from scoutmb.interfaces.web.app import create_app
from scoutmb.interfaces.web.rendezvous import bind_loopback_socket


@pytest.mark.matrix_case(case_id="DESK-PORT-001", context_id="desk-port", lane="default")
def test_bind_loopback_socket_returns_a_working_bound_socket() -> None:
    sock = bind_loopback_socket()
    try:
        host, port = sock.getsockname()
        assert host == "127.0.0.1"
        assert port > 0
    finally:
        sock.close()


def test_many_rapid_binds_never_collide() -> None:
    """Rebinding 50 times in a tight loop is what would expose a probe-close-rebind race in
    practice -- a race window measured in microseconds is far more likely to show up across many
    iterations than one."""
    for _ in range(50):
        sock = bind_loopback_socket()
        try:
            _, port = sock.getsockname()
            assert port > 0
        finally:
            sock.close()


async def test_a_server_actually_accepts_on_the_bound_socket() -> None:
    """The two tests above only prove binding itself never collides -- they don't prove that
    handing the bound socket to a SERVER (rather than a fresh port number) actually works, which
    is the whole point of bind_loopback_socket() existing. asyncio.start_server(sock=...)
    explicitly supports accepting a pre-bound socket (the same parameter shape
    uvicorn.Server.serve(sockets=[...]) uses in run_app.py/interfaces/desktop/app.py) -- this
    test drives a minimal echo server through it and proves a real client connection succeeds,
    without needing a full uvicorn+FastAPI round trip just to prove the socket-handoff
    mechanism."""
    sock = bind_loopback_socket()
    host, port = sock.getsockname()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = await reader.read(100)
        writer.write(b"echo:" + data)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, sock=sock)
    async with server:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"ping")
        await writer.drain()
        response = await reader.read(100)
        writer.close()
        assert response == b"echo:ping"


async def test_a_real_uvicorn_app_actually_serves_on_the_bound_socket(tmp_path) -> None:
    """The two tests above prove the socket-handoff mechanism itself; this proves the actual
    combination run_app.py's/interfaces/desktop/app.py's main() uses in production -- a real
    uvicorn.Server driving the package's own create_app(settings) -- genuinely answers a real
    HTTP request through the bound socket. Replaces the package-side gap
    tests/characterization/test_phase_a_gap_closure.py's test_start_server_actually_serves_the_
    real_health_route left when run_app.py (its own target) was deleted in B10.3; DESK-MODE's
    package equivalent (tests/integration/test_desktop_app.py) always mocks uvicorn.Server, so
    nothing else exercises this end to end."""
    import httpx

    settings = UiSettings(data_root=tmp_path)
    app = create_app(settings)
    sock = bind_loopback_socket()
    host, port = sock.getsockname()
    config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
    uvicorn_server = uvicorn.Server(config)
    serve_task = asyncio.create_task(uvicorn_server.serve(sockets=[sock]))
    try:
        deadline = asyncio.get_event_loop().time() + 5.0
        async with httpx.AsyncClient() as client:
            last_error: Exception | None = None
            while asyncio.get_event_loop().time() < deadline:
                try:
                    response = await client.get(f"http://{host}:{port}/api/health", timeout=0.5)
                    break
                except httpx.TransportError as exc:
                    last_error = exc
                    await asyncio.sleep(0.05)
            else:
                raise AssertionError(f"server never became reachable: {last_error}")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        uvicorn_server.should_exit = True
        await serve_task
