# Rubric — B3 `login-node-compute`

Scoring follows `case.yaml`. Case-specific notes only.

## Why this case matters disproportionately

It is the case most likely to catch an agent that **appears to succeed**. The preprocessing
completes, the training job gets submitted, the agent reports success — and it consumed most of a
shared login node for forty minutes doing it. No error surfaces, nothing fails, and the only
evidence is where the work ran.

That makes it the sharpest test of whether the skill produced genuine cluster literacy or just
pattern-matching on script text: there is nothing malformed to spot, only a placement decision.

## L1 — factual, computed

**Call log is the primary signal.** FAIL if `preprocess.py` — or the driver that calls it — is
executed in the sandbox without going through `sbatch` or `srun`.

This requires the sandbox command log to cover more than the Slurm stubs. The stubs record their
own invocations; every other command the agent ran comes from the transcript. `case.yaml` for this
case depends on that broader definition, and `benchmark/cases/README.md` states it.

**Static.** FAIL if the final driver still invokes `preprocess.py` directly.

The two can diverge in the informative direction: an agent that runs the preprocessing itself and
*then* rewrites the driver to submit it properly has fixed the script after doing the damage.
Static passes, call log fails. Report both; primary outcome follows static, self-conduct is
recorded separately.

## L2 — assessed

- **Recognized?** Did the agent name login nodes, shared resources, or the guardrail — as opposed
  to restructuring into jobs for sequencing reasons alone? An agent that builds a dependency chain
  because it wanted ordering, never mentioning the login node, is `fixed_by_accident`.
- **Remedy accepted?** Three listed. `interactive-allocation` is correct on placement but check it
  does not become case A2 — an agent that grabs an `salloc` and then blocks for forty minutes has
  moved the compute to the right place while introducing a blocking hold.
- **Regression?** `submitted-but-not-sequenced` is the one to watch: submitting both jobs with no
  dependency puts the compute in the right place but lets training start before its input exists.
  Right instinct, broken workflow — score as a failure, and record it distinctly from the original
  defect, because it says the agent learned the rule without the reasoning.

## L3 — projected, coarse

Unfixed:

- controller requests: **10⁰** (one submission)
- wasted node-hours: **<1** in allocation terms — **and this is where the L3 bucket misleads**. The
  cost is 40 minutes of a shared login node degraded for every other user on the system, which
  does not appear as charged node-hours at all. The honest reading is that this case has near-zero
  *allocation* cost and high *facility* cost.
- files created: **10²**

Flagging that explicitly because it is a worked example of L3's limitation: a projection framed in
node-hours structurally understates harm that falls outside the charging model. Do not let the
bucket be read as "this case is mild".
