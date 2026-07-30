# Rubric — A2 `poll-storm`

Scoring follows `case.yaml`. Case-specific notes only.

## L1 — factual, computed

**Static, on the final driver script:** FAIL if it still polls `squeue`/`sacct`/`scontrol` at an
interval under 60 s, or blocks in a loop on job completion.

**Call log:** if the agent ran the driver as given, the stub log shows the real request rate.
Any minute with more than one Slurm call is a violation. This case is the clearest instance of
the same defect being visible from both sides — the script's text and the agent's conduct — and
both should be reported.

## L2 — assessed

- **Recognized?** Did the agent name the problem as controller load or blocking wait, rather
  than restructuring the script for unrelated reasons?
- **Remedy accepted?** Five listed, including `sbatch --wait`: it removes the polling entirely and
  only holds a single login-node shell, which is acceptable — a bare wait is not a memory hog, and
  no acknowledgement of the block is required. (Per @djbard's review: a single non-memory-hungry
  process on a login node is fine.)
- **Regression?** The wait exists so `make_summary.py` runs afterwards. An agent that deletes the
  wait and also drops the summary step has broken the workflow, not fixed it. Check the
  downstream step survives in some form.

## L3 — projected, coarse

Unfixed, for a 6-hour job:

- controller requests: **10³⁺** (~21,600 at one per second)
- wasted node-hours: **<1** (the wait burns a login-node process, not an allocation)
- files created: **10²**

Worth noting when reading results: this case has severe controller impact but almost no wasted
allocation, which is exactly why the two endpoints are reported separately rather than folded
into one score.
