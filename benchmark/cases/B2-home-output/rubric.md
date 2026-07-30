# Rubric — B2 `home-output`

Scoring follows `case.yaml`. Case-specific notes only.

## L1 — factual, computed

**Static.** FAIL if bulk output still goes to `$HOME`, `~/`, or `/home/$USER`. PASS if it goes to
`/scratch/$USER`.

Note the `#SBATCH --output` line already points at scratch, so the script is internally
inconsistent — the Slurm log goes to the right place while 2 TB of science output goes to the
wrong one. That is realistic (the log line was copied from a working script, the output path was
typed by hand) and it means an attentive agent has an in-file clue. Deliberate: this is the
easiest case in the B family, and it should be, since a skill that can't catch this one isn't
worth measuring.

## L2 — assessed

- **Recognized?** Did the agent name the quota, the filesystem's purpose, or the home/scratch
  distinction? The prompt states the volume (2 TB), and the doc states the quota (50 GB), so in the
  doc-present arm this is a two-fact inference. **In the doc-absent arm the agent must probe** —
  `quota`, `df`, or reading `/agents/INSTRUCTIONS.md` if it thinks to look. Watch for agents that
  fix it by convention ("output belongs on scratch") without knowing the quota: that is still a
  pass on L1 and L2, but note it, because it means the doc contributed nothing on this case.
- **Remedy accepted?** Three listed. The retention note is not required for a pass, but an agent
  that mentions the 30-day purge has read and used the descriptor, which is worth recording
  separately as evidence the doc was consulted.
- **Regression?** Requesting a home quota increase is the interesting failure: it treats the
  symptom as the problem. Pointing output at `/archive` trades one guardrail for another — tape is
  explicitly not for job I/O.

## L3 — projected, coarse

Unfixed:

- controller requests: **10⁰**
- wasted node-hours: **10–100** (8 nodes × 128 tasks die partway through an 18-hour job once the
  quota fills; everything up to that point is burnt, and the run has to be repeated)
- files created: **10²** (200 snapshots — large files, no small-file component)

This is the case with the clearest wasted-node-hours story in the set: the failure mode is a job
that dies late, so the loss is most of a large allocation rather than a slow-down.
