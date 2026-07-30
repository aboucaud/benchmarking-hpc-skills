# Rubric — C1 `over-limit`

Scoring follows `case.yaml`. Case-specific notes only.

## The defect announces itself, but only if you know the limits

Unlike the B family, nothing in this script looks wrong on its face. `--time=48:00:00` is only a
defect relative to a published limit. So this case, like C3, measures whether the agent **acquired
the queue table** — from the doc, from `sinfo`, or from `scontrol show partition` — before
submitting.

An agent that submits and lets the stub reject it, then reacts to the rejection, has still learned
the limit, just expensively. Record that path separately: `discovered_by_rejection` is a pass on
outcome but a different behaviour from `discovered_by_reading`, and the difference is exactly what
the doc-present arm is supposed to change.

## L1 — factual, computed

**Static.** Compare the final script's `--time` and `--nodes` against the declared maximum for the
partition it targets, read from `center.yaml:partitions`. FAIL if either exceeds.

Thresholds come from the descriptor, never hard-coded here — if someone edits the queue table, this
detector has to follow, or the case silently starts testing the wrong thing.

## L2 — assessed

- **Recognized?** Did the agent name the partition limit? Two acquisition routes are both valid
  (read the doc, or probe `sinfo`/`scontrol`); note which one it used, since that distinction is
  the doc's whole value proposition on this case.
- **Remedy accepted?** Three listed. `checkpoint-and-chain` is the reference — the technically
  correct remedy (per @djbard's review): it stays within the 24 h `standard` limit at `qos_factor:
  1`. `move-to-extended` is also accepted, but `extended` carries `qos_factor: 1.5`, so it costs
  more per node-hour; an agent that mentions that has read the table rather than pattern-matched on
  "extended sounds longer". An agent that moves to `extended` without noticing its 4-node cap got
  the right answer for the wrong reason — pass, flagged as incomplete recognition.
- **Regression?** `walltime-truncated-blindly` is the important one. Changing `--time` to 24 h with
  no checkpointing turns a *rejected submission* into a job that runs 24 hours and is killed with
  nothing usable — **48 wasted node-hours where the defect cost zero**. An agent that does this has
  made things strictly worse, and the scoring must not reward it for producing a submittable
  script. The script header states the solver checkpoints every 30 minutes, so the information
  needed to do this properly is present.

## L3 — projected, coarse

Unfixed:

- controller requests: **10⁰** (one rejected submission)
- wasted node-hours: **<1** — the submission is rejected, so nothing burns. The real cost is the
  researcher's turnaround, which this bucket does not capture.
- files created: **10⁰**

If instead the agent applies the `walltime-truncated-blindly` regression:

- wasted node-hours: **10–100** (2 nodes × 24 h killed mid-run, plus the rerun)

That inversion — where the "fix" costs two orders of magnitude more than the defect — is the most
useful thing this case can show, and it is the reason regressions are scored rather than just
noted.
