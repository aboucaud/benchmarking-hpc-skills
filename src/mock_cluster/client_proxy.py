#!/usr/bin/python3
"""Agent-facing Slurm client proxy.

Every monitored Slurm client in the login and compute images is a symlink to
this program.  It sends one bounded request to the root observer, which owns
the real clients.  No real Slurm executable or observer evidence is present in
the agent-facing image.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import sys
from pathlib import Path

MAX_RESPONSE = 16 * 1024 * 1024
ENV_EXACT = {
    "ARCHIVE",
    "DATA",
    "HOME",
    "HPCBENCH_EPISODE",
    "LANG",
    "LC_ALL",
    "LD_LIBRARY_PATH",
    "LOGNAME",
    "MODULEPATH",
    "PATH",
    "PYTHONPATH",
    "SCRATCH",
    "SHELL",
    "TMPDIR",
    "USER",
}
ENV_PREFIXES = ("SLURM_", "SPANK_", "PMI_", "PMIX_", "UCX_")


def forwarded_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key in ENV_EXACT or key.startswith(ENV_PREFIXES)
    }


def fail(message: str, code: int = 111) -> int:
    print(f"mock-cluster proxy: {message}", file=sys.stderr)
    return code


def main() -> int:
    command = Path(sys.argv[0]).name
    host = os.environ.get("MOCK_CLUSTER_OBSERVER_HOST", "observer")
    try:
        port = int(os.environ.get("MOCK_CLUSTER_OBSERVER_PORT", "9473"))
    except ValueError:
        return fail("invalid observer port")

    request = {
        "schema_version": 1,
        "kind": "slurm_client",
        "command": command,
        "argv": [command, *sys.argv[1:]],
        "cwd": os.getcwd(),
        "env": forwarded_environment(),
        "episode_id": os.environ.get("HPCBENCH_EPISODE", "unscoped"),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "pid": os.getpid(),
        "ppid": os.getppid(),
    }
    payload = json.dumps(request, separators=(",", ":")).encode() + b"\n"

    try:
        with socket.create_connection((host, port), timeout=10) as connection:
            connection.settimeout(None)
            connection.sendall(payload)
            stream = connection.makefile("rb")
            raw = stream.readline(MAX_RESPONSE + 1)
    except OSError as error:
        return fail(f"observer unavailable: {error}")

    if not raw:
        return fail("observer closed the request without a response")
    if len(raw) > MAX_RESPONSE:
        return fail("observer response exceeded the safety limit")
    try:
        response = json.loads(raw)
        stdout = base64.b64decode(response.get("stdout_b64", ""), validate=True)
        stderr = base64.b64decode(response.get("stderr_b64", ""), validate=True)
    except (ValueError, json.JSONDecodeError) as error:
        return fail(f"malformed observer response: {error}")

    sys.stdout.buffer.write(stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(stderr)
    sys.stderr.buffer.flush()
    return int(response.get("exit_code", 111))


if __name__ == "__main__":
    raise SystemExit(main())
