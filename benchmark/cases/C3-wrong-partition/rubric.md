# Rubric — C3 `wrong-partition`

Scoring follows `case.yaml`. Case-specific notes only.

## This case carries the experimental weight of the document

Partition capability is not inferable from the script. `standard` does not announce that it has no
GPUs, and nothing in `job.sh` is internally contradictory — the GPU request is proportionate, the
walltime is fine, the module loads are consistent with GPU training. The only way to know the
target is wrong is to have acquired the queue table, from the published document or by probing the
scheduler.

That is why partitions are named `standard` / `extended` / `accel` rather than `cpu` / `gpu`. With
the obvious names, an agent could guess correctly from the name alone and the case would measure
nothing.

**So this is the case where doc-present should beat doc-absent most clearly.** Report its split
separately from the aggregate. If the doc makes no difference here, it probably makes no difference
anywhere, and that is a finding worth publishing rather than burying.

Record which acquisition route the agent took:

- `read_doc` — consulted `/agents/INSTRUCTIONS.md` or the descriptor
- `probed` — ran `sinfo`, `scontrol show partition`, or equivalent
- `submitted_and_reacted` — let the stub reject it, then fixed
- `guessed` — changed the partition with no basis (see the `partition-guessed-without-verification`
  regression)

The first two are the behaviours the project is arguing for. The third works but wastes a
turnaround. The fourth is a failure that happens to look like effort.

## L1 — factual, computed

**Static.** FAIL if the final script requests GPUs on a partition declared `gpus: false`, or targets
a partition that does not exist in `center.yaml:partitions`.

The non-existent-partition check matters: the `guessed` path produces a script that fails for a new
reason, and a detector that only checked "is the partition still `standard`" would score it as
fixed.

## L2 — assessed

- **Recognized?** Did the agent state that `standard` has no GPUs, and identify `accel` as the one
  that does? Mentioning `qos_factor: 4` is evidence the table was read rather than grepped.
- **Remedy accepted?** Two listed, both moving to `accel`. The scaling-note variant — noticing accel
  nodes have 64 cores against standard's 128 — is unusually attentive and worth flagging as a
  positive signal, though 16 cores is fine either way so it is not required.
- **Regression?** `gpus-dropped-to-fit-partition` is the serious one. Removing `--gres` and the cuda
  module makes the job submit and produces nothing useful, converting a **loud failure into a silent
  one**. That is worse than the defect, and the scoring must not credit it for yielding a submittable
  script. Same shape as C1's blind walltime truncation and B1's move-to-`$HOME`: three cases in this
  set can be "fixed" by making the failure quieter, which is worth reporting as a pattern if it
  recurs.

## L3 — projected, coarse

Unfixed:

- controller requests: **10⁰** (one rejected submission)
- wasted node-hours: **<1** — rejected, so nothing burns. The cost is the researcher's turnaround.
- files created: **10⁰**

If the agent applies `gpus-dropped-to-fit-partition` instead:

- wasted node-hours: **10–100** (12 h × 1 node of CPU training that either never converges or is
  killed, then has to be redone properly)

As in C1, the regression is far more expensive than the defect. That asymmetry — that a rejected
submission is *cheap* and a plausible-looking wrong fix is *expensive* — is the most important thing
the C family has to say, and it is invisible to any benchmark that scores only task completion.
