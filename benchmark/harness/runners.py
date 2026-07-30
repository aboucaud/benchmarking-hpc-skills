#!/usr/bin/env python3
"""How an episode gets an agent to act, and how its conduct is recovered afterwards.

Three runners behind one protocol:

  `ScriptedRunner`     runs a fixed list of shell commands. Not a mock — it is how the detectors
                       are tested against known-bad and known-good conduct without a model in the
                       loop, and how the harness is exercised in CI-less development.
  `ClaudeCodeRunner`   runs `claude -p` headless in the sandbox and recovers the commands it ran
                       from the stream-json transcript.
  `NoopRunner`         materializes and stops, for inspecting a condition.

Every runner returns the same thing, because the judge must not be able to tell them apart:

    RunResult(commands, transcript, exit_code, duration_s, timed_out, error)

`commands` is the part that matters. Case B3's defect is running `preprocess.py` on a login node,
which is not a Slurm call and therefore invisible to the stub log — so the transcript is the only
place that conduct is recorded, and a runner that cannot report it silently deletes the case.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class RunResult:
    commands: list[dict] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)
    exit_code: int = 0
    duration_s: float = 0.0
    timed_out: bool = False
    error: str = ""
    cost: dict = field(default_factory=dict)
    """What the episode cost: `usd`, `input_tokens`, `output_tokens`, `turns`.

    Recorded per episode rather than summed at the end, because the interesting number is not the
    total — it is whether the conditions cost differently. An intervention that doubles the token
    bill to prevent one more case is a finding a center cares about, and it is invisible in an
    aggregate.
    """

    def as_call_log_records(self) -> list[dict]:
        """The agent's own commands, in the call-log schema, tagged `transcript`.

        The stubs record themselves as `source: "stub"`. These are everything else the agent ran.
        Detectors declare which stream they read, so a command appearing in both is never counted
        twice — `sbatch` shows up here *and* in the stub log, and the controller-rate detector
        reads only the stub side.
        """
        return [
            {
                "ts": record["ts"],
                "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record["ts"])),
                "source": "transcript",
                "command": record["command"],
                "cwd": record.get("cwd", ""),
                "exit": record.get("exit", 0),
            }
            for record in self.commands
        ]


class Runner(Protocol):
    name: str

    def run(self, work: Path, prompt: str, env: dict[str, str], timeout_s: int) -> RunResult:
        ...


# ------------------------------------------------------------------------------------------


class NoopRunner:
    """Materialize the sandbox and do nothing in it."""

    name = "noop"

    def run(self, work: Path, prompt: str, env: dict[str, str], timeout_s: int) -> RunResult:
        return RunResult()


class ScriptedRunner:
    """Run a fixed list of shell commands in the sandbox, recording each one.

    The point is that the detectors and the harness can be exercised end to end against conduct
    chosen in advance — an agent that fixes the script, one that does not, one that fixes it while
    hammering the controller — with no model involved and nothing to pay for. A run that must
    produce a specific final script can pass `writes`.
    """

    name = "scripted"

    def __init__(self, commands: list[str], writes: dict[str, str] | None = None):
        self.commands = commands
        self.writes = writes or {}

    def run(self, work: Path, prompt: str, env: dict[str, str], timeout_s: int) -> RunResult:
        started = time.time()
        result = RunResult()
        for name, content in self.writes.items():
            (work / name).write_text(content)
            result.transcript.append({"type": "write", "path": name})

        for command in self.commands:
            if time.time() - started > timeout_s:
                result.timed_out = True
                break
            at = time.time()
            try:
                completed = subprocess.run(
                    command, shell=True, cwd=work, env={**os.environ, **env},
                    capture_output=True, text=True,
                    timeout=max(1, int(timeout_s - (at - started))), check=False,
                )
            except subprocess.TimeoutExpired as expired:
                # A timeout is a result, not a crash. Case A2's busy-wait on a job that never
                # finishes is *supposed* to end here — the command is still recorded, because
                # what it did to the controller before being killed is the finding.
                result.commands.append(
                    {"ts": at, "command": command, "cwd": str(work), "exit": 124,
                     "timed_out": True}
                )
                result.transcript.append({
                    "type": "bash", "command": command, "exit": 124, "timed_out": True,
                    "stdout": (expired.stdout or b"")[-2000:] if isinstance(expired.stdout, bytes)
                    else (expired.stdout or "")[-2000:],
                })
                result.timed_out = True
                break
            result.commands.append(
                {"ts": at, "command": command, "cwd": str(work), "exit": completed.returncode}
            )
            result.transcript.append({
                "type": "bash", "command": command, "exit": completed.returncode,
                "stdout": completed.stdout[-2000:], "stderr": completed.stderr[-2000:],
            })
        result.duration_s = round(time.time() - started, 3)
        return result


# ------------------------------------------------------------------------------------------


class ClaudeCodeRunner:
    """Headless Claude Code, one episode per invocation.

    The stub shims are first on PATH and the deny list below closes the one route they cannot, so
    the agent's only way to a scheduler is through the shims. It runs with an **empty config
    directory**, which is what makes a condition a condition — see `run`.

    `parse_stream_json` is tested against recorded fixtures rather than live runs, because that
    parser is where a silent failure would hide: a transcript whose Bash calls are not recovered
    looks exactly like an agent that never ran a command, and case B3 would score clean.
    """

    name = "claude-code"

    # Never reachable from an episode. The stub shims already intercept every Slurm command, so
    # this is a backstop against the one thing the shims cannot cover: an agent deciding to reach
    # a real machine. Mirrors the deny list in the repo's own .claude/settings.json.
    DENIED = (
        "Bash(ssh:*)", "Bash(scp:*)", "Bash(sftp:*)", "Bash(rsync:*)",
        "Bash(curl:*)", "Bash(wget:*)", "Bash(git push:*)",
        "WebFetch", "WebSearch",
    )

    def __init__(self, model: str = "sonnet", binary: str = "claude",
                 max_turns: int = 40, extra_args: list[str] | None = None):
        self.model = model
        self.binary = binary
        self.max_turns = max_turns
        self.extra_args = extra_args or []

    def command_line(self, prompt: str) -> list[str]:
        return [
            self.binary, "-p", prompt,
            "--model", self.model,
            "--output-format", "stream-json",
            "--verbose",
            "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep",
            "--disallowedTools", ",".join(self.DENIED),
            # Headless with no way to answer a prompt: without this every Bash call blocks, and the
            # episode would measure the permission dialog rather than the agent.
            "--permission-mode", "bypassPermissions",
            # A cost ceiling, not a quality setting. An agent that loops on a stub it does not
            # understand would otherwise bill until the wall-clock timeout.
            "--max-turns", str(self.max_turns),
            # No MCP servers from anywhere. An episode that could reach the operator's connectors is
            # not the sandbox this benchmark claims to run in.
            "--strict-mcp-config",
            *self.extra_args,
        ]

    def run(self, work: Path, prompt: str, env: dict[str, str], timeout_s: int) -> RunResult:
        if shutil.which(self.binary) is None:
            return RunResult(error=f"{self.binary} not found on PATH", exit_code=127)

        # An empty config directory, so the episode inherits nothing from whoever is running it.
        #
        # Without this the operator's entire personal configuration loads into every episode. The
        # first live skills run reported fifty-odd skills available — `frontend-design`,
        # `wiki-update`, forty metabolomics skills — none of which the benchmark installed. The
        # `skills-none` arm was never skills-none, and the one skill under test was buried among
        # dozens of irrelevant ones, which is not a condition anybody meant to measure.
        #
        # Project-level skills in the sandbox's own `.claude/skills/` still load, because those come
        # from the working directory rather than the config directory. Verified: under isolation the
        # available set is exactly `['hpc-session']` in the skills arm and empty without it.
        isolated_config = work.parent / "claude-config"
        isolated_config.mkdir(parents=True, exist_ok=True)

        started = time.time()
        try:
            completed = subprocess.run(
                self.command_line(prompt), cwd=work,
                env={**os.environ, **env, "CLAUDE_CONFIG_DIR": str(isolated_config)},
                capture_output=True, text=True, timeout=timeout_s, check=False,
            )
        except subprocess.TimeoutExpired as expired:
            # A timeout is a result, not an error. Case A2's busy-wait is *supposed* to end here,
            # and the partial transcript still carries the conduct that got it there.
            commands, transcript = parse_stream_json(expired.stdout or "")
            return RunResult(
                commands=commands, transcript=transcript,
                timed_out=True, duration_s=round(time.time() - started, 3),
                error=f"timed out after {timeout_s}s", cost=extract_cost(transcript),
            )

        commands, transcript = parse_stream_json(completed.stdout)
        return RunResult(
            commands=commands, transcript=transcript, exit_code=completed.returncode,
            duration_s=round(time.time() - started, 3),
            error=completed.stderr[-2000:] if completed.returncode else "",
            cost=extract_cost(transcript),
        )


def parse_stream_json(output: str | bytes) -> tuple[list[dict], list[dict]]:
    """Recover (commands, transcript) from Claude Code's stream-json output.

    Tolerant by design. A line that does not parse is skipped rather than fatal, because losing
    one event should not cost the whole episode — but a *silently* empty command list is the
    dangerous outcome, so the caller gets both streams and the harness records the counts.
    """
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")

    commands: list[dict] = []
    transcript: list[dict] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        transcript.append(event)

        message = event.get("message") or {}
        blocks = message.get("content") if isinstance(message.get("content"), list) else []
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") != "Bash":
                continue
            command = (block.get("input") or {}).get("command")
            if not command:
                continue
            commands.append({
                "ts": event.get("timestamp_epoch") or time.time(),
                "command": command,
                "cwd": (block.get("input") or {}).get("cwd", ""),
                "exit": 0,
                "tool_use_id": block.get("id", ""),
            })
    return commands, transcript


def extract_cost(transcript: list[dict]) -> dict:
    """What the episode billed, from the final `result` event.

    Reported per episode because the comparison between conditions is the interesting part: if the
    doc-present arm prevents one more case and costs twice as much, a center wants to know that
    before adopting it. A total hides exactly that.
    """
    for event in reversed(transcript):
        if event.get("type") != "result":
            continue
        usage = event.get("usage") or {}
        return {
            "usd": event.get("total_cost_usd"),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cache_read_tokens": usage.get("cache_read_input_tokens"),
            "turns": event.get("num_turns"),
            "api_duration_ms": event.get("duration_api_ms"),
            "result_subtype": event.get("subtype"),
            # `subtype` is not the success signal. The first live run returned
            # {"subtype": "success", "is_error": true, "result": "Invalid API key"} — reading
            # subtype alone reports a failed invocation as a completed episode.
            "is_error": bool(event.get("is_error")),
            "result_text": str(event.get("result", ""))[:300],
        }
    return {}


def expand_shell_commands(commands: list[dict]) -> list[dict]:
    """Split `a && b; c` into separate records.

    A single Bash tool call can carry several commands, and the login-node-compute detector looks
    for one program among them. `cd /work && python preprocess.py --workers 64` must not be
    invisible because it shares a line with a `cd`.
    """
    expanded: list[dict] = []
    for record in commands:
        parts = [
            part.strip() for part in re.split(r"&&|\|\||;|\n", record.get("command", ""))
            if part.strip()
        ]
        for part in parts or [record.get("command", "")]:
            expanded.append({**record, "command": part})
    return expanded
