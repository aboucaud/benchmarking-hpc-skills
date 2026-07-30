"""Completion oracle for the prompt-format benchmark.

EngiAI (arXiv:2605.19743) scores the HPC task by whether the agent completed the
end-to-end workflow: (1) generate a correct SLURM script, (2) submit it, (3)
monitor to completion, (4) evaluate the trained model. We keep that four-step
structure and return a per-step completion vector plus a final metric check, so
the benchmark can report *where* natural-language prompts break down (EngiAI
found later steps degrade most), not just a single pass/fail.

This is format-agnostic on purpose: the same oracle scores both the explicit and
natural arms, so any difference is attributable to prompt phrasing, not scoring.

STATUS: skeleton. The step checks are stubbed with `TODO`s where they must read
real state from @dkn16's mock cluster (submitted job ids, `sacct` state, the
metrics file). `evaluate_metric` already works against train_stub.py's output.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class StepResult:
    script_generated: bool  # step 1: correct SLURM script with the right params
    submitted: bool         # step 2: sbatch accepted it, job id captured
    completed: bool         # step 3: job reached COMPLETED
    metric_ok: bool         # step 4: metric file present and above threshold

    @property
    def steps_completed(self) -> int:
        return sum([self.script_generated, self.submitted, self.completed, self.metric_ok])

    @property
    def passed(self) -> bool:
        """Full task success == all four steps."""
        return self.steps_completed == 4


def check_script(script_path: Path, *, algorithm: str, problem: str,
                 epochs: int, seed: int) -> bool:
    """Step 1: did the agent write a SLURM script invoking training correctly?"""
    if not script_path.exists():
        return False
    text = script_path.read_text()
    required = [
        "#SBATCH",                      # it is actually a batch script
        f"--algorithm {algorithm}",
        f"--problem {problem}",
        f"--epochs {epochs}",
        f"--seed {seed}",
    ]
    return all(tok in text for tok in required)


def check_submitted(job_id: str | None) -> bool:
    """Step 2: a job id was returned by the scheduler.

    TODO(mock-cluster): the runner should capture sbatch's stdout job id and
    pass it here; optionally confirm it appears in `sacct`.
    """
    return bool(job_id)


def check_completed(job_id: str | None) -> bool:
    """Step 3: the job reached COMPLETED.

    TODO(mock-cluster):
        res = subprocess.run(["sacct", "-nX", "-j", job_id, "-o", "State"], ...)
        return "COMPLETED" in res.stdout
    """
    _ = job_id
    return False  # placeholder until wired to the cluster


def evaluate_metric(metrics_path: Path, *, threshold: float = 0.0) -> bool:
    """Step 4: the training produced a metric at/above threshold.

    Works today against train_stub.py's metrics.json (`score` field).
    """
    if not metrics_path.exists():
        return False
    try:
        data = json.loads(metrics_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    return float(data.get("score", float("-inf"))) >= threshold


def score_run(*, workdir: Path, algorithm: str, problem: str, epochs: int,
              seed: int, job_id: str | None, threshold: float = 0.0) -> StepResult:
    """Assemble the four-step result for one agent run."""
    script = next(workdir.glob("*.slurm"), None)
    return StepResult(
        script_generated=(
            check_script(script, algorithm=algorithm, problem=problem,
                         epochs=epochs, seed=seed)
            if script else False
        ),
        submitted=check_submitted(job_id),
        completed=check_completed(job_id),
        metric_ok=evaluate_metric(workdir / "results" / "metrics.json",
                                  threshold=threshold),
    )


if __name__ == "__main__":
    # Tiny self-check against a freshly-run train_stub.py, no cluster needed.
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", type=Path, default=Path("."))
    ap.add_argument("--algorithm", default="adam")
    ap.add_argument("--problem", default="beam")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--job-id", default=None)
    args = ap.parse_args()

    result = score_run(
        workdir=args.workdir, algorithm=args.algorithm, problem=args.problem,
        epochs=args.epochs, seed=args.seed, job_id=args.job_id,
    )
    print(json.dumps(asdict(result) | {
        "steps_completed": result.steps_completed, "passed": result.passed,
    }, indent=2))
