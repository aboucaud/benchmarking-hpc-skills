from __future__ import annotations

import json

import yaml

from .episode import CASES, GENERATED
from .score import score_episode

CASE_DIR = CASES / "A1-srun-loop"
CASE = yaml.safe_load((CASE_DIR / "case.yaml").read_text())
LIMITS = json.loads((GENERATED / "detectors.json").read_text())
ORIGINAL = (CASE_DIR / "job.sh").read_text()
REFERENCE = (CASE_DIR / "reference.sh").read_text()


def slurm_event(
    command: str,
    *,
    attempt: int | None = None,
    disposition: str = "forwarded",
    outcome: str = "accepted",
    job_id: str = "",
    script: str = "",
) -> dict:
    return {
        "event": "slurm_client",
        "source": "observer",
        "command": command,
        "attempt": attempt,
        "disposition": disposition,
        "outcome": outcome,
        "job_id": job_id,
        "script": script,
        "ts": float(attempt or 1),
        "iso": "2026-01-01T00:00:00Z",
        "exit": 0 if disposition == "forwarded" else 125,
    }


def test_floor_is_contained_but_not_scored_as_prevented():
    events = [
        slurm_event("sbatch", script="job.sh"),
        *[
            slurm_event("srun", attempt=attempt, job_id="20")
            for attempt in range(1, 5)
        ],
        slurm_event(
            "srun",
            attempt=5,
            disposition="blocked",
            outcome="blocked",
            job_id="20",
        ),
        {
            "event": "circuit_cancel",
            "source": "observer",
            "command": "scancel",
            "job_id": "20",
            "disposition": "observer_cancel",
        },
    ]
    result = score_episode(
        case=CASE,
        limits=LIMITS,
        original_job=ORIGINAL,
        files={"job.sh": ORIGINAL.encode()},
        events=events,
        commands=[],
    )

    assert result["static"]["verdict"] == "fail"
    assert result["call_log"]["verdict"] == "fail"
    assert result["runtime"]["verdict"] == "pass"
    assert result["runtime"]["circuit_breaker"]["jobs"]["20"]["forwarded"] == 4
    assert not result["prevented"]


def test_reference_ceiling_preserves_2000_tasks_and_passes():
    events = [slurm_event("sbatch", script="job.sh")]
    result = score_episode(
        case=CASE,
        limits=LIMITS,
        original_job=ORIGINAL,
        files={"job.sh": REFERENCE.encode()},
        events=events,
        commands=[],
    )

    assert result["static"]["verdict"] == "pass"
    assert result["call_log"]["verdict"] == "pass"
    assert result["runtime"]["verdict"] == "pass"
    assert result["logical_tasks"] == 2000
    assert result["regressions"] == []
    assert result["workload_submitted"]
    assert result["prevented"]


def test_shrinking_the_workload_is_a_regression():
    shrunken = REFERENCE.replace("1-2000%50", "1-100%50")
    result = score_episode(
        case=CASE,
        limits=LIMITS,
        original_job=ORIGINAL,
        files={"job.sh": shrunken.encode()},
        events=[slurm_event("sbatch", script="job.sh")],
        commands=[],
    )

    assert result["logical_tasks"] == 100
    assert result["regressions"][0]["id"] == "workload-shrunk"
    assert not result["prevented"]
