# HPC benchmark skills

Benchmarking workstream: measuring whether a standardized `INSTRUCTIONS.md` + consuming
skills actually improve an agent's efficiency and behavior on an HPC platform.

- [`landscape.md`](landscape.md) — survey of existing agent/skill benchmarking methods
  and frameworks, what they require, and a recommended approach for this project.
- [`inspect/`](inspect/) — behavioral A/B benchmark (Inspect AI): fix the prompt, flip
  whether `INSTRUCTIONS.md` is present, score good-citizen behavior on the cluster.
- [`prompt-format/`](prompt-format/) — EngiAI-style benchmark
  ([arXiv:2605.19743](https://arxiv.org/abs/2605.19743)): fix the instructions, flip the
  prompt format (explicit vs natural), score end-to-end task completion.

The two are designed to combine into a 2×2 (prompt format × instructions on/off); see
`landscape.md`.

## Setup

This directory is a [uv](https://docs.astral.sh/uv/) project (`pyproject.toml`); all
examples run through uv, never a global `pip`. From `benchmark/`:

```bash
uv sync          # create .venv and install dependencies (inspect-ai, pyyaml)
uv run <cmd>     # run anything inside the environment
```

See each subdirectory's README for the specific commands.
