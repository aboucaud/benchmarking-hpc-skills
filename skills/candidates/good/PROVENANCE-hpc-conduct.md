# Provenance of `hpc-conduct`

This bundle is an **input to the benchmark** — the intervention whose value the `skills` axis
is trying to measure. How it was written therefore determines what the measurement means, so
it is recorded here rather than left to memory.

> **This file lives beside the bundle, not inside it, and must stay there.** The harness copies
> the bundle directory wholesale into the episode sandbox, so anything under `hpc-conduct/`
> reaches the agent under test. This page describes the conditions matrix, states what the
> design predicts, and names a case's defect — handing it to the subject would disclose the
> experiment, pre-empt the open question of whether an agent should be told it is being
> evaluated, and leak a rubric into one case. It was inside the bundle for the length of one
> test episode; that episode was `scripted-reference` and read nothing, and no scored run used
> it. Keep documentation about the benchmark out of `hpc-conduct/`.

## Where it comes from

Adapted from [`HolobiomicsLab/hpc-session`](https://github.com/HolobiomicsLab/hpc-session)
(MIT, © 2026 CNRS and Université Côte d'Azur), specifically `docs/cluster-etiquette.md` and
`docs/guardrails.md`, plus the "Site-specific knowledge" section of its `SKILL.md`. This repo
is MIT as well; attribution is in the bundle frontmatter and at the foot of `SKILL.md`.

`hpc-session` is one of the two upstream skills this project was set up to compose rather
than duplicate (see the repo `CLAUDE.md`). Using it here is that instruction carried out.

**Why that source and not a fresh page.** Those documents were written for a different
purpose, for a different tool, before these benchmark cases existed. They were not aimed at
this benchmark, and nobody consulted a rubric to write them. A skill with that provenance is
evidence; a skill written by reading the cases is an answer key.

## What was removed

Everything about the transport layer: SSH multiplexing, the VPN, TOTP/2FA, and every
`hpc-session <subcommand>` invocation. None of it exists in an episode sandbox, and the
repo's `.claude/settings.json` denies those commands deliberately. The conduct layer was
kept and the commands rewritten as plain Slurm (`sbatch`, `sacct`, `salloc`, `seff`).

## Constraints this was written under

Both agreed before drafting, and both are checkable against this file's git history.

**1. The cases were not consulted.** No `benchmark/cases/*/rubric.md` and no
`reference.sh` was read while writing this bundle. Its sources are `hpc-session`,
`benchmark/center.yaml`, and `benchmark/generated/INSTRUCTIONS.md`. The case *identifiers*
and *families* were known — they appear in every report — but not the remedies a case scores,
nor the defect any case injects.

**2. General procedure, never a case-shaped prohibition.** A skill that says "do not write a
2000-iteration submission loop" is a rubric in disguise and would make the `skills-good` arm
win without telling anyone anything. A skill that says "many similar jobs are one array with
a throttle" is a skill. Where the two were hard to separate the general form was kept, even
where the specific form would have scored better.

## The design decision that matters most

**This bundle deliberately contains none of the site's own numbers.** No partition names, no
walltime ceilings, no filesystem paths, no quota figures, no required account string, no
polling rate.

That is not an omission. The conditions matrix crosses the site *document* with the *skill*,
and if the skill carried the site's numbers then `skills-good` would be a copy of
`doc-present` and the 2×2 could not separate them — the interaction the whole design exists
to measure would be unmeasurable by construction.

So the split is: **the skill teaches procedure and where to look; the document supplies the
facts.** Where the skill gives a rule of thumb ("poll on the order of a minute, not a
second") it explicitly defers to the site if the site states a rate. This mirrors
`hpc-session`'s own stance — *anything true of only one cluster belongs in that cluster's
notes; read them before guessing, and ask rather than inventing* — which is, stated
independently and before this benchmark, the thesis the `INSTRUCTIONS.md` arm is testing.

A consequence worth predicting out loud: if this is right, `skills-good` alone should help
*less* than `doc-present` alone on cases that turn on a site-specific number, and the two
together should beat either. If instead the skill alone matches the document alone, the skill
has leaked site facts and this bundle needs rewriting.

## Known weakness

`B4-foreign-scratch-path` was authored after the pilot **by the same person who wrote this
bundle**, so its defect was known while this was being drafted — constraint 1 covers the
rubric but not the memory. The "a path is only valid on the machine that defines it"
paragraph is therefore weaker evidence than the rest of the page, and B4 should be reported
separately from the eight cases that predate it, or excluded when this bundle's effect is
quoted.

## What is missing

The `degraded/` tier. Without it this axis measures skill **presence**, not skill
**quality**, and no claim that *this particular skill* is worth adopting is supported —
only that having something beats having nothing. See `../README.md`.
