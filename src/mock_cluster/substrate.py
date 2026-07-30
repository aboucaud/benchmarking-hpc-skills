"""Lifecycle and transport for a fresh Docker Slurm cluster."""

from __future__ import annotations

import fcntl
import io
import json
import os
import re
import shlex
import socket
import subprocess
import tarfile
import tempfile
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[1]
BASE_COMPOSE = REPO / "mock-cluster" / "compose.yaml"
OVERLAY_COMPOSE = PACKAGE / "compose.overlay.yaml"
DEVICE_COMPOSE = PACKAGE / "compose.device-auth.yaml"
PROJECT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,50}$")
MODEL = re.compile(r"^[A-Za-z0-9._-]+$")
DEVICE_AUTH_VOLUME = "benchmarking-hpc-codex-device-auth"


class SubstrateError(RuntimeError):
    pass


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: bytes
    stderr: bytes

    @property
    def text(self) -> str:
        return self.stdout.decode(errors="replace")


def free_local_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class DockerSlurmSubstrate:
    """One sequential, fresh Compose project.

    A host lock prevents two laptop-sized clusters from being started by this
    package at once.  Images are cached globally; containers and volumes are
    unique to the episode and removed on exit.
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        auth_mode: str = "gateway",
        model: str = "gpt-5.6-terra",
        build: bool = True,
        keep: bool = False,
        startup_timeout: int = 300,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        self.project = project or f"hpcbench_{suffix}"
        if not PROJECT.fullmatch(self.project):
            raise ValueError(f"invalid Compose project name: {self.project!r}")
        if auth_mode not in {"gateway", "device"}:
            raise ValueError("auth_mode must be gateway or device")
        if not MODEL.fullmatch(model):
            raise ValueError(f"invalid model slug: {model!r}")
        self.auth_mode = auth_mode
        self.model = model
        self.build_images = build
        self.keep = keep
        self.startup_timeout = startup_timeout
        self.ssh_port = free_local_port()
        self._unpublished_login_port = free_local_port()
        self.started = False
        self._temporary = tempfile.TemporaryDirectory(prefix=f"{self.project}-")
        self.temp = Path(self._temporary.name)
        self._lock_handle = None
        self.key = self.temp / "episode_ed25519"
        self.environment = {
            **os.environ,
            "CODEX_MODEL": model,
            # Docker Desktop does not publish a port for a container attached
            # only to an internal network. The inherited login mapping is
            # therefore kept on a different port while ssh-gateway publishes
            # the actual host-facing endpoint.
            "SSH_PORT": str(self._unpublished_login_port),
            "MOCK_CLUSTER_SSH_PORT": str(self.ssh_port),
            "COMPOSE_PROJECT_NAME": self.project,
            "MOCK_SLURM_CLIENT_IMAGE": "mock-slurm-client:25-11-2-1",
            "MOCK_SLURM_SUPPORT_IMAGE": "mock-slurm-support:25-11-2-1",
            "MOCK_CODEX_AUTH_VOLUME": DEVICE_AUTH_VOLUME,
        }

    @property
    def compose_files(self) -> list[Path]:
        files = [BASE_COMPOSE, OVERLAY_COMPOSE]
        if self.auth_mode == "device":
            files.append(DEVICE_COMPOSE)
        return files

    def compose_argv(self, *arguments: str) -> list[str]:
        argv = ["docker", "compose", "--project-name", self.project]
        for path in self.compose_files:
            argv.extend(["-f", str(path)])
        return [*argv, *arguments]

    def run(
        self,
        argv: Iterable[str],
        *,
        input_bytes: bytes | None = None,
        timeout: int | None = None,
        check: bool = True,
    ) -> CommandResult:
        command = list(argv)
        try:
            completed = subprocess.run(
                command,
                input=input_bytes,
                capture_output=True,
                timeout=timeout,
                env=self.environment,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SubstrateError(
                f"command failed to run: {shlex.join(command)}: {error}"
            ) from error
        result = CommandResult(
            command, completed.returncode, completed.stdout, completed.stderr
        )
        if check and completed.returncode:
            detail = completed.stderr.decode(errors="replace")[-4000:]
            raise SubstrateError(
                f"command exited {completed.returncode}: {shlex.join(command)}\n{detail}"
            )
        return result

    def compose(
        self,
        *arguments: str,
        input_bytes: bytes | None = None,
        timeout: int | None = None,
        check: bool = True,
    ) -> CommandResult:
        return self.run(
            self.compose_argv(*arguments),
            input_bytes=input_bytes,
            timeout=timeout,
            check=check,
        )

    def acquire(self) -> None:
        lock = Path(tempfile.gettempdir()) / "benchmarking-hpc-mock-cluster.lock"
        self._lock_handle = lock.open("w")
        try:
            fcntl.flock(self._lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SubstrateError(
                "another mock-cluster episode is running; laptop runs are intentionally sequential"
            ) from error

    def build(self) -> None:
        # Build the existing base once, then the two thin derived images.  This
        # avoids a race in which a Dockerfile FROMs the local base before
        # Compose has exported it.
        self.run(
            [
                "docker",
                "compose",
                "--project-name",
                self.project,
                "-f",
                str(BASE_COMPOSE),
                "build",
                "login",
            ],
            timeout=1200,
        )
        self.compose("build", "login", "observer", timeout=600)

    def start(self) -> None:
        self.acquire()
        if self.auth_mode == "device":
            self.ensure_device_auth_volume()
        if self.build_images:
            self.build()
        self.compose(
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            str(self.startup_timeout),
            timeout=self.startup_timeout + 120,
        )
        self.started = True
        self.generate_ssh_key()
        self.install_ssh_key()
        self.wait_for_ssh()
        self.enable_step_logging()

    def ensure_device_auth_volume(self) -> None:
        """Create the deliberately persistent, login-only Codex auth volume."""
        self.run(["docker", "volume", "create", DEVICE_AUTH_VOLUME], timeout=30)

    def __enter__(self) -> DockerSlurmSubstrate:
        self.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        if self.started and not self.keep:
            self.cancel_all(check=False)
            self.compose(
                "down",
                "--volumes",
                "--remove-orphans",
                timeout=120,
                check=False,
            )
        self.started = False
        if self._lock_handle is not None:
            fcntl.flock(self._lock_handle, fcntl.LOCK_UN)
            self._lock_handle.close()
            self._lock_handle = None
        if not self.keep:
            self._temporary.cleanup()

    def generate_ssh_key(self) -> None:
        self.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                f"{self.project}-ephemeral",
                "-f",
                str(self.key),
            ],
            timeout=30,
        )
        os.chmod(self.key, 0o600)

    def exec(
        self,
        service: str,
        argv: list[str],
        *,
        user: str | None = None,
        input_bytes: bytes | None = None,
        timeout: int = 60,
        check: bool = True,
    ) -> CommandResult:
        arguments = ["exec", "-T"]
        if user:
            arguments.extend(["--user", user])
        arguments.extend([service, *argv])
        return self.compose(
            *arguments,
            input_bytes=input_bytes,
            timeout=timeout,
            check=check,
        )

    def install_ssh_key(self) -> None:
        public = self.key.with_suffix(".pub").read_bytes()
        code = (
            "import os,pathlib,sys;"
            "p=pathlib.Path('/home/demo_user/.ssh');p.mkdir(parents=True,exist_ok=True);"
            "p.chmod(0o700);"
            "k=p/'authorized_keys';k.write_bytes(sys.stdin.buffer.read());k.chmod(0o600);"
            "os.chown(p,5001,5001);os.chown(k,5001,5001)"
        )
        self.exec("login", ["python3", "-c", code], input_bytes=public)

    def ssh_argv(self, remote: str, *, tty: bool = False) -> list[str]:
        return [
            "ssh",
            "-tt" if tty else "-T",
            "-i",
            str(self.key),
            "-p",
            str(self.ssh_port),
            "-o",
            "BatchMode=yes" if not tty else "BatchMode=no",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            f"UserKnownHostsFile={self.temp / 'known_hosts'}",
            "-o",
            "ConnectTimeout=5",
            "demo_user@127.0.0.1",
            remote,
        ]

    def ssh(
        self,
        argv: list[str],
        *,
        cwd: str = "/episode/work",
        environment: dict[str, str] | None = None,
        input_bytes: bytes | None = None,
        timeout: int = 60,
        check: bool = True,
    ) -> CommandResult:
        env = {
            "HPCBENCH_EPISODE": "harness",
            **(environment or {}),
        }
        assignments = [f"{key}={shlex.quote(value)}" for key, value in env.items()]
        remote = " ".join(
            [
                f"cd {shlex.quote(cwd)}",
                "&&",
                "env",
                *assignments,
                shlex.join(argv),
            ]
        )
        return self.run(
            self.ssh_argv(remote),
            input_bytes=input_bytes,
            timeout=timeout,
            check=check,
        )

    def ssh_shell(
        self, command: str, *, timeout: int = 60, check: bool = True
    ) -> CommandResult:
        remote = f"cd /episode/work && {command}"
        return self.run(self.ssh_argv(remote), timeout=timeout, check=check)

    def ssh_interactive(self, argv: list[str]) -> int:
        remote = shlex.join(argv)
        return subprocess.call(self.ssh_argv(remote, tty=True), env=self.environment)

    def wait_for_ssh(self) -> None:
        deadline = time.time() + 60
        last = ""
        while time.time() < deadline:
            result = self.ssh(["true"], timeout=10, check=False)
            if result.returncode == 0:
                return
            last = result.stderr.decode(errors="replace")[-500:]
            time.sleep(1)
        raise SubstrateError(f"SSH did not become ready: {last}")

    def enable_step_logging(self) -> None:
        self.exec(
            "slurmctld",
            ["/usr/bin/scontrol", "setdebugflags", "+Steps"],
            timeout=30,
        )

    def materialize(self, files: dict[str, bytes]) -> None:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for name, content in sorted(files.items()):
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"unsafe workspace path: {name}")
                info = tarfile.TarInfo(path.as_posix())
                info.size = len(content)
                info.mode = 0o755 if content.startswith(b"#!") else 0o644
                archive.addfile(info, io.BytesIO(content))
        code = """
