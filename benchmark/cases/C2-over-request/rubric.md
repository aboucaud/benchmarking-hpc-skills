# Rubric — C2 `over-request`

Scoring follows `case.yaml`. Case-specific notes only.

## The clue is in the script's own comment

Line 14 of `job.sh` says: *"Single GPU, single-threaded data loading — the model does not shard
across devices."* Directly above a `--gres=gpu:4` request.

That is deliberate and it makes this the one case in the C family solvable **without** the doc or
any probing: the script contradicts itself in plain text. So C2 is the control for C1 and C3. If an
agent catches C2 but not C1/C3, it can read scripts but hasn't acquired the cluster's facts — which
is a finding about the doc's contribution, not about the skill.

An agent that instead runs the workload to measure actual GPU utilisation is doing the `estimate`
skill's job properly. Nothing executes here so it can't, but record the intent if it appears: it is
the behaviour Phase 2's simulator would reward.

## L1 — factual, computed

**Static.** Compare the request against `detection.workload_actually_uses` (1 GPU, 8 CPUs, not
exclusive). FAIL if the final script requests more GPUs than 1, retains `--exclusive`, or requests
substantially more cores than the workload uses.

"Substantially" needs a threshold to be computable: fail above 2× the declared CPU need, so the
`right-sized-with-headroom` remedy (12–16 cores) passes while 64 does not.

## L2 — assessed

- **Recognized?** Did the agent connect the request to the workload's actual needs? Quoting the
  script's own comment counts. An agent that trims the request because "4 GPUs seems like a lot"
  without reference to the workload is `fixed_by_accident`.
- **Remedy accepted?** Three listed. `array-over-shards` is the most sophisticated — it uses the
  four GPUs productively instead of merely not requesting them — and should be scored as a full pass
  even though it changes the job's shape more than the reference does. Bonus signal if the agent
  mentions `accel`'s `qos_factor: 4`.
- **Regression?** `gpus-dropped-entirely` is C3's defect arriving as a fix, and the second instance
  in this set of an agent trading one guardrail for another (B1 has the same shape). If both appear
  across a run, that pattern is worth reporting on its own: it suggests the skill teaches rules
  without the reasoning that orders them.

## L3 — projected, coarse

Unfixed, for a 3-hour job:

- controller requests: **10⁰**
- wasted node-hours: **1–10** — 3 GPUs and ~56 cores idle for 3 h on a partition charged at 4×.
  Small per occurrence, which is the point: this is the defect that costs most in aggregate because
  it is invisible and repeated, not because any single instance is large.
- files created: **10⁰**

Also worth noting and not captured by any bucket: an exclusive whole-node request queues
substantially longer than a one-GPU request, so the researcher waits longer for a job that needed
less.
