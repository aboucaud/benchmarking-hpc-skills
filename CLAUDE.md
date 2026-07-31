# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

The MVP misuse-repair benchmark has landed (PRs #4–#9). Python lives under `src/hpcbench/`
(uv project at the repo root), tests under `tests/`, and the run's data — `center.yaml`,
`cases/`, `generated/` — under `benchmark/`; `mock-cluster/` is the Docker Slurm mock; design
in `docs/mvp-misuse-benchmark.md` and `docs/prd.md`. Entry points are run by path, e.g.
`uv run --with pyyaml src/hpcbench/harness/episode.py …` (each has a bootstrap that puts `src`
on `sys.path`).

## Build / test / verify

All commands run from the repo root through the root uv project (never global pip). Entry
points and tests add `pyyaml`/`pytest` inline with `--with` (matching the module docstrings);
CI runs these same commands, so they and the docs cannot drift:

- `uv run --with pyyaml src/hpcbench/validate_cases.py` — case ↔ center.yaml consistency gate
- `uv run --with pyyaml --with pytest pytest tests -q` — tests
- `uv run --with pyyaml src/hpcbench/render.py check` — fail if `benchmark/generated/` is stale
- `uv run --with astra-tools astra validate benchmark/astra.yaml` — the experiment spec
- `uv run --with astra-tools astra universe check benchmark/universes/<u>.yaml -a benchmark/astra.yaml` — once per universe
- Calibration (the end-to-end check): `src/hpcbench/harness/episode.py all --runner scripted-asis` must give **0/9** and `--runner scripted-reference` **9/9** prevented

## The ASTRA / MySTRA layer

`benchmark/astra.yaml` declares the *experiment* — decisions, the output DAG, findings —
and `benchmark/*.md` renders it as a MyST report where every measured value is interpolated
from the episode records at build time. Regenerate after a run, in this order:

```
uv run --with pyyaml     src/hpcbench/astra_results.py   results/episodes-*.judged.jsonl
uv run --with matplotlib src/hpcbench/astra_figures.py
uv run --with pyyaml     src/hpcbench/astra_case_flow.py results/episodes-*.judged.jsonl
cd benchmark && myst build --html          # or `myst start`
```

`benchmark/pages/cases/case-*.md` are **generated** — one "what happened" page per case,
every count taken from the records. Edit the generator, never the pages. The hand-written
pages (`pages/a3-no-array.md` and friends) carry the *argument* and link to them.

Three rules this layer lives by, each learned the hard way:

- **Never reimplement the endpoint.** `astra_results.py` imports `report.endpoint_of`.
  Scoring with `judge.combine` instead drops unjudged L1 failures from the denominator and
  reports ~100%. `tests/test_astra.py` pins this.
- **`astra.yaml` declares no cluster facts.** Partitions, limits and guardrails live in
  `center.yaml`; restating them here recreates the drift `render.py` exists to prevent.
- **A finding never states a count.** Findings render beside live values from whichever run
  is active, so a hard-coded number reads as describing that run. Counts belong in a metric;
  `scope` names the run a finding came from. Both are enforced by tests.

The active universe is **the first file in `benchmark/universes/` when sorted**, and MySTRA
takes the universe id from the *file stem* — so `active_full_matrix.yaml` is named to sort
first on purpose. Renaming it silently repoints the whole site.

Three more filename/rendering traps, each of which fails quietly rather than loudly:

- **MyST derives a route from the file stem and flattens directories.** A generated
  `cases/A3-no-array.md` collides with `pages/a3-no-array.md` and becomes `/a3-no-array-1`,
  with which page wins the bare slug depending on build order. Generated pages carry a
  `case-` prefix for that reason.
- **A block embed mints a project-wide identifier**, so each ASTRA output may be
  `:::{astra}`-embedded on exactly one page. Reference it inline anywhere else.
- **MyST resolves image paths relative to the page file**, while MySTRA emits them relative
  to the project root — hence the gitignored `results` symlinks in `pages/` and
  `pages/cases/`. Without them the build reports "Cannot find image" and would publish a
  figureless site; the deploy guards against that by counting figures.

Figures are saved **opaque, never transparent**. The site renders dark by default and the
figures use dark ink, so a transparent background makes their titles and `k/n` labels
invisible — which reads as "the numbers are missing" rather than as a styling bug.

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
- `benchmark/center.yaml` is the single source of truth for the synthetic cluster; the
  files in `benchmark/generated/` are produced by `render.py write` — edit the descriptor,
  never the generated output. `max_time` values must stay quoted (YAML 1.1 sexagesimal).

## Working conventions

- **Nothing here reaches a real cluster.** The harness exercises Slurm through simulator/echo
  shims inside a sandbox, so an agent developing this repo has no reason to call `sbatch`, `ssh`,
  or `hpc-session`. `.claude/settings.json` denies those (and reads of `.ssh`/`*.pem`/TOTP files)
  on purpose — don't relax it; wanting to run a bare Slurm command here means you're about to
  benchmark against the wrong thing.
- **Several people work here agentically.** Branch per person (`<user>/<topic>`); stage only the
  files you changed (**never `git add -A`** — someone else's half-finished work may be in the
  tree); verify the live tree before committing; keep `results/` append-only; prefer small PRs.
- **Skills under test are data.** Candidate skills live in `skills/candidates/<tier>/` and are
  installed into episode sandboxes by the harness. Never put them in `.claude/skills/` — that
  contaminates every episode with the thing being measured. (How a skill is delivered into the
  sandbox is still open — see `docs/first-run-results.md` Decision 1.)