import os,pathlib,shutil,sys,tarfile
root=pathlib.Path('/episode/work')
for child in root.iterdir():
    shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|*') as archive:
    for member in archive:
        target=(root/member.name).resolve()
        if root.resolve() not in target.parents and target != root.resolve():
            raise SystemExit('unsafe archive member')
        if member.issym() or member.islnk() or member.isdev():
            raise SystemExit('unsupported archive member')
        archive.extract(member,root)
for current,dirs,files in os.walk(root):
    os.chown(current,5001,5001)
    for name in dirs+files:
        os.chown(os.path.join(current,name),5001,5001)
"""
        self.exec(
            "login",
            ["python3", "-c", code],
            input_bytes=buffer.getvalue(),
            timeout=60,
        )

    def materialize_agent_document(self, content: bytes) -> None:
        code = (
            "import os,pathlib,sys;"
            "p=pathlib.Path('/agents');p.mkdir(parents=True,exist_ok=True);"
            "p.chmod(0o755);"
            "d=p/'INSTRUCTIONS.md';d.write_bytes(sys.stdin.buffer.read());"
            "d.chmod(0o444);os.chown(p,0,0);os.chown(d,0,0)"
        )
        self.exec(
            "login",
            ["python3", "-c", code],
            input_bytes=content,
            timeout=30,
        )

    def collect_workspace(self) -> dict[str, bytes]:
        code = """
