#!/usr/bin/env python3
"""Stand-in "training" job for the prompt-format benchmark.

EngiAI (arXiv:2605.19743) trains real EngiOpt models; we don't have that
codebase, so this is a tiny deterministic stand-in that behaves like a training
job from the agent's point of view: it takes an algorithm/problem/epochs/seed,
runs a short loop, and writes a metrics JSON the scorer can check. Pure stdlib
so it runs on any node of the mock cluster without extra packages.

Swap this for the real training entry point when one is available; the benchmark
only cares that the agent produced a correct SLURM script, submitted it,
monitored it to completion, and that a metric file appeared.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

# Known stand-in workloads. Extend as needed; keep them cheap.
ALGORITHMS = ("sgd", "adam", "cmaes")
PROBLEMS = ("beam", "heat", "truss")


def train(algorithm: str, problem: str, epochs: int, seed: int) -> dict:
    rng = random.Random(f"{algorithm}/{problem}/{seed}")
    # A deterministic decaying "loss" curve; final objective depends on inputs
    # so a wrong algorithm/problem/seed yields a different, checkable result.
    base = 1.0 + rng.random()
    loss = base
    for epoch in range(epochs):
        loss = base * math.exp(-3.0 * (epoch + 1) / epochs) + rng.random() * 0.01
        time.sleep(0.0)  # placeholder for per-epoch work
    objective = round(loss, 6)
    return {
        "algorithm": algorithm,
        "problem": problem,
        "epochs": epochs,
        "seed": seed,
        "final_loss": objective,
        # EngiOpt-style headline metric stand-in (higher = better).
        "score": round(1.0 / (1.0 + objective), 6),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="stand-in training job")
    p.add_argument("--algorithm", required=True, choices=ALGORITHMS)
    p.add_argument("--problem", required=True, choices=PROBLEMS)
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--out", type=Path, default=Path("results/metrics.json"))
    args = p.parse_args()

    metrics = train(args.algorithm, args.problem, args.epochs, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metrics, indent=2))
    print(f"wrote {args.out}: {metrics}")


if __name__ == "__main__":
    main()
