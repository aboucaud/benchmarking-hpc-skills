#!/usr/bin/python3
"""Record bounded, redacted process evidence for the login service."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import time
from pathlib import Path

TARGET_UID = int(os.environ.get("SITE_MONITOR_UID", "5001"))
OUTPUT = Path(os.environ.get("SITE_MONITOR_OUTPUT", "/run/site-monitor/events.jsonl"))
INTERVAL = float(os.environ.get("SITE_MONITOR_INTERVAL", "0.05"))
MAX_EVENTS = int(os.environ.get("SITE_MONITOR_MAX_EVENTS", "5000"))
SCRIPT = re.compile(r"(?:^|[\s\"'])([^/\s\"']+\.(?:py|sh))(?:$|[\s\"'])")


def process_uid(pid: str) -> int | None:
    try:
        for line in (Path("/proc") / pid / "status").read_text().splitlines():
            if line.startswith("Uid:"):
                return int(line.split()[1])
    except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
        return None
    return None


def process_key(pid: str) -> tuple[str, str, str] | None:
    try:
        fields = (Path("/proc") / pid / "stat").read_text().split()
        command_line = (Path("/proc") / pid / "cmdline").read_bytes()
        signature = hashlib.sha256(command_line).hexdigest()
        return pid, fields[21], signature
    except (
        FileNotFoundError,
        PermissionError,
        ProcessLookupError,
        IndexError,
    ):
        return None


def process_summary(pid: str) -> dict | None:
    root = Path("/proc") / pid
    try:
        raw = (root / "cmdline").read_bytes().split(b"\0")
        arguments = [item.decode(errors="replace") for item in raw if item]
        parent = int((root / "stat").read_text().split()[3])
    except (
        FileNotFoundError,
        PermissionError,
        ProcessLookupError,
        ValueError,
        IndexError,
    ):
        return None
    if not arguments:
        return None
    # Resolving /proc/<pid>/exe for a different UID requires ptrace capability
    # on some Docker hosts. The first argv entry is sufficient for the
    # redacted basename and avoids broadening container privileges.
    executable = Path(arguments[0]).name

    scripts: list[str] = []
    for argument in arguments[1:]:
        if argument.endswith((".py", ".sh")):
            scripts.append(Path(argument).name)
        scripts.extend(Path(item).name for item in SCRIPT.findall(argument))
    scripts = list(dict.fromkeys(scripts))[:4]
    command = " ".join([executable, *scripts]).strip()
    now = time.time()
    return {
        "schema_version": 1,
        "source": "login_process",
        "event": "process_start",
        "pid": int(pid),
        "ppid": parent,
        "executable": executable,
        "scripts": scripts,
        "command": command,
        "ts": now,
        "iso": dt.datetime.now(dt.timezone.utc).isoformat(),  # noqa: UP017
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.chmod(0o700)
    OUTPUT.touch(exist_ok=True)
    OUTPUT.chmod(0o600)
    # Include the command line in the identity so an sshd child that drops
    # privileges and execs the user's command is observed after each change.
    seen: set[tuple[str, str, str]] = set()
    written = 0
    while written < MAX_EVENTS:
        try:
            pids = [entry.name for entry in Path("/proc").iterdir() if entry.name.isdigit()]
        except FileNotFoundError:
            time.sleep(INTERVAL)
            continue
        for pid in pids:
            key = process_key(pid)
            if key is None or key in seen:
                continue
            if process_uid(pid) != TARGET_UID:
                continue
            seen.add(key)
            event = process_summary(pid)
            if event is None:
                continue
            with OUTPUT.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
            written += 1
            if written >= MAX_EVENTS:
                break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
