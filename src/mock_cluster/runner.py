"""Headless Codex execution inside the Slurm login node."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from .substrate import DockerSlurmSubstrate


@dataclass
class RunResult:
    commands: list[dict[str, Any]] = field(default_factory=list)
    transcript: list[dict[str, Any]] = field(default_factory=list)
    exit_code: int = 0
    duration_s: float = 0.0
    timed_out: bool = False
    error: str = ""
    cost: dict[str, Any] = field(default_factory=dict)
    final_message: str = ""


def parse_codex_jsonl(output: str | bytes) -> tuple[list[dict], list[dict], str, dict]:
    if isinstance(output, bytes):
        output = output.decode(errors="replace")
    transcript: list[dict] = []
    commands: list[dict] = []
    completed_ids: set[str] = set()
    final_message = ""
    usage: dict[str, Any] = {}

    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        transcript.append(event)
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        item_type = item.get("type")
        item_id = str(item.get("id", ""))
        if event.get("type") == "item.completed" and item_type in {
            "command_execution",
            "command",
        }:
            if item_id and item_id in completed_ids:
                continue
            if item_id:
                completed_ids.add(item_id)
            command = item.get("command")
            if isinstance(command, list):
                command = " ".join(str(part) for part in command)
            if command:
                commands.append(
                    {
                        "ts": event.get("timestamp_epoch") or time.time(),
                        "command": str(command),
                        "cwd": str(item.get("cwd") or ""),
                        "exit": item.get("exit_code", 0),
                        "item_id": item_id,
                    }
                )
        if event.get("type") == "item.completed" and item_type in {
            "agent_message",
            "message",
        }:
            final_message = str(item.get("text") or item.get("content") or final_message)
        candidate = event.get("usage")
        if isinstance(candidate, dict):
            usage = candidate

    cost = {
        "input_tokens": usage.get("input_tokens"),
        "cached_input_tokens": usage.get("cached_input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }
    return commands, transcript, final_message, cost


class CodexExecRunner:
    name = "codex-exec"

    def __init__(
        self,
        model: str = "gpt-5.6-terra",
        *,
        sandbox: str = "danger-full-access",
    ) -> None:
        self.model = model
        self.sandbox = sandbox

    def command(self, substrate: DockerSlurmSubstrate, episode_id: str) -> list[str]:
        codex_home = (
            "/run/mock-codex"
            if substrate.auth_mode == "gateway"
            else "/home/demo_user/.codex"
        )
        command = [
            "codex",
            "exec",
            "--model",
            self.model,
            "--json",
            "--ephemeral",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--sandbox",
            self.sandbox,
            "--cd",
            "/episode/work",
        ]
        if substrate.auth_mode == "device":
            command.append("--ignore-user-config")
        command.append("-")
        return [
            "env",
            f"CODEX_HOME={codex_home}",
            f"HPCBENCH_EPISODE={episode_id}",
            *command,
        ]

    def run(
        self,
        substrate: DockerSlurmSubstrate,
        prompt: str,
        episode_id: str,
        timeout_s: int,
    ) -> RunResult:
        substrate.prepare_codex_home()
        import shlex

        remote = "cd /episode/work && " + shlex.join(
            self.command(substrate, episode_id)
        )
        argv = substrate.ssh_argv(remote)
        started = time.time()
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=substrate.environment,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(prompt.encode(), timeout=timeout_s)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            timed_out = True
        commands, transcript, final_message, cost = parse_codex_jsonl(stdout)
        return RunResult(
            commands=commands,
            transcript=transcript,
            exit_code=process.returncode if process.returncode is not None else 124,
            duration_s=round(time.time() - started, 3),
            timed_out=timed_out,
            error=stderr.decode(errors="replace")[-4000:],
            cost=cost,
            final_message=final_message,
        )
