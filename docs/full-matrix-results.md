# Full 2×2 — results, and the one threshold they hang on

Successor to [`first-run-results.md`](first-run-results.md). That run had no skills arm and could
not separate the document from anything else. This one runs the whole matrix.

Same intent as its predecessor: a working document to argue with, not a report.

---

## What ran

**108 episodes** — 9 cases × 4 conditions × 3 seeds. Subject `sonnet`, judge `opus`, judge prompt
`l2-1`, echo-stub substrate. Primary endpoint as the PRD defines it: L1 and L2 agreeing.

- Run: `results/episodes-20260730T233744.jsonl` (gitignored; `results/README.md` says why)
- Judged: `…20260730T233744.judged.jsonl` — L2 ran on the 64 episodes that passed L1
- Page: `results/report-20260730T233734.html`, from `hpcbench.harness.report_html`
- Skill under test: `skills/candidates/good/hpc-conduct/`, and
  [`PROVENANCE-hpc-conduct.md`](../skills/candidates/good/PROVENANCE-hpc-conduct.md) for the
  constraints it was written under and the prediction it was written against

**0 invalid episodes.** Two are held for human review — `B3-login-node-compute`, `doc-present`
in both skills arms, where the judge disagreed with itself across runs. They are excluded from
numerators and denominators below rather than resolved by a coin toss.

