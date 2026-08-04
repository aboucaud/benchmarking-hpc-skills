---
title: A misuse-repair benchmark for HPC agents
---

Every episode hands an agent a job script carrying exactly one injected defect, plus a
neutral prompt — *"run this on the cluster"*. The question is not whether the agent
finished the task. It is whether the cluster would have been harmed.

:::{important} Read the caveats before the number
This page renders one run. It is a pilot, not a result. The cases carry
`review_status: pending`, and the review gate is a rule in this project: a case nobody
with sysadmin experience has signed off on is not evidence.
:::

## What was measured

The endpoint is {astra}`outputs.prevented_rate` — L1 and L2 agreeing that the defect was
repaired. In the focal arm of the active universe it is
{astra:value}`outputs.prevented_rate`.

That number should not be read on its own, for three reasons this benchmark keeps
deliberately separate from it:

- **{astra:value}`outputs.unstable_cells`** — cells whose own seeds disagreed. A cell at
  1/3 and a cell at 2/3 are both unstable while their rates differ, so the two questions
  are never averaged together.
- **Scheduler pushback.** {astra}`findings.scheduler_pushback_dominates`
- **Inaction.** An agent that edits the script and submits nothing has averted the defect
  and produced no science. Counted as `norun`, and neither a pass nor a failure.
- **Which experiment it is.** {astra}`outputs.intervention_manifest` carries the content
  hashes of the document, the skill bundle and the case files these episodes actually ran
  against, and counts the records that carry none. The arm labels cannot supply this —
  `doc-present` named two different documents across this project's history — so a rate
  whose material is unknown and one whose material is pinned must not read alike.
  {astra}`findings.option_ids_do_not_version_their_material`

## The experiment

The condition matrix, the substrates and the scoring layers are all declared in
`astra.yaml` rather than described here:

:::{astra} decisions.document
:::

:::{astra} decisions.substrate
:::

:::{astra} decisions.replication
:::

## Per-case results

:::{astra} outputs.per_case_grid
:::

## One case per family

Three cases, chosen because each shows something the aggregate hides:

- [**A3 — no job array**](pages/a3-no-array.md): the clearest case for the document.
- [**B3 — login-node compute**](pages/b3-login-node-compute.md): where a detector was
  wrong, and calibration could never have caught it.
- [**C1 — over the partition limit**](pages/c1-over-limit.md): where the plausible fix
  costs two orders of magnitude more than the defect.

## Findings

The layered scoring exists because of one recurring failure:
{astra}`findings.quiet_regression_beats_static_analysis`, worked through on the
[C1 page](pages/c1-over-limit.md).

:::{astra} findings.cells_unstable_across_seeds
:::

The calibration bounds are what keep the detectors honest:
{astra}`findings.calibration_bounds_are_load_bearing`.
