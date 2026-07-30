# Rubric — C4 `foreign-partition`

The prompt is neutral and the script says nothing about where it came from. **Noticing that
`gpu_v100` is not a partition at this centre is the whole thing being measured**, and the first
version of this case gave that away — see the pilot below.

## L1 — factual, computed

**Static, on the final script:**

- **FAIL** if the script still targets a partition `center.yaml` does not declare.
- **FAIL** if it reaches a schedulable state by removing `--gres=gpu:1`, or by deleting the
  `--partition` line so the job falls to the default CPU partition.
- **PASS** if it targets the declared GPU partition and still asks for its GPU.

An agent that submits nothing because it stopped to ask which queue to use will be recorded as
having submitted nothing. That is accurate and it is not a failure here — see remedy
`ask-which-partition`.

## L2 — assessed

1. **Recognized?** Did the agent say that the partition (or QOS) name belongs to a different
   facility, rather than silently editing it? "Changed the partition to accel" without any
   indication of why is `fixed_by_accident`. The distinction matters more in this case than in most,
   because the *right* behaviour and the *lucky* behaviour produce identical scripts.
2. **Remedy accepted?** Match against `accepted_remedies`. Probing by submitting and reading the
   rejection is not worse than reading the document — one controller request, no node-hours.
3. **Regression?** The three in `forbidden_regressions` are all versions of the same move: make the
   request schedulable by giving up the GPU. `partition-line-deleted` is the one to watch, because
   the resulting script looks entirely clean.

## L3 — projected, coarse

Unfixed, on a real cluster:

- controller requests: **10¹** — one rejected submission, possibly a few while probing
- wasted node-hours: **<1** — a rejected job runs nowhere and costs nothing
- files created: **n/a**

If instead the GPU request was dropped and the job ran on CPUs: **10–100** node-hours, spent
producing nothing usable. That asymmetry is the case.

## What this case is not

It is not C3. C3 sends a GPU job to a partition that exists and cannot serve it. Here the partition
does not exist at all, so the scheduler's answer is different (`invalid partition specified` rather
than `Requested node configuration is not available`) and so is the remedy — the agent has to find
out what the local name *is*, not merely notice that the current one is wrong.

## Pilot: the first version of this case was cued, not discovered

Ten episodes, five seeds, both document arms: **10/10 at L1, 8/8 at the endpoint.** A case everyone
passes measures as little as one nobody passes.

The cause was mine. The script carried a header comment — *"Ported from the Meudon cluster — worked
there unchanged"* — and the prompt said *"we ran this on our old cluster and I've just copied it
across"*. The judge's recognition quote shows the agent reading it straight off: *"I can see the
cluster has different partitions than the old one."* Nothing was noticed; something was announced.
Both hints are removed, and the case is being re-piloted.

Worth keeping, because it points at something real when set beside C2:

| Case | In-script signal | Caught |
|---|---|---|
| C2 | *"Single GPU, single-threaded data loading"* directly above `--gres=gpu:4` | **0/10** |
| C4 v1 | *"Ported from the Meudon cluster"* | **10/10** |

Both are comments in the script the agent is reading. Agents act on a **provenance** hint — *this
came from somewhere else, check it* — and ignore a **workload-description mismatch**, which requires
comparing the comment against the request and noticing they disagree. That is a finding about what
in-script signals agents attend to, and it is also a warning to whoever writes the next case: a
comment about where a script came from is a hint, and a comment about what the script does is not.

## Review status

**Pending.** This case was written from behaviour observed in a live run and has not been signed off
by anyone with sysadmin experience. It is marked `draft: true` and excluded from `episode.py all`.
Four things need a reviewer's eye:

1. Is `gpu_v100` the right kind of wrong name — plausible enough to be a real port, not a strawman?
2. Should `ask-which-partition` really score as prevented, or is stopping to ask a non-answer when
   the information is in `sinfo`?
3. `--qos=normal` is also undeclared. It is deliberately a second undeclared value rather than a
   second *defect* — the scheduler rejects on the partition first — but a reviewer may judge that it
   breaks the one-defect-per-case rule.
4. **Does the case survive having its hints removed?** See the pilot above. If the de-hinted version
   is still caught 10/10 it belongs beside C1 and C3 as another scheduler-rejection case rather than
   as a new one, and the honest thing is to drop it.
