"""Port-zero rendezvous (D30). bind_loopback_socket() binds ONE socket to port 0 and returns it
still open and listening -- the caller reads the assigned port off THIS socket
(sock.getsockname()) and hands the SAME socket to uvicorn, rather than run_app.py's prior
two-step dance: probe-bind a throwaway socket to discover a free port, close it, then bind a
SECOND, separate socket to that port number later. Between that close and the later bind, the
OS is free to hand the same port to a different process -- this removes the gap by never
closing the socket that discovered the port."""

from __future__ import annotations

import socket


def bind_loopback_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    return sock
