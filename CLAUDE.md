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
- `uv run --with pyyaml src/hpcbench/render.py check` — fail if a generated consumer is stale
  (covers `agents/INSTRUCTIONS.md` as well as `benchmark/generated/`)
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
- **`version:` in `astra.yaml` is the ASTRA spec version, not this document's.** Bumping it
  because the spec changed makes `astra validate` warn that the installed `astra-spec` is older,
  which reads as a real incompatibility. Leave it pinned to the spec being validated against.

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
- **`agents/INSTRUCTIONS.md` is generated too**, byte-identical to
  `benchmark/generated/INSTRUCTIONS.md`, and covered by `render.py check`. It is the copy the
  Docker substrate serves. It used to be hand-maintained and 1.85× longer, so `doc-present`
  meant a different intervention on each substrate — same seven guardrails, different
  surrounding document — which is why the two runs could not be pooled (#29). Do not hand-edit
  it, and do not add prose to the renderer that names a case's answer: an earlier draft told
  agents that partition names do not describe their hardware, which is C3's answer, and the
  hand-maintained copy said "GPU requests must use `accel`" outright.

## Working conventions

- **Nothing here reaches a real cluster.** The harness exercises Slurm through simulator/echo
  shims inside a sandbox, so an agent developing this repo has no reason to call `sbatch`, `ssh`,
  or `hpc-session`. `.claude/settings.json` denies those (and reads of `.ssh`/`*.pem`/TOTP files)
  on purpose — don't relax it; wanting to run a bare Slurm command here means you're about to
  benchmark against the wrong thing.
- **Several people work here agentically.** Branch per person (`<user>/<topic>`); stage only the
  files you changed (**never `git add -A`** — someone else's half-finished work may be in the
  tree); verify the live tree before committing; keep `results/` append-only; prefer small PRs.
- **An episode must stay in its arm, and this is checked.** `validity` has a fourth value,
  `contaminated`: the agent acted but the transcript contains verbatim text from the other arm's
  content. It is excluded from every rate via `report.UNSCOREABLE` — never counted as a pass or a
  failure — and reported by name. The check sees verbatim text only, so its count is a floor;
  paraphrase is invisible to it. `materialize` separately asserts the arm was *built* as labelled,
  which is the quieter failure (a doc-present episode with no document runs as a control and is
  counted as an intervention).
- **Skills under test are data.** Candidate skills live in `skills/candidates/<tier>/` and are
  installed into episode sandboxes by the harness. Never put them in `.claude/skills/` — that
  contaminates every episode with the thing being measured. (How a skill is delivered into the
  sandbox is still open — see `docs/first-run-results.md` Decision 1.)
- **A case's files may describe the workload, never the experiment.** `job.sh`, `prompt.md` and
  everything under `assets/` are handed to the agent, and they used to carry the answer: three
  cases shipped *"The defect in case A2 lives in the driver, not here"*, and C3's trainer said
  *"the defect is the partition, not the request"* — C3's answer, in the case whose Docker result
  is the sharpest here, read in 5 of 6 doc-present episodes and 0 of 6 doc-absent ones. Keep the
  physical facts (a GPU requirement, a memory footprint, a per-index cost); drop what the
  experiment thinks about them. `tests/test_case_fixtures.py` enforces this from `case.yaml`, so a
  new case is covered without anyone remembering the rule.
- **Every record says which intervention it ran, and something reads it.**
  `episode["intervention"]` carries content hashes of the document, the skill bundle and the case
  files, taken at materialization time on both substrates under the same field names. The label
  says which cell; this says which *version* of it. Without it, a matrix run against a skill
  `main` did not have (#34) and two substrates serving two documents under one label (#29) both
  looked identical in the data. `harness/provenance.py` is the reader: `astra_results.py`
  **refuses to publish** a pooled rate over records that disagree (`--allow-mixed-intervention`
  to override, and it still says so), `report.py` prints a "Which intervention ran" section, and
  `provenance.py … --tree` compares a run against the working tree — advisory, because the answer
  is usually "re-run rather than re-score" rather than an error.
  - **An absent stamp is unknown, never agreement.** Records predating the field cannot say what
    they ran against, and the easy bug is to let `None == None` read as "these match". They are
    counted as unstamped everywhere. The stub's 108 published records are permanently in this
    state; the Docker substrate's 90 are recoverable from `evidence.input_sha256`, which is what
    `src/mock_cluster/backfill.py` does — into a **new file**, never in place.
  - **`case_files_sha256` is comparable within a substrate only.** The stub appends the
    site-guidance pointer to `prompt.md` and Docker delivers its pointer in the prompt it sends,
    so an untouched case stamps two different digests. `document_sha256` and `skills_sha256` are
    cross-substrate by design — that is what makes #29 a question the data can answer.
- **Docker serves its own copies of the case assets.** `materialize_condition` copies
  `benchmark/cases/<case>/assets/` and then `files.update(agent_fixture_files(case))`, so where a
  name exists in `src/mock_cluster/fixtures/<case>/` that copy wins outright — seven cases,
  covering every file the fixture pass rewrote. Those were written separately and were already
  clean, so that leak was stub-only, but the rule now applies to both trees and
  `tests/test_case_fixtures.py` checks both. Editing one tree does not change what the other
  substrate's agents read.
