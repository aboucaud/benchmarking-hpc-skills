# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Docs, plus the workspace scaffolding described below. The harness itself is still being
built out, PR by PR, against the plan in
[issue #1](https://github.com/aboucaud/benchmarking-hpc-skills/issues/1). Update the
architecture notes in this file as each component lands, rather than after the fact.

## Commands

```bash
uv sync --extra dev       # install
uv run pytest             # tests
uv run ruff check .       # lint
uv run ruff format .      # format
```

CI runs lint, format-check and tests on every PR.

## Layout

| Path | Holds |
|---|---|
| `src/hpcbench/` | the harness package (see its docstring for the module map) |
| `benchmark/` | task definitions and center descriptors — data, not code |
| `skills/candidates/<tier>/` | skills **under test**, installed into episode sandboxes by the harness |
| `mock-cluster/` | @dkn16's Docker Slurm mock, the fidelity target |
| `results/` | append-only run records; see `results/README.md` |

## Purpose

This repo ("benchmarking-hpc-skills") is the testbed for **Benchmarking #4** from the
[Lightcone Research AAI4Science Developer Summit](https://github.com/LightconeResearch/AAI4ScienceDeveloperSummit)
(tracked as [issue #14](https://github.com/LightconeResearch/AAI4ScienceDeveloperSummit/issues/14)).

Scope for this 3-day hack (fixed as of Day 2 — see `docs/working-notes.md` for the full
discussion log):
1. An `INSTRUCTIONS.md` template HPC centers can host to tell agents (and humans) about
   platform resources, environments, and rules.
2. Simple skills that consume that template to discover/use resources efficiently and
   avoid abusive behavior (e.g. spamming the Slurm queue), plus a trace-analysis/feedback
   skill so an agent can summarize its own run for platform admins.
3. A benchmarking harness measuring whether standardized instructions actually improve
   agent experience/efficiency on HPC, not just whether they can be written.

- Project leads: @aboucaud, @dkn16, @djbard
- Communication: `#benchmarking-skills` on Discord
- Target: a live demo on a locally built Slurm cluster (summit Friday demo session)

**Current status**: two workstreams in progress — @aboucaud is exploring benchmarking
approaches/methodology, @dkn16 is setting up a mock Slurm cluster to benchmark against.

The broader context (from the AAI4Science summit synthesis doc, `docs/context.md`) frames
the specific gap this project addresses: HPC skills currently degrade across model
releases, there is no shared general→specific skill hierarchy, and HPC-specific
*benchmarking* of agent skills is missing entirely.

## Skills this project builds on

Rather than writing HPC skills from scratch, this project composes/benchmarks existing
ones. Read these before adding new skill content — new work here should extend or
combine them, not duplicate them:

- **[LightconeResearch/agent-skills](https://github.com/LightconeResearch/agent-skills/tree/feat/async-job-skills/skills/estimate)**
  (branch `feat/async-job-skills`, `skills/estimate`) — estimates CPU/memory/GPU/walltime
  for a job by running small pilot measurements inside an existing Slurm allocation and
  extrapolating, then writes the result into an ASTRA recipe's `resources` block. Notable
  conventions worth mirroring: distinguishes "inside a Slurm allocation" vs. "on a login
  node" vs. "local machine" before running anything; never launches a production run on
  its own; pads estimates with explicit safety factors (≥1.5x walltime, ≥25% memory).
- **[HolobiomicsLab/hpc-session](https://github.com/HolobiomicsLab/hpc-session)** (by
  @lfnothias) — a cluster-agnostic CLI (`hpc-session`) wrapping one multiplexed SSH master
  session so an agent can `open` a Slurm cluster session, `run`/`submit`/`watch`/`fetch`
  jobs, and `close`, without re-authenticating (including TOTP 2FA) per command. Hard
  rules from that skill that apply here too: never sit in `watch` for long-running jobs —
  submit, close, and poll `queue` later; never handle/store TOTP seeds, passwords, or
  scratch codes in messages, commits, or transcripts; site-specific facts (partition
  names, scratch paths, module versions) belong in a per-cluster notes file, not hardcoded
  into the skill.

Both are packaged as Claude Code **skills** (a `SKILL.md` with YAML frontmatter
`name`/`description`, plus supporting `docs/`, `templates/`, `examples/`, `lib/`, `bin/`
as needed). Any skill work added to this repo should follow that same packaging shape so
it can be dropped into an agent's skill set directly.

## Working on this repo

- The demo target is a real local Slurm cluster, but benchmarking work in the meantime
  runs against the mock Slurm cluster @dkn16 is setting up — guardrails from the source
  skills above (rate-limit Slurm requests, don't monopolize queues, don't sit in blocking
  watch loops) apply to any benchmarking code/harness written here regardless of target.
- Do not hardcode credentials, TOTP seeds, hostnames, partitions, or account names for the
  demo cluster into source or commits; treat them the way `hpc-session` does — as
  per-deployment config the user supplies, not something to invent.

### Nothing here reaches a real cluster

`.claude/settings.json` denies `ssh`, `scp`, `rsync`, `hpc-session`, and every bare Slurm
command (`sbatch`, `squeue`, `sacct`, `srun`, `module`, …). That is deliberate and should
not be relaxed.

The harness exercises Slurm through **simulator shims placed on a sandbox `PATH`**, invoked
by the agent under test inside its own sandbox — never by the agent developing this repo.
If you find yourself wanting to run `sbatch` directly, you are about to test against the
wrong thing.

### Several people work here agentically

Five collaborators, some driving agents. Conventions that keep them from colliding:

- **One branch per person per topic**, named `<user>/<topic>`. Use a git worktree if you're
  running more than one agent at once.
- **Stage only the files you changed.** Never `git add -A` or `git add .` — another
  session's half-finished work may be sitting in the tree.
- **Verify the live tree before committing** (`git status`, `git diff --staged`). Do not
  assume the working copy is the one you left.
- **Results are append-only.** Never edit or delete an existing `results/` run directory.
- **Small, single-purpose PRs.** Each one should be reviewable in under ten minutes; issue
  #1 lists the intended sequence.

### Skills under test are data, not workspace skills

Candidate skills live in `skills/candidates/<tier>/` and are installed into episode
sandboxes by the harness. Do **not** install them into `.claude/skills/` — that would put
them in the context of every agent working on the repo and contaminate every episode.

Personal agent overrides belong in `.claude/settings.local.json`, which is gitignored.