import sys,tarfile
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
    archive.add('/episode/work',arcname='.')
"""
        result = self.exec("login", ["python3", "-c", code], timeout=60)
        files: dict[str, bytes] = {}
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:*") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                path = Path(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise SubstrateError(f"unsafe collected path: {member.name}")
                handle = archive.extractfile(member)
                if handle is not None:
                    files[path.as_posix().removeprefix("./")] = handle.read()
        return files

    def prepare_codex_home(self) -> None:
        if self.auth_mode == "device":
            code = (
                "import os,pathlib;"
                "p=pathlib.Path('/home/demo_user/.codex');"
                "p.mkdir(parents=True,exist_ok=True);"
                "p.chmod(0o700);os.chown(p,5001,5001)"
            )
            self.exec("login", ["python3", "-c", code])
            return
        config = f"""model = "{self.model}"
model_provider = "benchmark_gateway"
project_root_markers = []

[model_providers.benchmark_gateway]
name = "credential-isolating benchmark gateway"
base_url = "http://credential-gateway:8080/v1"
wire_api = "responses"
supports_websockets = false
request_max_retries = 2
stream_max_retries = 2
stream_idle_timeout_ms = 300000
"""
        code = (
            "import os,pathlib,sys;"
            "p=pathlib.Path('/run/mock-codex');p.mkdir(parents=True,exist_ok=True);"
            "p.chmod(0o700);os.chown(p,5001,5001);"
            "c=p/'config.toml';c.write_bytes(sys.stdin.buffer.read());"
            "c.chmod(0o600);os.chown(c,5001,5001)"
        )
        self.exec("login", ["python3", "-c", code], input_bytes=config.encode())
        ready = self.exec(
            "login",
            [
                "python3",
                "-c",
                (
                    "import urllib.request;"
                    "assert urllib.request.urlopen("
                    "'http://credential-gateway:8080/ready',timeout=2).status==200"
                ),
            ],
            timeout=10,
            check=False,
        )
        if ready.returncode:
            raise SubstrateError(
                "gateway auth requires OPENAI_API_KEY in the host environment"
            )

    def device_login(self) -> None:
        if self.auth_mode != "device":
            raise SubstrateError("device login requires auth_mode=device")
        self.prepare_codex_home()
        if self.ssh_interactive(
            [
                "env",
                "CODEX_HOME=/home/demo_user/.codex",
                "codex",
                "login",
                "--device-auth",
            ]
        ):
            raise SubstrateError("Codex device login failed")
        if not self.device_auth_status():
            raise SubstrateError("Codex did not report a logged-in device session")

    def device_auth_status(self) -> bool:
        if self.auth_mode != "device":
            return False
        self.prepare_codex_home()
        result = self.ssh(
            [
                "env",
                "CODEX_HOME=/home/demo_user/.codex",
                "codex",
                "login",
                "status",
            ],
            cwd="/home/demo_user",
            timeout=30,
            check=False,
        )
        return result.returncode == 0

    def observer_events(self, episode_id: str | None = None) -> list[dict]:
        code = (
            "import pathlib;"
            "p=pathlib.Path('/observer/events.jsonl');"
            "print(p.read_text() if p.exists() else '',end='')"
        )
        result = self.exec("observer", ["python3", "-c", code])
        events = []
        for line in result.text.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if episode_id is None or event.get("episode_id") == episode_id:
                events.append(event)
        return events

    def gateway_events(self) -> list[dict]:
        code = (
            "import pathlib;"
            "p=pathlib.Path('/observer/gateway-events.jsonl');"
            "print(p.read_text() if p.exists() else '',end='')"
        )
        result = self.exec("credential-gateway", ["python3", "-c", code])
        events = []
        for line in result.text.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def submitted_job_ids(self, episode_id: str | None = None) -> list[str]:
        return list(
            dict.fromkeys(
                event["result_job_id"]
                for event in self.observer_events(episode_id)
                if event.get("command") == "sbatch"
                and event.get("result_job_id")
            )
        )

    def accounting(self, job_ids: list[str]) -> list[dict[str, str]]:
        if not job_ids:
            return []
        # slurmctld already bridges the scheduler and accounting networks.
        # Keeping the observer internal-only avoids granting that service
        # general egress merely so sacct can reach slurmdbd.
        result = self.exec(
            "slurmctld",
            [
                "/usr/bin/sacct",
                "--noheader",
                "--parsable2",
                "--allocations",
                "--jobs",
                ",".join(job_ids),
                "--format",
                "JobIDRaw,State,ExitCode,Elapsed,ReqCPUS,ReqMem,NodeList",
            ],
            timeout=30,
            check=False,
        )
        rows = []
        fields = ["job_id", "state", "exit_code", "elapsed", "req_cpus", "req_mem", "nodes"]
        for line in result.text.splitlines():
            values = line.split("|")
            if len(values) >= len(fields):
                rows.append(dict(zip(fields, values, strict=False)))
        return rows

    def controller_log(self, job_ids: list[str]) -> str:
        code = (
            "from pathlib import Path;"
            "p=Path('/var/log/slurm/slurmctld.log');"
            "print(''.join(p.read_text(errors='replace').splitlines(True)[-2000:])"
            " if p.exists() else '',end='')"
        )
        result = self.exec("slurmctld", ["python3", "-c", code], check=False)
        text = result.text
        if not job_ids:
            return text[-20000:]
        selected = [
            line
            for line in text.splitlines()
            if any(re.search(rf"(?<!\d){re.escape(job)}(?!\d)", line) for job in job_ids)
        ]
        return "\n".join(selected)[-20000:] + ("\n" if selected else "")

    def cancel_all(self, *, check: bool = True) -> None:
        self.exec(
            "observer",
            ["/usr/bin/scancel", "--user", "demo_user"],
            timeout=30,
            check=check,
        )

    def wait_for_jobs(self, job_ids: list[str], timeout: int = 20) -> list[dict[str, str]]:
        terminal = {
            "BOOT_FAIL",
            "CANCELLED",
            "COMPLETED",
            "DEADLINE",
            "FAILED",
            "NODE_FAIL",
            "OUT_OF_MEMORY",
            "PREEMPTED",
            "TIMEOUT",
        }
        deadline = time.time() + timeout
        rows: list[dict[str, str]] = []
        while time.time() < deadline:
            rows = self.accounting(job_ids)
            states = {
                re.split(r"[ +]", row["state"], maxsplit=1)[0] for row in rows
            }
            if rows and states and states <= terminal:
                break
            time.sleep(1)
        return rows

    def container_inspect(self, service: str) -> dict:
        identifier = self.compose("ps", "-q", service).text.strip()
        if not identifier:
            raise SubstrateError(f"no container for service {service}")
        result = self.run(["docker", "inspect", identifier])
        return json.loads(result.text)[0]

    def security_preflight(self) -> dict:
        login = self.container_inspect("login")
        mounts = [item.get("Destination") for item in login.get("Mounts", [])]
        if "/observer" in mounts or "/var/run/docker.sock" in mounts:
            raise SubstrateError("agent container exposes observer evidence or Docker API")
        environment = login.get("Config", {}).get("Env", [])
        if any(item.startswith("OPENAI_API_KEY=") for item in environment):
            raise SubstrateError("agent container exposes the upstream API credential")
        resources = {}
        for service in (
            "login",
            "c1",
            "c2",
            "c3",
            "observer",
            "credential-gateway",
            "ssh-gateway",
        ):
            inspected = self.container_inspect(service)
            resources[service] = {
                "nano_cpus": inspected["HostConfig"].get("NanoCpus", 0),
                "memory": inspected["HostConfig"].get("Memory", 0),
                "pids_limit": inspected["HostConfig"].get("PidsLimit", 0),
            }
            if service in {
                "c1",
                "c2",
                "c3",
                "observer",
                "credential-gateway",
                "ssh-gateway",
            }:
                destinations = {
                    item.get("Destination") for item in inspected.get("Mounts", [])
                }
                if "/home/demo_user/.codex" in destinations:
                    raise SubstrateError(
                        f"Codex device credentials are exposed to {service}"
                    )
        return {"login_mounts": mounts, "resources": resources}
