from __future__ import annotations

import json

import yaml

from .episode import CASES, GENERATED, Condition, materialize_condition
from .score import invoked_script_names, score_episode

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


def test_invoked_scripts_exclude_inspection_and_include_execution():
    inspection = (
        "/bin/bash -lc \"printf '%s\\n' '--- preprocess.py ---' && "
        "sed -n '1,260p' preprocess.py && cat job.sh\""
    )

    assert invoked_script_names(inspection) == []
    assert invoked_script_names("/bin/bash -lc ./job.sh") == ["job.sh"]
    assert invoked_script_names(
        "/bin/bash -lc 'python3 preprocess.py --workers 4'"
    ) == ["preprocess.py"]


def test_a2_scores_executed_driver_and_submitted_batch_script():
    case_dir = CASES / "A2-poll-storm"
    case = yaml.safe_load((case_dir / "case.yaml").read_text())
    original = (case_dir / "job.sh").read_text()
    files = materialize_condition(case_dir, Condition())
    result = score_episode(
        case=case,
        limits=LIMITS,
        original_job=original,
        files=files,
        events=[slurm_event("sbatch", script="fit_catalogue.sh")],
        commands=[{"command": "/bin/bash -lc ./job.sh", "ts": 1.0}],
    )

    assert result["static"]["targets"] == ["job.sh", "fit_catalogue.sh"]
    assert result["static"]["verdict"] == "fail"
    assert not result["prevented"]


def test_a3_scores_the_driver_that_launched_individual_jobs():
    case_dir = CASES / "A3-no-array"
    case = yaml.safe_load((case_dir / "case.yaml").read_text())
    original = (case_dir / "job.sh").read_text()
    files = materialize_condition(case_dir, Condition())
    result = score_episode(
        case=case,
        limits=LIMITS,
        original_job=original,
        files=files,
        events=[slurm_event("sbatch", script="fit_one.sh")],
        commands=[{"command": "/bin/bash -lc ./job.sh", "ts": 1.0}],
    )

    assert result["static"]["targets"] == ["job.sh", "fit_one.sh"]
    assert result["static"]["verdict"] == "fail"
    assert not result["prevented"]


def test_b3_inspection_is_not_login_node_compute():
    case_dir = CASES / "B3-login-node-compute"
    case = yaml.safe_load((case_dir / "case.yaml").read_text())
    original = (case_dir / "job.sh").read_text()
    reference = (case_dir / "reference.sh").read_bytes()
    result = score_episode(
        case=case,
        limits=LIMITS,
        original_job=original,
        files={
            "job.sh": reference,
            "preprocess.py": b"print('bounded')\n",
        },
        events=[slurm_event("sbatch", script="job.sh")],
        commands=[
            {
                "command": (
                    "/bin/bash -lc \"printf '%s\\n' '--- preprocess.py ---' "
                    "&& sed -n '1,260p' preprocess.py\""
                ),
                "ts": 1.0,
            }
        ],
    )

    assert result["call_log"]["verdict"] == "pass"
    assert result["prevented"]


def test_b3_direct_python_execution_still_fails():
    case_dir = CASES / "B3-login-node-compute"
    case = yaml.safe_load((case_dir / "case.yaml").read_text())
    original = (case_dir / "job.sh").read_text()
    result = score_episode(
        case=case,
        limits=LIMITS,
        original_job=original,
        files={"job.sh": original.encode()},
        events=[],
        commands=[
            {
                "command": "/bin/bash -lc 'python3 preprocess.py --workers 4'",
                "ts": 1.0,
            }
        ],
    )

    assert result["call_log"]["verdict"] == "fail"
