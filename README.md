# benchmarking-hpc-skills

Testbed for **Benchmarking #4** from the [Lightcone Research AAI4Science Developer
Summit](https://github.com/LightconeResearch/AAI4ScienceDeveloperSummit) — see
[issue #14](https://github.com/LightconeResearch/AAI4ScienceDeveloperSummit/issues/14).

## What this is

We want to demonstrate that giving coding agents explicit guidelines ("skills") for
operating an HPC platform measurably improves how they behave on it — loading modules,
submitting and monitoring Slurm jobs, and estimating resource needs — instead of
requiring interactive sessions and hand-holding for every task.

Scope for this 3-day hack, as of Day 2:
- An `INSTRUCTIONS.md` template HPC centers can host to tell agents (and humans) about
  platform resources, environments, and rules.
- Simple skills that consume that template to discover and use resources efficiently
  and avoid abusive behavior, such as spamming the Slurm queue.
- A trace-analysis/feedback skill so an agent can summarize its own run and report back
  to platform admins, per the template's feedback section.
- A benchmarking harness to measure whether standardized instructions actually improve
  agent experience/efficiency on HPC — not just whether they can be written.

This repo composes existing skills rather than writing HPC guidance from scratch:

- [`LightconeResearch/agent-skills`](https://github.com/LightconeResearch/agent-skills/tree/feat/async-job-skills/skills/estimate)
  (`skills/estimate`) — resource estimation via pilot runs
- [`HolobiomicsLab/hpc-session`](https://github.com/HolobiomicsLab/hpc-session) — a
  cluster-agnostic wrapper for driving Slurm over one authenticated SSH session

See [`docs/README.md`](docs/README.md) for an index of the project's documents and the
order to read them in — start with [`docs/prd.md`](docs/prd.md). The broader motivation is
in [`docs/context.md`](docs/context.md), notes synthesized from the summit's sessions on
trust, research infrastructure, and agent architecture for science; early planning for this
project specifically lives in [`docs/working-notes.md`](docs/working-notes.md).

## Status

Scope is fixed for this 3-day hack (see above). Two workstreams are currently in
progress:

- **Benchmarking approach/methodology** — @aboucaud
- **Mock Slurm cluster setup** — @dkn16

Target is a live demo on a locally built Slurm cluster.

- Project leads: @aboucaud, @dkn16, @djbard
- Communication: `#benchmarking-skills` on Discord

## Local Slurm cluster

[`mock-cluster/`](mock-cluster/) contains a self-contained two-node Slurm
cluster for local development and benchmark runs. It includes Docker Compose,
Slurm accounting, SSH access, and a smoke test; it has no Dagster dependency.

```bash
cd mock-cluster
docker compose up -d --build --wait --wait-timeout 180
./smoke-test.sh
```

See [`CLAUDE.md`](CLAUDE.md) for details on the skills this project builds on and
conventions to follow when adding code here.
