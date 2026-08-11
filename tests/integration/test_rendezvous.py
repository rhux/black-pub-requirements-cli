"""B9: binding directly to port 0 and reading the assigned port back from the SAME live socket
removes the race a separate probe-then-close-then-rebind has -- a socket can be reused by
another process the instant it closes, and free_port()/start_server()'s two-step dance in
run_app.py has exactly that gap. This test proves the merged bind never contends with itself
across many rapid iterations, which is the only way a TOCTOU race actually shows up."""

from __future__ import annotations

import asyncio

from scoutmb.interfaces.web.rendezvous import bind_loopback_socket


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
