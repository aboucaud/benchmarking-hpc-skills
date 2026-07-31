---
title: "C1 — over the partition limit, and the fix that costs more"
---

**Family C, wrong resources.** The script asks for a 48-hour walltime on a partition whose
ceiling is lower. Slurm rejects it outright, so the defect costs nothing at all: a rejected
submission burns zero node-hours.

The full record for this case — what happened across all twelve episodes, with
the audit figure — is on [C1-over-limit](cases/case-C1-over-limit.md).

## The contrast

Without the document:
{astra:value col=prevented where="case=C1-over-limit doc=absent skills=none"}`outputs.per_case_grid`
of
{astra:value col=scored where="case=C1-over-limit doc=absent skills=none"}`outputs.per_case_grid`.
With it:
{astra:value col=prevented where="case=C1-over-limit doc=present skills=none"}`outputs.per_case_grid`
of
{astra:value col=scored where="case=C1-over-limit doc=present skills=none"}`outputs.per_case_grid`.

But read the doc-absent arm with its stratifier attached:
{astra:value col=rejected where="case=C1-over-limit doc=absent skills=none"}`outputs.per_case_grid`
of those episodes had a submission **rejected by the scheduler**, and
{astra:value col=norun where="case=C1-over-limit doc=absent skills=none"}`outputs.per_case_grid`
submitted nothing at all. The cell is also marked unstable across its own seeds
({astra:value col=unstable where="case=C1-over-limit doc=absent skills=none"}`outputs.per_case_grid`).
Almost nothing here is attributable to the document.

## The finding this case exists for

:::{astra} findings.quiet_regression_beats_static_analysis
:::

The modal repair is to truncate the walltime from 48 hours to 24 and resubmit, with no
checkpointing added. Every layer of a naive benchmark scores that a success:

| Layer | Verdict on the truncated fix | Why |
|---|---|---|
| Task completion | pass | The job ran. |
| Static analysis | **pass** | `partition_limits` asks whether the request is *legal*, and it now is. |
| L2 judge | **fail** | Matches the forbidden regression `walltime-truncated-blindly`. |

The job now starts, runs for 24 hours, hits the wall with no checkpoint, and produces
nothing. The repair converts a **zero-cost rejection into a full wasted allocation** — two
orders of magnitude more expensive than the defect it replaced.

This is why a matched forbidden regression is decisive in the endpoint even against an L1
pass. Routing it to human review, as an earlier version did, discarded the clearest result
in the run.

## What it implies for anyone building one of these

A benchmark that scores only completion, or only the final artifact, will report this
agent as having succeeded — and will keep reporting it, run after run, because the failure
is quiet. The defect is loud and cheap; the plausible fix is silent and expensive.

:::{astra} decisions.judge_model
:::
