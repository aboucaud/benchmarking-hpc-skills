"""Command line for monitored Docker Slurm episodes."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

from .episode import (
    CASES,
    REPO,
    Condition,
    DockerEpisode,
)
from .qualification import qualify, write_report
from .substrate import DockerSlurmSubstrate

CONDITIONS = (
    "doc-absent_skills-none",
    "doc-absent_skills-good",
    "doc-present_skills-none",
    "doc-present_skills-good",
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    qualification = commands.add_parser(
        "qualify", help="run no-model path, floor, ceiling, and security checks"
    )
    qualification.add_argument("--no-build", action="store_true")
    qualification.add_argument("--output", type=Path)

    auth = commands.add_parser(
        "auth",
        help="perform one-time Codex device login in the Slurm login node",
    )
    auth.add_argument("--model", default="gpt-5.6-terra")
    auth.add_argument("--no-build", action="store_true")

    run = commands.add_parser("run", help="run one case or a condition matrix")
    run.add_argument("case", help="case id, or 'all'")
    run.add_argument("--substrate", default="docker-slurm", choices=("docker-slurm",))
    run.add_argument("--runner", default="codex-exec", choices=("codex-exec",))
    run.add_argument("--model", default="gpt-5.6-terra")
    run.add_argument("--auth-mode", default="gateway", choices=("gateway", "device"))
    run.add_argument(
        "--device-login",
        action="store_true",
        help="perform interactive device authentication after the fresh cluster starts",
    )
    run.add_argument("--condition", choices=CONDITIONS)
    run.add_argument("--matrix", action="store_true")
    run.add_argument("--seeds", type=int, default=1)
    run.add_argument("--skills", type=Path)
    run.add_argument("--timeout", type=int, default=300)
    run.add_argument("--no-build", action="store_true")
    run.add_argument(
        "--include-drafts",
        action="store_true",
        help="include draft cases when CASE is 'all'",
    )
    run.add_argument(
        "--results",
        type=Path,
        default=REPO / "results" / "mock-cluster",
    )
    return root


def run_episodes(arguments: argparse.Namespace) -> int:
    if arguments.case != "all" and not (CASES / arguments.case).is_dir():
        raise SystemExit(f"unknown case: {arguments.case}")
    if arguments.seeds < 1:
        raise SystemExit("--seeds must be positive")
    if arguments.device_login and arguments.auth_mode != "device":
        raise SystemExit("--device-login requires --auth-mode device")

    if arguments.matrix:
        conditions = Condition.matrix(with_skills=bool(arguments.skills))
    elif arguments.condition:
        conditions = [Condition.from_label(arguments.condition)]
    else:
        conditions = [Condition()]
    if arguments.case == "all":
        case_ids = []
        for path in sorted(CASES.iterdir()):
            metadata = path / "case.yaml"
            if not metadata.is_file():
                continue
            case = yaml.safe_load(metadata.read_text())
            if case.get("draft") and not arguments.include_drafts:
                continue
            case_ids.append(path.name)
    else:
        case_ids = [arguments.case]
    arguments.results.mkdir(parents=True, exist_ok=True)
    artifacts = arguments.results / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    destination = (
        arguments.results / f"episodes-{time.strftime('%Y%m%dT%H%M%S')}.jsonl"
    )
    built = arguments.no_build
    first_episode = True
    with destination.open("w", encoding="utf-8") as stream:
        for case_id in case_ids:
            for condition in conditions:
                for seed in range(arguments.seeds):
                    episode = DockerEpisode(
                        case_id=case_id,
                        condition=condition,
                        seed=seed,
                        model=arguments.model,
                        auth_mode=arguments.auth_mode,
                        skills_path=arguments.skills,
                        timeout_s=arguments.timeout,
                        build=not built,
                        device_login=arguments.device_login and first_episode,
                    ).run()
                    built = True
                    first_episode = False
                    stream.write(json.dumps(episode, sort_keys=True) + "\n")
                    stream.flush()
                    stem = f"{case_id}__{condition.label}__seed{seed}"
                    (artifacts / f"{stem}.json").write_text(
                        json.dumps(episode, indent=2, sort_keys=True) + "\n"
                    )
                    print(
                        f"{case_id} {condition.label} seed{seed}: "
                        f"validity={episode['validity']} "
                        f"static={episode['l1']['static']['verdict']} "
                        f"runtime={episode['l1']['runtime']['verdict']} "
                        f"prevented={episode['l1']['prevented']}",
                        flush=True,
                    )
    print(
        "pilot only: case results are not publishable until administrator sign-off\n"
        f"written to {destination}"
    )
    return 0


def authenticate(arguments: argparse.Namespace) -> int:
    substrate = DockerSlurmSubstrate(
        auth_mode="device",
        model=arguments.model,
        build=not arguments.no_build,
    )
    try:
        substrate.start()
        substrate.security_preflight()
        if substrate.device_auth_status():
            print("Codex is already authenticated in the persistent login-node volume.")
            return 0
        substrate.device_login()
        print(
            "Codex device authentication is ready. The login-only Docker volume "
            "will be reused by later `run --auth-mode device` commands."
        )
        return 0
    finally:
        substrate.close()


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.command == "qualify":
        report = qualify(build=not arguments.no_build)
        if arguments.output:
            write_report(report, arguments.output)
            print(arguments.output)
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if arguments.command == "auth":
        return authenticate(arguments)
    if arguments.command == "run":
        return run_episodes(arguments)
    return 2


if __name__ == "__main__":
    sys.exit(main())
