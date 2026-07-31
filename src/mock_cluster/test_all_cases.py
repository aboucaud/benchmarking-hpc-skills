from __future__ import annotations

import json

import yaml

from .episode import CASES, GENERATED
from .score import score_episode

LIMITS = json.loads((GENERATED / "detectors.json").read_text())


def accepted_submission(script: str = "job.sh") -> dict:
    return {
        "event": "slurm_client",
        "source": "observer",
        "command": "sbatch",
        "attempt": 1,
        "policy": "job_launch_count",
        "disposition": "forwarded",
        "outcome": "accepted",
        "script": script,
        "ts": 1.0,
        "iso": "2026-01-01T00:00:00Z",
        "exit": 0,
    }


def test_every_case_floor_fails_and_reference_passes_l1():
    for case_dir in sorted(CASES.iterdir()):
        if not (case_dir / "case.yaml").is_file():
            continue
        case = yaml.safe_load((case_dir / "case.yaml").read_text())
        original = (case_dir / "job.sh").read_text()
        reference = (case_dir / "reference.sh").read_text()

        floor = score_episode(
            case=case,
            limits=LIMITS,
            original_job=original,
            files={"job.sh": original.encode()},
            events=[accepted_submission()],
            commands=[],
        )
        ceiling = score_episode(
            case=case,
            limits=LIMITS,
            original_job=original,
            files={"job.sh": reference.encode()},
            events=[accepted_submission()],
            commands=[],
        )

        assert floor["static"]["verdict"] == "fail", case_dir.name
        assert not floor["prevented"], case_dir.name
        assert ceiling["static"]["verdict"] == "pass", case_dir.name
        assert ceiling["runtime"]["verdict"] == "pass", case_dir.name
        assert ceiling["prevented"], case_dir.name


def test_root_process_evidence_corroborates_login_node_compute():
    case_dir = CASES / "B3-login-node-compute"
    case = yaml.safe_load((case_dir / "case.yaml").read_text())
    original = (case_dir / "job.sh").read_text()
    result = score_episode(
        case=case,
        limits=LIMITS,
        original_job=original,
        files={"job.sh": original.encode()},
        events=[],
        commands=[],
        processes=[
            {
                "event": "process_start",
                "source": "login_process",
                "command": "python3 preprocess.py",
                "ts": 1.0,
            }
        ],
    )

    assert result["call_log"]["verdict"] == "fail"
    finding = result["call_log"]["findings"][0]
    assert finding["detector"] == "login_node_compute"
    assert "preprocess.py" in finding["evidence"]
