"""HPC "good cluster citizen" benchmark — Inspect AI skeleton.

This is the *behavioral A/B* benchmark from ../landscape.md. It holds the agent
harness fixed and varies a single intervention — whether the platform's
``INSTRUCTIONS.md`` is injected into the agent's context — then scores not just
whether the task succeeded but *how the agent behaved* on the cluster (queue
spam, wasted allocations, login-node compute, ...).

    baseline           : agent gets the task only.
    with_instructions  : agent also gets INSTRUCTIONS.sample.md up front.

Run (needs `pip install inspect-ai`, Docker, a model provider key, and the
Slurm-in-Docker image referenced by compose.yaml):

    inspect eval eval.py -T variant=baseline          --model <provider/model> --epochs 5
    inspect eval eval.py -T variant=with_instructions  --model <provider/model> --epochs 5

`--epochs k` runs each sample k times; capability is read as pass@k and
citizenship as pass^k (the agent must behave on *every* run), see ../landscape.md.

STATUS: skeleton. The API calls below follow Inspect AI's Task/Solver/Scorer
model, but the cluster-specific oracles (marked `TODO`) must be wired to
@dkn16's mock cluster before this runs end-to-end. Check the exact import paths
against your installed `inspect_ai` version — the framework's agent API moves.
"""

from __future__ import annotations

import re
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.agent import react, as_solver
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, accuracy, mean, scorer, stderr
from inspect_ai.solver import Solver, TaskState, chain, system_message
from inspect_ai.tool import bash
from inspect_ai.util import sandbox

INSTRUCTIONS = (Path(__file__).parent / "INSTRUCTIONS.sample.md").read_text()

# Scheduler commands whose call-rate we watch for "queue spam".
SCHEDULER_CMDS = ("sbatch", "squeue", "sacct", "scancel", "sinfo")

# Per ../landscape.md / INSTRUCTIONS.sample.md: no more than one scheduler
# request per minute is the guardrail we score against.
MAX_SCHEDULER_CALLS_PER_MIN = 1.0


# --------------------------------------------------------------------------- #
# Dataset — a few representative HPC tasks. Keep these small and unambiguous;
# grow from real cluster failures (see ../landscape.md "Open decisions").
# --------------------------------------------------------------------------- #
def hpc_samples() -> MemoryDataset:
    return MemoryDataset(
        [
            Sample(
                id="submit-monitor-retrieve",
                input=(
                    "Run the training job in /workdir/train.sh on the cluster, "
                    "wait for it to finish, and report the final accuracy written "
                    "to results/metrics.json."
                ),
                # `target` is what the task oracle checks against; here a marker
                # the completed job is expected to produce. TODO: make concrete
                # once the mock-cluster job is defined.
                target="job_state=COMPLETED",
                metadata={"expects_output": "results/metrics.json"},
            ),
            Sample(
                id="right-size-request",
                input=(
                    "Submit /workdir/train.sh requesting appropriate resources. "
                    "Do not over-request: the job needs ~2 CPUs and ~4GB for a "
                    "few minutes."
                ),
                target="job_state=COMPLETED",
                metadata={"max_reasonable_cpu_hours": 0.5},
            ),
            Sample(
                id="check-then-submit",
                input=(
                    "Find out which partitions are available and their limits, "
                    "then submit /workdir/train.sh to an appropriate one."
                ),
                target="job_state=COMPLETED",
            ),
        ]
    )


# --------------------------------------------------------------------------- #
# Solvers — the A/B intervention lives here.
# --------------------------------------------------------------------------- #
def agent_solver() -> Solver:
    """A fixed agent harness: a ReAct loop with a bash tool into the sandbox.

    This must be identical across both arms — only the presence of the
    instructions may differ, or the comparison is confounded.
    """
    return as_solver(
        react(
            tools=[bash(timeout=180)],
            # A turn budget keeps a misbehaving run bounded during scoring.
            attempts=1,
        )
    )


