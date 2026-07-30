#!/usr/bin/python3
"""Minimal credential-isolating Responses API gateway.

The agent-facing login node knows only this service's internal URL.  The real
API key exists in this service's environment, which is neither mounted nor
network-reachable as a filesystem from the login node.  Request bodies and
response bodies are never logged.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import http.client
import json
import os
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

MAX_BODY = 20 * 1024 * 1024
SAFE_REQUEST_HEADERS = {
    "accept",
    "content-type",
    "openai-beta",
    "x-stainless-arch",
    "x-stainless-lang",
    "x-stainless-os",
    "x-stainless-package-version",
    "x-stainless-runtime",
    "x-stainless-runtime-version",
}
SAFE_RESPONSE_HEADERS = {
    "content-type",
    "openai-organization",
    "openai-processing-ms",
    "openai-project",
    "x-request-id",
}


class State:
    def __init__(self) -> None:
        self.key = os.environ.get("OPENAI_API_KEY", "")
        upstream = urlsplit(
            os.environ.get("MOCK_CLUSTER_GATEWAY_UPSTREAM", "https://api.openai.com")
        )
        if upstream.scheme != "https" or not upstream.hostname:
            raise SystemExit("gateway upstream must be an https URL")
        self.host = upstream.hostname
        self.port = upstream.port or 443
        self.prefix = upstream.path.rstrip("/")
        self.max_requests = int(
            os.environ.get("MOCK_CLUSTER_GATEWAY_MAX_REQUESTS", "200")
        )
        self.requests = 0
        self.lock = threading.Lock()
        self.evidence = Path(
            os.environ.get(
                "MOCK_CLUSTER_GATEWAY_EVIDENCE", "/observer/gateway-events.jsonl"
            )
        )
        self.evidence.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.evidence.parent, 0o700)
        self.evidence.touch(exist_ok=True)
        os.chmod(self.evidence, 0o600)

    def reserve(self) -> int | None:
        with self.lock:
            if self.requests >= self.max_requests:
                return None
            self.requests += 1
            return self.requests

    def record(
        self, sequence: int, path: str, body: bytes, status: int, started: float
    ) -> None:
        model = ""
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                model = str(parsed.get("model", ""))[:120]
        except json.JSONDecodeError:
            pass
        event = {
            "schema_version": 1,
            "source": "credential_gateway",
            "sequence": sequence,
            "path": path.split("?", 1)[0],
            "model": model,
            "request_sha256": hashlib.sha256(body).hexdigest(),
            "request_bytes": len(body),
            "status": status,
            "duration_s": round(time.time() - started, 4),
            "ts": started,
            "iso": dt.datetime.now(dt.UTC).isoformat(),
        }
        line = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
        with self.lock, self.evidence.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()


STATE = State()


class Gateway(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "mock-cluster-gateway/1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def health(self, ready: bool = False) -> None:
        ok = bool(STATE.key) if ready else True
        body = json.dumps({"ok": ok}).encode()
        self.send_response(200 if ok else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/health":
            self.health()
        elif self.path == "/ready":
            self.health(ready=True)
        else:
            self.proxy()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.proxy()

    def proxy(self) -> None:
        started = time.time()
        sequence = STATE.reserve()
        if sequence is None:
            self.send_error(429, "episode gateway request limit reached")
            return
        if not STATE.key:
            self.send_error(503, "gateway has no upstream credential")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "invalid content length")
            return
        if length < 0 or length > MAX_BODY:
            self.send_error(413, "request body exceeds gateway limit")
            return
        body = self.rfile.read(length)
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() in SAFE_REQUEST_HEADERS
        }
        headers["Authorization"] = f"Bearer {STATE.key}"
        headers["Content-Length"] = str(len(body))
        headers["Host"] = STATE.host
        connection = http.client.HTTPSConnection(
            STATE.host,
            STATE.port,
            timeout=int(os.environ.get("MOCK_CLUSTER_GATEWAY_TIMEOUT", "360")),
            context=ssl.create_default_context(),
        )
        status = 502
        headers_sent = False
        try:
            path = f"{STATE.prefix}{self.path}"
            connection.request(self.command, path, body=body, headers=headers)
            response = connection.getresponse()
            status = response.status
            self.send_response(response.status, response.reason)
            for name, value in response.getheaders():
                if name.lower() in SAFE_RESPONSE_HEADERS:
                    self.send_header(name, value)
            self.send_header("Connection", "close")
            self.end_headers()
            headers_sent = True
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (OSError, http.client.HTTPException) as error:
            if not headers_sent and not self.wfile.closed:
                payload = json.dumps(
                    {"error": {"message": f"credential gateway: {error}"}}
                ).encode()
                try:
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(payload)
                except OSError:
                    pass
        finally:
            self.close_connection = True
            connection.close()
            STATE.record(sequence, self.path, body, status, started)


def main() -> None:
    host = os.environ.get("MOCK_CLUSTER_GATEWAY_BIND", "0.0.0.0")
    port = int(os.environ.get("MOCK_CLUSTER_GATEWAY_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), Gateway)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
