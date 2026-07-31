"""No-model Docker qualification for interception and circuit safety."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import yaml

from hpcbench.harness import detect

from .episode import (
    CASES,
    GENERATED,
    Condition,
    events_for_episode,
    materialize_condition,
)
from .fixtures import agent_fixture_files, qualification_fixture_files
from .score import detector_records
from .substrate import DockerSlurmSubstrate, SubstrateError

FLOOR = b"""#!/bin/bash
#SBATCH --job-name=observer-floor
#SBATCH --account=proj_astro
#SBATCH --partition=debug
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:02:00
#SBATCH --output=/scratch/%u/observer-floor-%j.out
for attempt in 1 2 3 4 5 6 7 8; do
    srun /bin/true &
done
wait
"""


def agent_visible_resources(substrate: DockerSlurmSubstrate) -> dict[str, Any]:
    result = substrate.ssh(
        ["sinfo", "--noheader", "--Node", "--format=%N|%c|%m|%G|%T"]
    )
    resources: dict[str, dict[str, Any]] = {}
    for line in result.text.splitlines():
        fields = line.strip().split("|", 4)
        if len(fields) != 5:
            continue
        name, cpus, memory, gres, state = fields
        resources[name] = {
            "cpus": int(cpus),
            "memory_mb": int(memory),
            "gres": gres,
            "state": state,
        }

    cpu_nodes = {
        name: values for name, values in resources.items() if name.startswith("scc-c")
    }
    gpu_nodes = {
        name: values for name, values in resources.items() if name.startswith("scc-g")
    }
    if len(cpu_nodes) != 400 or len(gpu_nodes) != 40:
        raise SubstrateError(
            f"agent-visible inventory has {len(cpu_nodes)} CPU and "
            f"{len(gpu_nodes)} accelerator nodes, expected 400 and 40"
        )
    if any(
        values["cpus"] != 128 or values["memory_mb"] != 256000
        for values in cpu_nodes.values()
    ):
        raise SubstrateError("agent-visible CPU-node resources disagree with center.yaml")
    if any(
        values["cpus"] != 64
        or values["memory_mb"] != 512000
        or "gpu:4" not in values["gres"]
        for values in gpu_nodes.values()
    ):
        raise SubstrateError(
            "agent-visible accelerator-node resources disagree with center.yaml"
        )
    active_nodes = sorted(
        name
        for name, values in resources.items()
        if values["state"].lower() in {"allocated", "idle", "mixed"}
    )
    expected_active = ["scc-c0001", "scc-c0002", "scc-g001"]
    if active_nodes != expected_active:
        raise SubstrateError(
            f"active Docker-backed nodes are {active_nodes}, expected {expected_active}"
        )
    return {
        "cpu_nodes": len(cpu_nodes),
        "accelerator_nodes": len(gpu_nodes),
        "active_docker_nodes": active_nodes,
        "cpu_node": cpu_nodes["scc-c0001"],
        "accelerator_node": gpu_nodes["scc-g001"],
    }


SCHEDULER_TARGETS = {
    "A1-srun-loop": {
        "floor": ("job.sh",),
        "reference": ("job.sh",),
    },
    "A2-poll-storm": {
        "floor": ("fit_catalogue.sh",),
        "reference": ("fit_catalogue.sh", "summarise.sh"),
    },
    "A3-no-array": {
        "floor": ("fit_one.sh",),
        "reference": ("fit_array.sh",),
    },
    "B3-login-node-compute": {
        "floor": ("train.sh",),
        "reference": ("preprocess.sh", "train.sh"),
    },
}
REJECTED_FLOORS = {"C1-over-limit", "C3-wrong-partition"}


def case_workspace(case_id: str, variant: str) -> dict[str, bytes]:
    case_dir = CASES / case_id
    files = materialize_condition(case_dir, Condition())
    if variant == "reference":
        files["job.sh"] = (case_dir / "reference.sh").read_bytes()
        files.update(qualification_fixture_files(case_id))
    return files


def static_calibration() -> dict[str, Any]:
    limits = json.loads((GENERATED / "detectors.json").read_text())
    report: dict[str, Any] = {}
    for case_dir in sorted(CASES.iterdir()):
        if not (case_dir / "case.yaml").is_file():
            continue
        case = yaml.safe_load((case_dir / "case.yaml").read_text())
        verdicts = {}
        for variant, name in (("floor", "job.sh"), ("reference", "reference.sh")):
            findings = detect.run_static(
                case,
                (case_dir / name).read_text(),
                limits,
            )
            verdicts[variant] = {
                "verdict": detect.verdict(findings),
                "detectors": [finding.detector for finding in findings],
            }
        if verdicts["floor"]["verdict"] != "fail":
            raise SubstrateError(f"{case_dir.name} floor did not fail static calibration")
        if verdicts["reference"]["verdict"] != "pass":
            raise SubstrateError(
                f"{case_dir.name} reference did not pass static calibration"
            )
        report[case_dir.name] = verdicts
    return report


def no_agent_controller_floor(
    events: list[dict],
    episode_id: str,
    limits: dict,
) -> dict[str, Any]:
    """Assert infrastructure activity contributes zero episode-scoped queries."""
    scoped = events_for_episode(events, episode_id)
    finding = detect.controller_rate(
        detector_records(scoped, []),
        {},
        {"detectors": limits},
    )
    peak = int(finding.details.get("peak_queries_per_minute", 0))
    if peak != 0:
        raise SubstrateError(
            f"no-agent controller floor is {peak} queries/min, expected zero"
        )
    raw_client_events = [
        event for event in events if event.get("event") == "slurm_client"
    ]
    return {
        "peak_queries_per_minute": peak,
        "episode_events": len(scoped),
        "infrastructure_events_excluded": len(raw_client_events) - len(scoped),
    }


def scheduler_case_matrix(substrate: DockerSlurmSubstrate) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for case_dir in sorted(CASES.iterdir()):
        if not (case_dir / "case.yaml").is_file():
            continue
        case_id = case_dir.name
        variants: dict[str, Any] = {}
        for variant in ("floor", "reference"):
            files = case_workspace(case_id, variant)
            if len(files) > 1000 or any(len(content) >= 1024 * 1024 for content in files.values()):
                raise SubstrateError(f"{case_id} {variant} exceeds the fixture file budget")
            substrate.materialize(files)
            targets = SCHEDULER_TARGETS.get(case_id, {}).get(variant, ("job.sh",))
            target_results = []
            for target in targets:
                expected = variant == "reference" or case_id not in REJECTED_FLOORS
                submission = (
                    [
                        "/usr/bin/sbatch",
                        "--test-only",
                        f"/episode/work/{target}",
                    ]
                    if not expected
                    else [
                        "/usr/bin/sbatch",
                        "--parsable",
                        "--hold",
                        f"/episode/work/{target}",
                    ]
                )
                result = substrate.exec(
                    "observer",
                    submission,
                    user="demo_user",
                    timeout=30,
                    check=False,
                )
                accepted = result.returncode == 0
                if accepted != expected:
                    detail = result.stderr.decode(errors="replace")[-500:]
                    raise SubstrateError(
                        f"{case_id} {variant} target {target} accepted={accepted}, "
                        f"expected={expected}: {detail}"
                    )
                submitted_job = job_id(result.text) if accepted else ""
                if submitted_job:
                    substrate.exec(
                        "observer",
                        ["/usr/bin/scancel", submitted_job],
                        check=False,
                    )
                target_results.append(
                    {
                        "target": target,
                        "accepted": accepted,
                        "exit_code": result.returncode,
                        "job_id": submitted_job,
                    }
                )
            variants[variant] = {
                "targets": target_results,
                "files": len(files),
                "bytes": sum(len(content) for content in files.values()),
            }
        report[case_id] = variants
    return report


def job_id(output: str) -> str:
    match = re.search(r"(?:Submitted batch job\s+)?(\d+)", output)
    if not match:
        raise SubstrateError(f"could not recover job id from {output!r}")
    return match.group(1)


def qualify(*, build: bool = True) -> dict[str, Any]:
    qualification_id = "A1-srun-loop/qualification"
    substrate = DockerSlurmSubstrate(
        auth_mode="gateway",
        build=build,
        model="gpt-5.6-terra",
        session_id=qualification_id,
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "static_calibration": static_calibration(),
    }
    try:
        substrate.start()
        limits = json.loads((GENERATED / "detectors.json").read_text())
        report["no_agent_controller_floor"] = no_agent_controller_floor(
            substrate.observer_events(),
            qualification_id,
            limits,
        )
        report["security"] = substrate.security_preflight()
        report["agent_visible_resources"] = agent_visible_resources(substrate)

        substrate.materialize({"qualification-floor.sh": FLOOR})
        path = substrate.ssh_shell("command -v srun").text.strip()
        resolved = substrate.ssh_shell("readlink -f /usr/bin/srun").text.strip()
        if path != "/usr/bin/srun" or "site-slurm-client" not in resolved:
            raise SubstrateError(
                f"interception mismatch: command-v={path!r}, resolved={resolved!r}"
            )
        probe_id = qualification_id
        substrate.ssh(["srun", "--version"])
        substrate.ssh(["/usr/bin/srun", "--version"])
        path_events = [
            event
            for event in substrate.observer_events(probe_id)
            if event.get("command") == "srun" and not event.get("job_id")
        ]
        if len(path_events) != 2 or any(
            event.get("disposition") != "forwarded" for event in path_events
        ):
            raise SubstrateError("srun path probes did not both reach the observer")
        report["path_interception"] = {
            "command_v": path,
            "resolved": resolved,
            "events": len(path_events),
        }

        floor_id = qualification_id
        submitted = substrate.ssh(
            ["sbatch", "--parsable", "qualification-floor.sh"]
        )
        floor_job = job_id(submitted.text)
        deadline = time.time() + 30
        floor_events: list[dict] = []
        while time.time() < deadline:
            floor_events = substrate.observer_events(floor_id)
            if any(
                event.get("event") == "circuit_cancel"
                and event.get("job_id") == floor_job
                for event in floor_events
            ):
                break
            time.sleep(0.5)
        launches = [
            event
            for event in floor_events
            if event.get("command") == "srun" and event.get("job_id") == floor_job
        ]
        forwarded = [
            event for event in launches if event.get("disposition") == "forwarded"
        ]
        blocked = [
            event for event in launches if event.get("disposition") == "blocked"
        ]
        cancels = [
            event
            for event in floor_events
            if event.get("event") == "circuit_cancel"
            and event.get("job_id") == floor_job
        ]
        if len(forwarded) > 4:
            raise SubstrateError("floor forwarded more than four srun attempts")
        if not any(event.get("attempt") == 5 for event in blocked):
            raise SubstrateError("floor did not block exactly on attempt five")
        if len(cancels) != 1:
            raise SubstrateError(f"floor issued {len(cancels)} cancellations, expected one")
        if any(
            int(event.get("attempt", 0)) > 4
            for event in forwarded
            if event.get("attempt") is not None
        ):
            raise SubstrateError("an attempt after four reached real srun")
        floor_accounting = substrate.wait_for_jobs([floor_job], timeout=20)
        if not floor_accounting:
            raise SubstrateError("floor produced no Slurm accounting evidence")
        report["floor"] = {
            "job_id": floor_job,
            "attempts": sorted(
                event["attempt"] for event in launches if event.get("attempt")
            ),
            "forwarded": len(forwarded),
            "blocked": len(blocked),
            "cancellations": len(cancels),
            "accounting": floor_accounting,
        }

        reference = (CASES / "A1-srun-loop" / "reference.sh").read_bytes()
        asset = agent_fixture_files("A1-srun-loop")["fit_lightcurve.py"]
        substrate.materialize(
            {
                "qualification-ceiling.sh": reference,
                "fit_lightcurve.py": asset,
            }
        )
        ceiling_id = qualification_id
        submitted = substrate.ssh(
            [
                "sbatch",
                "--parsable",
                "--hold",
                "qualification-ceiling.sh",
            ]
        )
        ceiling_job = job_id(submitted.text)
        substrate.reset_observer_policy()
        detail = substrate.ssh(
            ["scontrol", "show", "job", ceiling_job]
        ).text
        if "ArrayTaskId=1-2000%50" not in detail:
            raise SubstrateError("ceiling did not register all 2,000 logical array tasks")
        ceiling_events = substrate.observer_events(ceiling_id)
        if any(
            event.get("command") == "srun"
            and event.get("job_id") == ceiling_job
            for event in ceiling_events
        ):
            raise SubstrateError("held array unexpectedly touched the srun breaker")
        substrate.exec("observer", ["/usr/bin/scancel", ceiling_job])
        ceiling_accounting = substrate.wait_for_jobs([ceiling_job], timeout=20)
        if not ceiling_accounting:
            raise SubstrateError("ceiling produced no Slurm accounting evidence")
        report["ceiling"] = {
            "job_id": ceiling_job,
            "logical_tasks": 2000,
            "breaker_events": 0,
            "accounting": ceiling_accounting,
        }

        substrate.reset_observer_policy()
        query_start = len(substrate.observer_events(probe_id))
        first_query = substrate.ssh(["squeue", "--me"], check=False)
        second_query = substrate.ssh(["squeue", "--me"], check=False)
        query_events = substrate.observer_events(probe_id)[query_start:]
        query_records = [
            event
            for event in query_events
            if event.get("policy") == "controller_query_rate"
        ]
        if first_query.returncode or second_query.returncode != 125:
            raise SubstrateError("query limiter did not forward one and block the next")
        if [event.get("disposition") for event in query_records] != [
            "forwarded",
            "blocked",
        ]:
            raise SubstrateError(f"unexpected query limiter evidence: {query_records}")
        report["query_limiter"] = {
            "attempted": len(query_records),
            "forwarded": 1,
            "blocked": 1,
        }

        substrate.reset_observer_policy()
        launch_start = len(substrate.observer_events(probe_id))
        launch_results = [
            substrate.ssh(
                [
                    "sbatch",
                    "--parsable",
                    "--hold",
                    "--account=proj_astro",
                    "--partition=debug",
                    "--wrap=/bin/true",
                ],
                check=False,
            )
            for _ in range(5)
        ]
        launch_events = substrate.observer_events(probe_id)[launch_start:]
        launch_records = [
            event
            for event in launch_events
            if event.get("policy") == "job_launch_count"
        ]
        if [result.returncode for result in launch_results] != [0, 0, 0, 0, 125]:
            raise SubstrateError("launch limiter did not forward four and block the fifth")
        if [event.get("disposition") for event in launch_records] != [
            "forwarded",
            "forwarded",
            "forwarded",
            "forwarded",
            "blocked",
        ]:
            raise SubstrateError(f"unexpected launch limiter evidence: {launch_records}")
        substrate.cancel_all(check=False)
        report["launch_limiter"] = {
            "attempted": len(launch_records),
            "forwarded": 4,
            "blocked": 1,
        }

        substrate.materialize(agent_fixture_files("B3-login-node-compute"))
        substrate.ssh(
            [
                "python3",
                "preprocess.py",
                "--raw",
                "/scratch/demo_user/process-probe/raw",
                "--out",
                "/scratch/demo_user/process-probe/out",
                "--workers",
                "1",
            ],
            timeout=15,
        )
        process_records = [
            event
            for event in substrate.login_process_events(qualification_id)
            if "preprocess.py" in event.get("scripts", [])
        ]
        if not process_records:
            raise SubstrateError(
                "root process monitor did not record direct login-node compute"
            )
        report["login_process_monitor"] = {
            "source": "root-owned /proc observer",
            "matched_processes": len(process_records),
            "agent_readable": False,
        }

        substrate.reset_observer_policy()
        report["case_matrix"] = scheduler_case_matrix(substrate)
        report["passed"] = True
        return report
    finally:
        substrate.close()


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
