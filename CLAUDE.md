# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository is a **greenfield project** — at present it contains only a `LICENSE`
file. There is no build system, source tree, or test suite yet. The sections below
describe what this repo is *for* and what it will be built out of, so that whichever
Claude instance starts adding code makes choices consistent with that plan rather than
guessing. Once real code, configs, or CI lands, this file should be updated with actual
build/lint/test commands and a description of the resulting architecture.

## Purpose

This repo ("benchmarking-hpc-skills") is the testbed for **Benchmarking #4** from the
[Lightcone Research AAI4Science Developer Summit](https://github.com/LightconeResearch/AAI4ScienceDeveloperSummit)
(tracked as [issue #14](https://github.com/LightconeResearch/AAI4ScienceDeveloperSummit/issues/14)).

Goal: demonstrate that giving agents explicit guidelines ("skills") for operating an HPC
platform measurably improves their ability to act as competent cluster citizens — loading
modules, submitting/monitoring Slurm jobs, and estimating resource needs — instead of
requiring interactive sessions for everything.

- Project leads: @aboucaud, @dkn16, @djbard
- Communication: `#benchmarking-skills` on Discord
- Target: a live demo on a locally built Slurm cluster (summit Friday demo session)

The broader context (from the AAI4Science summit synthesis doc) frames the specific gap
this project addresses: HPC skills currently degrade across model releases, there is no
shared general→specific skill hierarchy, and HPC-specific *benchmarking* of agent skills
is missing entirely. This repo exists to fill that last gap — build a bench that measures
whether a given skill package actually improves agent behavior on a Slurm cluster, not
just to write another skill.

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

- This is meant to run against a **real local Slurm cluster**, not a mock — guardrails
  from the source skills above (rate-limit Slurm requests, don't monopolize queues, don't
  sit in blocking watch loops) apply to any benchmarking code/harness written here too.
- Do not hardcode credentials, TOTP seeds, hostnames, partitions, or account names for the
  demo cluster into source or commits; treat them the way `hpc-session` does — as
  per-deployment config the user supplies, not something to invent.
