# benchmarking-hpc-skills

Testbed for **Benchmarking #4** from the [Lightcone Research AAI4Science Developer
Summit](https://github.com/LightconeResearch/AAI4ScienceDeveloperSummit) — see
[issue #14](https://github.com/LightconeResearch/AAI4ScienceDeveloperSummit/issues/14).

## What this is

We want to demonstrate that giving coding agents explicit guidelines ("skills") for
operating an HPC platform measurably improves how they behave on it — loading modules,
submitting and monitoring Slurm jobs, and estimating resource needs — instead of
requiring interactive sessions and hand-holding for every task.

This repo builds a bench to measure that improvement on a locally built Slurm cluster,
composing existing skills rather than writing HPC guidance from scratch:

- [`LightconeResearch/agent-skills`](https://github.com/LightconeResearch/agent-skills/tree/feat/async-job-skills/skills/estimate)
  (`skills/estimate`) — resource estimation via pilot runs
- [`HolobiomicsLab/hpc-session`](https://github.com/HolobiomicsLab/hpc-session) — a
  cluster-agnostic wrapper for driving Slurm over one authenticated SSH session

The broader motivation is documented in [`docs/context.md`](docs/context.md), notes
synthesized from the summit's sessions on trust, research infrastructure, and agent
architecture for science. Concrete, in-progress planning for this project specifically
lives in [`docs/working-notes.md`](docs/working-notes.md).

## Status

Early stage — no code yet. Target is a live demo on a locally built Slurm cluster.

- Project leads: @aboucaud, @dkn16, @djbard
- Communication: `#benchmarking-skills` on Discord

See [`CLAUDE.md`](CLAUDE.md) for details on the skills this project builds on and
conventions to follow when adding code here.
