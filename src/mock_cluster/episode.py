"""Condition materialization, evidence collection, and episode orchestration."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .runner import CodexExecRunner, RunResult
from .score import score_episode
from .substrate import DockerSlurmSubstrate


PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[1]
BENCHMARK = REPO / "benchmark"
CASES = BENCHMARK / "cases"
GENERATED = BENCHMARK / "generated"
VISIBLE = ("job.sh", "prompt.md")
WITHHELD = ("case.yaml", "reference.sh", "rubric.md")


@dataclass(frozen=True)
class Condition:
    doc: bool = False
    skills: str = "none"

    @property
    def label(self) -> str:
        return f"doc-{'present' if self.doc else 'absent'}_skills-{self.skills}"

    @classmethod
    def from_label(cls, label: str) -> "Condition":
        doc, skills = label.split("_", 1)
        return cls(doc == "doc-present", skills.removeprefix("skills-"))

    @classmethod
    def matrix(cls, with_skills: bool) -> list["Condition"]:
        tiers = ("none", "good") if with_skills else ("none",)
        return [cls(doc, tier) for doc in (False, True) for tier in tiers]


def withheld_lines() -> set[str]:
    lines: set[str] = set()
    for case in CASES.iterdir():
        if not case.is_dir():
            continue
        for name in WITHHELD:
            path = case / name
            if not path.exists():
                continue
            lines.update(
                line.strip()
                for line in path.read_text().splitlines()
                if len(line.strip()) > 40
            )
    return lines


def materialize_condition(
    case_dir: Path,
    condition: Condition,
    skills_path: Path | None = None,
) -> dict[str, bytes]:
    files: dict[str, bytes] = {
        name: (case_dir / name).read_bytes() for name in VISIBLE
    }
    assets = case_dir / "assets"
    if assets.is_dir():
        for path in sorted(assets.iterdir()):
            if path.is_file():
                files[path.name] = path.read_bytes()
    if condition.doc:
        files["INSTRUCTIONS.md"] = (GENERATED / "INSTRUCTIONS.md").read_bytes()
    if condition.skills != "none":
        if skills_path is None or not skills_path.is_dir():
            raise ValueError(
                f"condition {condition.label} requires a real --skills directory"
            )
        manifests = list(skills_path.rglob("SKILL.md"))
        if not manifests:
            raise ValueError(f"{skills_path} contains no SKILL.md")
        for path in sorted(skills_path.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(skills_path)
            if any(part in {".git", ".github", "tests", "__pycache__"} for part in relative.parts):
                continue
            target = Path(".agents") / "skills" / skills_path.name / relative
            files[target.as_posix()] = path.read_bytes()

    leaked = withheld_lines()
    for name, content in files.items():
        if Path(name).name in WITHHELD:
            raise AssertionError(f"withheld filename leaked: {name}")
        try:
            text = content.decode()
        except UnicodeDecodeError:
            continue
        overlap = {line.strip() for line in text.splitlines()} & leaked
        if name not in VISIBLE and overlap:
            raise AssertionError(f"{name} contains withheld benchmark text")
    return files


def artifact_text(files: dict[str, bytes]) -> dict[str, str]:
    result = {}
    for name, content in sorted(files.items()):
        try:
            result[name] = content.decode()
        except UnicodeDecodeError:
            result[name] = f"<binary sha256={hashlib.sha256(content).hexdigest()}>"
    return result


class DockerEpisode:
    def __init__(
        self,
        *,
        case_id: str,
        condition: Condition,
        seed: int = 0,
        model: str = "gpt-5.6-terra",
        auth_mode: str = "gateway",
        skills_path: Path | None = None,
        timeout_s: int = 300,
        build: bool = True,
        device_login: bool = False,
    ) -> None:
        self.case_id = case_id
        self.condition = condition
        self.seed = seed
        self.model = model
        self.auth_mode = auth_mode
        self.skills_path = skills_path
        self.timeout_s = timeout_s
        self.build = build
        self.login_requested = device_login

    def run(self, runner: CodexExecRunner | None = None) -> dict[str, Any]:
        case_dir = CASES / self.case_id
        if not case_dir.is_dir():
            raise ValueError(f"unknown case: {self.case_id}")
        case = yaml.safe_load((case_dir / "case.yaml").read_text())
        limits = json.loads((GENERATED / "detectors.json").read_text())
        files = materialize_condition(case_dir, self.condition, self.skills_path)
        episode_id = (
            f"{self.case_id}/{self.condition.label}/seed{self.seed}/"
            f"{int(time.time())}"
        )
        started = time.time()
        substrate = DockerSlurmSubstrate(
            auth_mode=self.auth_mode,
            model=self.model,
            build=self.build,
        )
        run_result = RunResult()
        final_files: dict[str, bytes] = {}
        events: list[dict] = []
        accounting: list[dict] = []
        controller_log = ""
        gateway_events: list[dict] = []
        security: dict[str, Any] = {}
        try:
            substrate.start()
            security = substrate.security_preflight()
            substrate.materialize(files)
            path = substrate.ssh_shell("command -v srun").text.strip()
            if path != "/usr/bin/srun":
                raise RuntimeError(f"srun interception is not first on PATH: {path}")
            if self.auth_mode == "device" and self.login_requested:
                substrate.device_login()
            elif self.auth_mode == "device" and not substrate.device_auth_status():
                raise RuntimeError(
                    "no persisted Codex device login; run "
                    "`python -m src.mock_cluster auth` once"
                )
            active_runner = runner or CodexExecRunner(self.model)
            prompt = (case_dir / "prompt.md").read_text().strip()
            run_result = active_runner.run(
                substrate, prompt, episode_id, self.timeout_s
            )
            time.sleep(1)
            final_files = substrate.collect_workspace()
            # Every episode owns a fresh observer volume, so collect the full
            # record. The agent-visible episode label remains useful metadata,
            # but cannot hide an event by changing its environment.
            events = substrate.observer_events()
            job_ids = substrate.submitted_job_ids()
            accounting = substrate.accounting(job_ids)
            controller_log = substrate.controller_log(job_ids)
            gateway_events = substrate.gateway_events()
            substrate.cancel_all(check=False)
            terminal = substrate.wait_for_jobs(job_ids, timeout=10)
            if terminal:
                accounting = terminal
            events = substrate.observer_events()
        finally:
            substrate.close()

        l1 = score_episode(
            case=case,
            limits=limits,
            original_job=(case_dir / "job.sh").read_text(),
            files=final_files,
            events=events,
            commands=run_result.commands,
        )
        acted = bool(run_result.transcript or run_result.commands)
        validity = "ok" if acted and not run_result.timed_out else (
            "partial" if acted else "invalid"
        )
        review = str(case.get("review_status", "unknown"))
        return {
            "schema_version": 1,
            "substrate": "docker-slurm",
            "runner": getattr(runner, "name", "codex-exec"),
            "case": self.case_id,
            "case_review_status": review,
            "administrator_signoff": review == "signed-off",
            "publishable_evidence": review == "signed-off",
            "condition": {
                "doc": self.condition.doc,
                "skills": self.condition.skills,
                "label": self.condition.label,
            },
            "seed": self.seed,
            "model": self.model,
            "auth_mode": self.auth_mode,
            "episode_id": episode_id,
            "duration_s": round(time.time() - started, 3),
            "validity": validity,
            "agent": {
                "exit_code": run_result.exit_code,
                "timed_out": run_result.timed_out,
                "error": run_result.error,
                "cost": run_result.cost,
                "final_message": run_result.final_message,
                "commands": run_result.commands,
                "transcript": run_result.transcript,
            },
            "evidence": {
                "input_sha256": {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in sorted(files.items())
                },
                "final_files": artifact_text(final_files),
                "observer": events,
                "gateway": gateway_events,
                "accounting": accounting,
                "controller_log": controller_log,
                "security_preflight": security,
            },
            "l1": l1,
        }


def write_episode_artifacts(
    episode: dict[str, Any], results: Path
) -> tuple[Path, Path]:
    results.mkdir(parents=True, exist_ok=True)
    artifacts = results / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    stem = (
        f"{episode['case']}__{episode['condition']['label']}__"
        f"seed{episode['seed']}__{int(time.time())}"
    )
    artifact = artifacts / f"{stem}.json"
    artifact.write_text(json.dumps(episode, indent=2, sort_keys=True) + "\n")
    record = results / f"episodes-{time.strftime('%Y%m%dT%H%M%S')}.jsonl"
    record.write_text(json.dumps(episode, sort_keys=True) + "\n")
    return record, artifact
