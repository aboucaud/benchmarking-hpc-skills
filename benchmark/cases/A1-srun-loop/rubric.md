# Rubric — A1 `srun-loop`

The prompt is deliberately neutral. It says "run this on the cluster" and gives no hint that
anything is wrong. Noticing is part of what's being measured, so a case where the agent had to be
told there was a problem is not a pass.

## L1 — factual, computed

**Static, on the final `job.sh`:**

- **FAIL** if `srun`, `sbatch` or `salloc` is still invoked from inside a loop iterating more
  than 4 times.
- **PASS** if launches per script are at or below 4 — a job array, a single `srun`, or a
  launcher that fans out inside one allocation.

Count the loop's iteration count, not the number of `srun` tokens in the file. `srun` written
once inside `for i in $(seq 1 2000)` is 2000 launches.

**Call log, on the agent's own conduct:**

- Any minute containing more than one Slurm call is a self-conduct violation, recorded
  separately. It does not affect the primary outcome for this case — an agent can fix the script
  correctly while polling too eagerly, and those are two different findings.

## L2 — assessed

Three questions, each answered against `case.yaml`:

1. **Recognized?** Did the agent state, before or while changing it, that launching thousands of
   `srun` steps overloads the controller — or something equivalent? An agent that rewrote the
   script to an array without ever indicating why gets `fixed_by_accident`, which counts as a
   pass on L1 but is reported separately. This distinction is the whole point of the skill: we
   want to know whether it taught the agent to *see* the problem.
2. **Remedy accepted?** Match against `accepted_remedies`. Any of the four passes. A remedy not
   on the list that a reviewer would accept is a **bug in the case, not a failure by the agent** —
   flag it for the review gate and add it to the list.
3. **Regression?** Check `forbidden_regressions`. Shrinking the catalogue from 2000 entries, or
   inserting sleeps to slow the launch rate while still issuing 2000 requests, are failures
   dressed as fixes.

Note whether the agent adjusted the walltime after converting to an array. Copying
`--time=02:00:00` onto each of 2000 array tasks is not a controller-abuse failure and does not
fail this case, but it is worth recording — it's the over-request defect (C2) appearing
spontaneously, and the same signal C2 tests for directly.

## L3 — projected, coarse

Unfixed, on a real cluster:

- controller requests: **10³⁺** (~2000 near-simultaneous step requests)
- wasted node-hours: **1–10** (one node held for the duration while steps queue and contend)
- files created: **10²** (one output per light curve, not a small-file storm at this scale)

Report buckets. Anything more precise is invented.

## Judge inputs

The judge receives `case.yaml`, `reference.sh`, this rubric, the agent's final `job.sh`, the
stub call log, and the transcript. It never receives the credit it would need to invent a new
accepted remedy — it matches against the list and flags anything unlisted for human review.
