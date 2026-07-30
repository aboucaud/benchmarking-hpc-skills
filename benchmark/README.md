# HPC benchmark skills

Benchmarking workstream: measuring whether a standardized `INSTRUCTIONS.md` + consuming
skills actually improve an agent's efficiency and behavior on an HPC platform.

- [`center.yaml`](center.yaml) — the single source of truth. `render.py` generates the
  document the agent reads, the limits the detectors score against, and the config the
  mock cluster enforces, so none of them can drift apart.
- [`cases/`](cases/) — nine misuse cases, one injected defect each.
- [`harness/`](../src/hpcbench/harness/) — episode orchestration, L1 detectors, L2/L3 judge, reporting.
- [`stubs/`](../src/hpcbench/stubs/) — the echo-stub Slurm substrate episodes run on.
- [`landscape.md`](landscape.md) — survey of existing agent/skill benchmarking methods
  and frameworks, what they require, and a recommended approach for this project.

Two pre-MVP skeletons — `inspect/` (an Inspect AI A/B) and `prompt-format/` (an
EngiAI-style completion benchmark, [arXiv:2605.19743](https://arxiv.org/abs/2605.19743)) —
were removed once the harness landed equivalents. They are recoverable from git history;
`landscape.md` still records what they were for.

## Setup

This directory is a [uv](https://docs.astral.sh/uv/) project (`pyproject.toml`); all
examples run through uv, never a global `pip`. From `benchmark/`:

```bash
uv sync          # create .venv and install dependencies (inspect-ai, pyyaml)
uv run <cmd>     # run anything inside the environment
```

See each subdirectory's README for the specific commands.