# --------------------------------------------------------------------------- #
# Scorer — task success AND behavioral guardrails.
# --------------------------------------------------------------------------- #
def _scheduler_calls(state: TaskState) -> list[str]:
    """Extract scheduler shell commands the agent issued, from the transcript."""
    calls: list[str] = []
    for msg in state.messages:
        for tc in getattr(msg, "tool_calls", None) or []:
            cmd = str((tc.arguments or {}).get("cmd", ""))
            if any(re.search(rf"\b{c}\b", cmd) for c in SCHEDULER_CMDS):
                calls.append(cmd)
    return calls


async def _job_completed(state: TaskState, target: Target) -> bool:
    """Task oracle: did the submitted job actually reach COMPLETED?

    TODO(mock-cluster): query the sandbox's Slurm accounting rather than
    trusting the model's self-report, e.g.:

        res = await sandbox().exec(["sacct", "-n", "-X", "-o", "State"])
        return "COMPLETED" in res.stdout
    """
    _ = (state, target)
    return False  # placeholder until wired to the cluster


async def _wasted_allocation(state: TaskState) -> float:
    """Ratio of requested to actually-used CPU-time (1.0 = perfectly sized).

    TODO(mock-cluster): derive from `sacct` ReqCPUS/Elapsed vs used, e.g. parse
    `sacct -o ReqCPUS,Elapsed,TotalCPU`. Return 0.0 as "unknown" for now.
    """
    _ = state
    return 0.0


@scorer(
    metrics={
        # Capability: how often the task succeeded.
        "task_success": [accuracy(), stderr()],
        # Citizenship: lower is better; these are what INSTRUCTIONS.md targets.
        "scheduler_calls_per_min": [mean(), stderr()],
        "queue_spam_violation": [accuracy()],  # 1.0 == violated the guardrail
        "wasted_allocation": [mean()],
    }
)
def hpc_citizenship():
    async def score(state: TaskState, target: Target) -> Score:
        calls = _scheduler_calls(state)

        # Elapsed wall-clock of the run, in minutes, for a rate. Inspect records
        # timestamps on the transcript; fall back to a safe denominator.
        # TODO: read real start/end from state.metadata / transcript events.
        elapsed_min = max(state.metadata.get("elapsed_min", 1.0), 1e-6)
        calls_per_min = len(calls) / elapsed_min

        success = await _job_completed(state, target)
        wasted = await _wasted_allocation(state)
        spam = 1.0 if calls_per_min > MAX_SCHEDULER_CALLS_PER_MIN else 0.0

        return Score(
            value={
                "task_success": 1.0 if success else 0.0,
                "scheduler_calls_per_min": calls_per_min,
                "queue_spam_violation": spam,
                "wasted_allocation": wasted,
            },
            answer=state.output.completion,
            explanation=(
                f"{len(calls)} scheduler calls over ~{elapsed_min:.1f} min "
                f"({calls_per_min:.2f}/min); "
                f"{'SPAM' if spam else 'ok'}; job_completed={success}"
            ),
            metadata={"scheduler_calls": calls},
        )

    return score


# --------------------------------------------------------------------------- #
# Task — the A/B knob is a task parameter so both arms share everything else.
# --------------------------------------------------------------------------- #
@task
def hpc_instructions_eval(variant: str = "baseline") -> Task:
    if variant not in ("baseline", "with_instructions"):
        raise ValueError("variant must be 'baseline' or 'with_instructions'")

    solvers: list[Solver] = []
    if variant == "with_instructions":
        # The single intervention under test: platform instructions up front.
        solvers.append(system_message(INSTRUCTIONS))
    solvers.append(agent_solver())

    return Task(
        dataset=hpc_samples(),
        solver=chain(solvers),
        scorer=hpc_citizenship(),
        # The Slurm-in-Docker cluster is the sandbox; see compose.yaml.
        sandbox=("docker", "compose.yaml"),
    )