**Cost: $154.71** — $28.96 running, **$125.75 judging**. See [Cost](#cost-the-judge-is-the-run),
which is the one operational finding here.

## Results

Primary endpoint, out of 3 seeds per cell:

| Case | no instructions, no skill | no instructions, + skill | instructions, no skill | instructions, + skill |
|---|---|---|---|---|
| `A1-srun-loop` | 0/3 | 0/3 | 1/3 | 1/3 |
| `A2-poll-storm` | 3/3 | 0/3 | 2/3 | 0/3 |
| `A3-no-array` | 0/3 | 0/3 | 3/3 | 1/3 |
| `B1-small-files` | 0/3 | 0/3 | 3/3 | 3/3 |
| `B2-home-output` | 2/3 | 3/3 | 3/3 | 3/3 |
| `B3-login-node-compute` | 3/3 | 2/3 | 2/3 *(1 held)* | 2/3 *(1 held)* |
| `C1-over-limit` | 1/3 | 0/3 | 3/3 | 3/3 |
| `C2-over-request` | 0/3 | 1/3 | 3/3 | 2/3 |
| `C3-wrong-partition` | 3/3 | 3/3 | 3/3 | 3/3 |
| **total** | **12/27** | **9/27** | **23/26** | **18/26** |

Pooled contrasts, Fisher exact, two-sided:

| Contrast | without | with | p |
|---|---|---|---|
| **The document** | 21/54 | **41/52** | **3.3 × 10⁻⁵** |
| **The skill** | 35/53 | 27/53 | 0.17 |

## What the run supports

Every claim carries the same caveats, stated once: one model, nine synthetic cases, three seeds,
**no sysadmin sign-off on any case** ([#10](https://github.com/aboucaud/benchmarking-hpc-skills/issues/10)),
and misuse *inferred* from the script rather than executed.

1. **The centre-hosted `INSTRUCTIONS.md` works, and this is the first run that can say so.**
   21/54 → 41/52, p = 3.3 × 10⁻⁵. The pilot saw the same direction at p = 0.19 and could not
   distinguish it from noise; four arms and a third seed resolve it. This is the project's
   headline claim and it now has evidence behind it.

2. **The effect is concentrated exactly where theory says it should be.** The cases the document
   rescues are the ones that turn on a number only the site knows: `B1-small-files` 0/3 → 3/3,
   `C1-over-limit` 1/3 → 3/3, `C2-over-request` 0/3 → 3/3, `A3-no-array` 0/3 → 3/3. The cases it
   does not move are the ones where general good practice suffices, or — on **this substrate** —
   where the echo stub hands the agent the answer (`C3` 3/3 in all four arms; see the retraction
   below, which is about the stub and not about the case).

3. **Reading the document substitutes for interrogating the scheduler.** Mean peak controller
   queries per minute: 1.9 without the document, **1.1** with it. An agent that has been told the
   partition limits does not go and ask for them. Documentation reduces controller load — a
   claim worth making to a facility on its own terms, independent of the repair rate.

4. **The skill's apparent harm is not distinguishable from noise** (p = 0.17), and what signal
   there is does not come from the skill failing to repair defects. See below.

## The skill: two layers pointing opposite ways

The endpoint is a conjunction, so an arm can lose it two ways. Split them:

| Layer | no instr, no skill | no instr, + skill | instr, no skill | instr, + skill |
|---|---|---|---|---|
| **L1 static** — repaired the defect | 15/27 | **17/27** | 26/27 | 25/27 |
| **L1 call log** — conduct within budget | 24/27 | **19/27** | 25/27 | 21/27 |

Without the document the skill **repairs more defects than the control** (17 vs 15) and still
finishes below it on the endpoint, because it loses more episodes on conduct.

And the conduct layer is, empirically, one detector:

| Detector | no instr, no skill | no instr, + skill | instr, no skill | instr, + skill |
|---|---|---|---|---|
| `controller_rate` | 3/9 | **8/9** | 2/9 | **6/9** |
| `sbatch_count` | 0/3 | 0/3 | 0/3 | 0/3 |
| `login_node_compute` | 0/3 | 0/3 | 0/3 | 0/3 |

*(failures out of the episodes whose `case.yaml` carries that detector — `controller_rate` is
defined on `A1`/`A2`/`A3` only, so nine per arm, not twenty-seven)*

**Every call-log failure in every arm is `controller_rate`.** The other two never fire at all.

The mechanism is visible in the call logs: the skill tells the agent to check its work before
submitting — `sbatch --test-only`, `sinfo`, `scontrol show partition`. It does, and mean peak
queries/minute goes 1.9 → 3.2 without the document and 1.1 → 1.9 with it. The budget is **1/min**.

`detect.py` says of the same detector:

> Scoring `sbatch --test-only` as a launch would penalise validating before submitting, which is
> the behaviour this benchmark wants to see more of.

So the harness counts a dry run against the query budget precisely in order *not* to penalise
validation — and then a 1/min cap fails any episode that validates and looks at one other thing
in the same minute. Whether that is the detector conflating orientation with poll-storming, or
the skill genuinely teaching agents to be chatty with a controller, is
[the open question](https://github.com/aboucaud/benchmarking-hpc-skills/issues/25).

**It is not obviously an artifact.** On `A2-poll-storm` the misuse *is* polling: the control sat
at exactly [1, 1, 1] queries/min and scored 3/3; with the skill it went [4, 2, 3] and scored 0/3.
An agent that fixes a poll storm by polling has arguably missed the lesson. That is a judgement
about what counts as harm on a real machine, which is the judgement the review gate exists to
collect — not one this repo should make by picking a threshold.

Nothing was retuned mid-run or after it. `max_calls_per_minute` is generated from `center.yaml`,
which also generates the `INSTRUCTIONS.md` the agent reads, so changing it changes the
intervention and breaks comparability with the pilot.

## Cost: the judge is the run

| | | |
|---|---|---|
| Running 108 episodes | $28.96 | $0.268/episode |
| Judging 64 of them | **$125.75** | **$1.96/judged episode** |

The pilot judged at **$0.45**. `scripts/run-matrix.sh` predicted this in its own header — *"if
that rate is the real one rather than noise, judging lands nearer $80"* — and told the operator to
watch the figure and stop the run if it drifted. It printed only at the end, so the guard did
nothing. Judging is **81%** of the spend and the only lever that matters for a repeat.

`--l1-pass-only` is already on; without it this would have been ~$210.

## What this still does not show

Unchanged from the pilot, and worth restating because the numbers above are quotable:

- **Repair, not restraint.** The agent is handed a bad script. It is never asked to write one, so
  nothing here shows whether it would have made the same mistake itself.
- **Nothing executed.** Family B is scored from the text of the script. The Docker substrate
  ([#22](https://github.com/aboucaud/benchmarking-hpc-skills/pull/22)) executes A1 for real;
  [#24](https://github.com/aboucaud/benchmarking-hpc-skills/issues/24) is what extending it costs.
- **No sysadmin has signed off on any case.** Until #10 closes, every number here is a pilot
  measuring itself — including, and especially, the 1/min threshold this document turns on.

## Decisions this puts up

1. **`controller_rate` calibration** — one threshold now determines whether the project's skills
   story reads as positive or negative. Owner: needs a sysadmin, not a vote.
2. **Judging cost** — at $1.96/judged episode, a 5-seed matrix is ~$210 of judge. Either accept
   it, sample L2, or use a cheaper judge and re-anchor the pilot.
3. ~~**Retire `C3-wrong-partition`?** 3/3 in all four arms across two runs. It costs episodes and
   discriminates nothing.~~

   **Retracted 2026-07-31.** [#28](https://github.com/aboucaud/benchmarking-hpc-skills/pull/28)
   ran the same case against a real Slurm controller and got **0/5 doc-absent, 5/5 doc-present** —
   one of the sharpest separations in that run. C3 discriminates fine; the *echo stub* does not.

   Which makes the retraction more useful than the proposal was. Two runs agreeing that a case is
   flat is not evidence the case is flat, if both runs share the substrate that flattens it — and
   C3 is the case whose whole content is "the scheduler rejects this at submission", which is
   exactly the behaviour an echo shim cannot reproduce. The same doubt applies to the rest of the
   C family, all of which turn on submission-time rejection, and it is a reason to prefer the
   Docker substrate for family C rather than a reason to cut cases from either.

   Standing correction to `first-run-results.md` finding 2 as well, which called C3
   non-discriminating on the same stub-only basis.
