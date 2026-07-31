"""No-model Docker qualification for interception and circuit safety."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .episode import CASES
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


def agent_visible_resources(substrate: DockerSlurmSubstrate) -> dict[str, dict[str, Any]]:
    result = substrate.ssh(
        ["sinfo", "--noheader", "--Node", "--format=%N|%c|%m|%G"]
    )
    resources: dict[str, dict[str, Any]] = {}
    for line in result.text.splitlines():
        fields = line.strip().split("|", 3)
        if len(fields) != 4:
            continue
        name, cpus, memory, gres = fields
        resources[name] = {
            "cpus": int(cpus),
            "memory_mb": int(memory),
            "gres": gres,
        }

    expected = {
        "c1": {"cpus": 128, "memory_mb": 256000},
        "c2": {"cpus": 128, "memory_mb": 256000},
        "c3": {"cpus": 64, "memory_mb": 512000},
    }
    for name, values in expected.items():
        observed = resources.get(name)
        if observed is None:
            raise SubstrateError(f"agent-visible node is missing: {name}")
        if any(observed[key] != value for key, value in values.items()):
            raise SubstrateError(
                f"agent-visible resources for {name} are {observed}, expected {values}"
            )
    if "gpu:4" not in resources["c3"]["gres"]:
        raise SubstrateError(
            f"agent-visible c3 GRES is {resources['c3']['gres']!r}, expected gpu:4"
        )
    return resources


def job_id(output: str) -> str:
    match = re.search(r"(?:Submitted batch job\s+)?(\d+)", output)
    if not match:
        raise SubstrateError(f"could not recover job id from {output!r}")
    return match.group(1)


def qualify(*, build: bool = True) -> dict[str, Any]:
    substrate = DockerSlurmSubstrate(
        auth_mode="gateway",
        build=build,
        model="gpt-5.6-terra",
        session_id="qualification",
    )
    report: dict[str, Any] = {"schema_version": 1}
    try:
        substrate.start()
        report["security"] = substrate.security_preflight()
        report["agent_visible_resources"] = agent_visible_resources(substrate)

        substrate.materialize({"qualification-floor.sh": FLOOR})
        path = substrate.ssh_shell("command -v srun").text.strip()
        resolved = substrate.ssh_shell("readlink -f /usr/bin/srun").text.strip()
        if path != "/usr/bin/srun" or "site-slurm-client" not in resolved:
            raise SubstrateError(
                f"interception mismatch: command-v={path!r}, resolved={resolved!r}"
            )
        probe_id = "qualification"
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

        floor_id = "qualification"
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
        asset = (
            CASES / "A1-srun-loop" / "assets" / "fit_lightcurve.py"
        ).read_bytes()
        substrate.materialize(
            {
                "qualification-ceiling.sh": reference,
                "fit_lightcurve.py": asset,
            }
        )
        ceiling_id = "qualification"
        submitted = substrate.ssh(
            [
                "sbatch",
                "--parsable",
                "--hold",
                "qualification-ceiling.sh",
            ]
        )
        ceiling_job = job_id(submitted.text)
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
        report["passed"] = True
        return report
    finally:
        substrate.close()


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
