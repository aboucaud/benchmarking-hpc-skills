#!/usr/bin/env python3
"""Fixed-purpose TCP forwarder from host loopback to the internal login SSH."""

from __future__ import annotations

import os
import selectors
import socket
import socketserver


UPSTREAM_HOST = os.environ.get("MOCK_CLUSTER_SSH_UPSTREAM", "login")
UPSTREAM_PORT = 22
LISTEN_PORT = 2222


class Forward(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        try:
            upstream = socket.create_connection((UPSTREAM_HOST, UPSTREAM_PORT), timeout=5)
        except OSError:
            return
        with upstream:
            self.request.setblocking(False)
            upstream.setblocking(False)
            selector = selectors.DefaultSelector()
            selector.register(self.request, selectors.EVENT_READ, upstream)
            selector.register(upstream, selectors.EVENT_READ, self.request)
            while True:
                ready = selector.select(timeout=60)
                if not ready:
                    return
                for key, _ in ready:
                    destination = key.data
                    try:
                        block = key.fileobj.recv(65536)
                    except OSError:
                        return
                    if not block:
                        return
                    try:
                        destination.sendall(block)
                    except OSError:
                        return


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16


if __name__ == "__main__":
    with Server(("0.0.0.0", LISTEN_PORT), Forward) as server:
        server.serve_forever()
