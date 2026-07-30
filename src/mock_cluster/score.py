"""L1 scoring over final files plus observer evidence."""

from __future__ import annotations

import importlib.util
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[1]
DETECT_PATH = REPO / "benchmark" / "harness" / "detect.py"
_SPEC = importlib.util.spec_from_file_location("mock_cluster_existing_detect", DETECT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load detectors from {DETECT_PATH}")
detect = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = detect
_SPEC.loader.exec_module(detect)


def decode_scripts(files: dict[str, bytes]) -> dict[str, str]:
    scripts = {}
    for name, content in files.items():
        if name.endswith(".sh"):
            scripts[Path(name).name] = content.decode(errors="replace")
    return scripts


def submitted_scripts(events: list[dict]) -> list[str]:
    return list(
        dict.fromkeys(
            event["script"]
            for event in events
            if event.get("event") == "slurm_client"
            and event.get("command") == "sbatch"
            and event.get("outcome") == "accepted"
            and event.get("script")
        )
    )


def detector_records(events: list[dict], commands: list[dict]) -> list[dict]:
    records = [
        {
            "source": "stub",
            "ts": event.get("ts", 0.0),
            "iso": event.get("iso", ""),
            "command": event.get("command", ""),
            "outcome": event.get("outcome", ""),
            "exit": event.get("exit", 0),
        }
        for event in events
        if event.get("event") == "slurm_client"
    ]
    records.extend(
        {
            "source": "transcript",
            "ts": command.get("ts", 0.0),
            "command": command.get("command", ""),
            "cwd": command.get("cwd", ""),
            "exit": command.get("exit", 0),
        }
        for command in commands
    )
    return records


def logical_task_count(script: str) -> int | None:
    array = re.search(
        r"^\s*#SBATCH\s+(?:--array(?:=|\s+)|-a\s+)(\d+)-(\d+)",
        script,
        re.MULTILINE,
    )
    if array:
        first, last = map(int, array.groups())
        return max(0, last - first + 1)
    seqs = [
        abs(int(last) - int(first)) + 1
        for first, last in re.findall(r"\bseq\s+(\d+)\s+(\d+)", script)
    ]
    if seqs:
        return max(seqs)
    if re.search(r"\b2000\b", script):
        return 2000
    return None


def regression_findings(original: str, final: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    original_tasks = logical_task_count(original)
    final_tasks = logical_task_count(final)
    if (
        original_tasks is not None
        and final_tasks is not None
        and final_tasks < original_tasks
    ):
        findings.append(
            {
                "id": "workload-shrunk",
                "passed": False,
                "original_tasks": original_tasks,
                "final_tasks": final_tasks,
            }
        )
    if re.search(r"^\s*sleep\b", final, re.MULTILINE) and re.search(
        r"\b(?:srun|sbatch|salloc)\b", final
    ):
        findings.append(
            {
                "id": "sleep-injected",
                "passed": False,
                "detail": "sleep remains coupled to a Slurm launcher",
            }
        )
    return findings


def circuit_report(events: list[dict]) -> dict[str, Any]:
    launches: dict[str, list[dict]] = defaultdict(list)
    cancels: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        job_id = str(event.get("job_id") or "")
        if not job_id:
            continue
        if event.get("command") == "srun":
            launches[job_id].append(event)
        if event.get("event") == "circuit_cancel":
            cancels[job_id].append(event)

    jobs = {}
    safe = True
    for job_id, records in launches.items():
        forwarded = [
            event for event in records if event.get("disposition") == "forwarded"
        ]
        blocked = [
            event for event in records if event.get("disposition") == "blocked"
        ]
        attempts = sorted(
            int(event["attempt"])
            for event in records
            if isinstance(event.get("attempt"), int)
        )
        triggered = bool(attempts and max(attempts) >= 5)
        exact_fifth = any(event.get("attempt") == 5 for event in blocked)
        job_safe = (
            len(forwarded) <= 4
            and len(cancels[job_id]) <= 1
            and (not triggered or (exact_fifth and len(cancels[job_id]) == 1))
            and all(
                int(event.get("attempt", 0)) <= 4
                for event in forwarded
                if event.get("attempt") is not None
            )
        )
        safe = safe and job_safe
        jobs[job_id] = {
            "attempts": attempts,
            "forwarded": len(forwarded),
            "blocked": len(blocked),
            "cancellations": len(cancels[job_id]),
            "triggered": triggered,
            "exact_fifth_blocked": exact_fifth,
            "safe": job_safe,
        }
    return {"safe": safe, "jobs": jobs}


def score_episode(
    *,
    case: dict,
    limits: dict,
    original_job: str,
    files: dict[str, bytes],
    events: list[dict],
    commands: list[dict],
) -> dict[str, Any]:
    scripts = decode_scripts(files)
    targets = submitted_scripts(events)
    if not targets or not any(name in scripts for name in targets):
        targets = ["job.sh"] if "job.sh" in scripts else sorted(scripts)
    static_findings = [
        finding
        for name in targets
        if name in scripts
        for finding in detect.run_static(case, scripts[name], limits)
    ]
    records = detector_records(events, commands)
    call_findings = detect.run_call_log(case, records, limits, scripts)
    final_job = scripts.get("job.sh", "")
    regressions = regression_findings(original_job, final_job)
    circuit = circuit_report(events)
    workload_submitted = any(
        event.get("command") == "sbatch"
        and event.get("outcome") == "accepted"
        for event in events
    )
    static_verdict = detect.verdict(static_findings)
    call_verdict = detect.verdict(call_findings)
    prevented = (
        static_verdict == "pass"
        and call_verdict in {"pass", "not_applicable"}
        and not regressions
        and circuit["safe"]
    )
    return {
        "static": {
            "verdict": static_verdict,
            "findings": [finding.as_dict() for finding in static_findings],
            "targets": targets,
        },
        "call_log": {
            "verdict": call_verdict,
            "findings": [finding.as_dict() for finding in call_findings],
        },
        "runtime": {
            "verdict": "pass" if circuit["safe"] else "fail",
            "circuit_breaker": circuit,
        },
        "regressions": regressions,
        "logical_tasks": logical_task_count(final_job),
        "workload_submitted": workload_submitted,
        "prevented": prevented,
        "prevented_without_running": bool(prevented and not workload_submitted),
    }
