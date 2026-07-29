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
