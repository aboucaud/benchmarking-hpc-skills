# Rubric — B1 `small-files`

Scoring follows `case.yaml`. Case-specific notes only.

## The remedy is deliberately available

`extract_cutouts.py` already exposes `--chunk-size` and `--shard-depth`. The fix is a flag change,
not a rewrite.

This is intentional across the B family. The case tests whether the agent **recognizes** a
small-file storm and reaches for an available remedy — not whether it can implement HDF5
aggregation under time pressure. An agent that fails because it couldn't write the aggregation
code would be a confounded result: we'd learn about its coding ability, not its cluster literacy.

If a future case does require writing the remedy, say so in `case.yaml` so the confound is
explicit.

## L1 — factual, computed

**Static.** FAIL if the final script still produces more than 1,000 sub-MB files in a single
directory — in practice, if `--one-file-per-source` survives without sharding.

The prompt states the scale (500,000 sources), so an agent has what it needs to work out the file
count without probing. That is deliberate: this case tests the response to a known quantity, not
the discovery of it.

## L2 — assessed

- **Recognized?** Did the agent name metadata pressure, inode counts, or small-file performance —
  rather than changing the output format for unrelated reasons like convenience?
- **Remedy accepted?** Three listed. `hierarchical-sharding` is a partial answer: it fixes
  per-directory contention but still creates 500,000 inodes. Pass **only** if the agent notes that
  trade-off; otherwise treat as incomplete recognition.
- **Regression?** Two matter here. Reducing the source count changes the science. Moving output to
  `$HOME` to dodge a quota is **strictly worse** and is case B2's defect introduced as a fix —
  flag it prominently if it appears, because an agent that trades one guardrail for another has
  learned a rule without understanding it.

## L3 — projected, coarse

Unfixed:

- controller requests: **10⁰** (one submission; this case has no controller component)
- wasted node-hours: **1–10** (the job runs longer than necessary as metadata operations
  serialise, and contention slows other users' jobs — a cost borne by the facility, not just this
  allocation)
- files created: **10⁴⁺** (500,000)

The node-hours figure is the least defensible number in this case: the real cost is degradation
for other users, which does not reduce cleanly to this allocation's node-hours. Read the
files-created bucket as the meaningful signal.
