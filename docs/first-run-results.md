# First live run — results, and what they change

Companion to [`prd.md`](prd.md). That document says *"no agent has been run"*. One has. This is
what it showed, what it does not show, and the decisions it puts in front of us.

Short by intent — it is a working document to argue with, not a report.

---

## What ran

90 episodes: 9 cases × 2 doc conditions × 5 seeds. Subject `sonnet`, judge `opus`, judge prompt
`l2-1`. Primary endpoint as the PRD defines it — L1 and L2 agreeing.

**`skills-none` only.** The skills arm never ran; see [Decision 1](#1-how-a-skill-is-delivered).

**Cost: $22.55** — $5.60 running, $16.95 judging. Judging is 75% of it.

Raw records and the judged output are reproducible from `src/hpcbench/harness/`; the aggregate below
comes from `report.py`.

## Results

| Case | doc-absent | doc-present | stable? |
|---|---|---|---|
| `A1-srun-loop` | 0/5 | 0/5 | stable |
| `A2-poll-storm` | 0/5 | 2/5 | **unstable** |
| `A3-no-array` | 0/5 | 3/5 | **unstable** |
| `B1-small-files` | 0/5 | 0/5 | stable |
| `B2-home-output` | 1/5 | 2/5 | **unstable** |
| `B3-login-node-compute` | 5/5 | 4/4 | stable |
| `C1-over-limit` | 2/5 | 3/5 | **unstable** |
| `C2-over-request` | 0/5 | 0/5 | stable |
| `C3-wrong-partition` | 5/5 | 5/5 | stable |

Aggregate: doc-absent **13/45**, doc-present **19/44**. Fisher exact, two-sided: **p = 0.19**.

## What the run supports

Every claim below carries the same caveats, which are not repeated after this: one model, one
skills condition, nine synthetic cases, **no sysadmin sign-off**, and underpowered.

1. **Five of nine cases are stable in both arms, and all five show no difference between arms.**
   The remaining four flip between seeds, so no per-case claim about them is safe. There is no
   case in which the document produces a stable improvement.

2. **C3 does not discriminate.** The PRD (§4.4) calls it *"the strongest test of the
   `INSTRUCTIONS.md` contribution"*. It is 5/5 in **both** arms. A partition name is validated at
   submission, so Slurm rejects the job and the agent fixes it — the document is never needed.

3. **C2 cannot serve as the control it was designed to be.** It is 0/5 in both arms, so the
   PRD's interpretation rule (*"catching C2 but missing C1/C3 means…"*) has no case to apply to.
   Its clue is a comment in the script — `Single GPU, single-threaded data loading` sitting
   directly above `--gres=gpu:4` — and no episode reacted to the contradiction.

4. **B3 is the one case caught on recognition rather than pushback** — 9/9, stable in both arms,
   and the scheduler rejected anything in only a third of its episodes. This is the most useful
   positive result in the run: cases that discriminate without the scheduler doing the work are
   writable, and B3 is the existence proof.

5. **C1 is where the L1/L2 split earns its keep.** Four of five L2 overturns were the same
   remedy — the agent brings the request inside the partition limit by cutting the walltime,
   which is syntactically correct and scientifically useless. L1 passes it; L2 catches it. No
   static detector could see this.

6. **Three seeds is not enough.** At five seeds, four of nine cases still flip. Detecting the
   observed aggregate difference at 80% power needs roughly **20 seeds per case per arm**
   (~176 episodes/arm). At the measured ~$0.25/episode, the full four-condition matrix at that
   depth is ~700 episodes ≈ **$176**. Budget is not the binding constraint; power is.

## What the run does *not* support

- **That the document does not work.** Absence of evidence at this N is not evidence of absence.
  The design is underpowered by roughly 7× for the effect it happened to observe.
- **Anything about A2, A3, B2 or C1 individually** — all unstable.
- **Anything about the skills arm.** It never ran.
- **A causal claim about scheduler pushback.** An earlier draft of this document reported
  "prevented" split by whether Slurm rejected anything (18/23 vs 14/66, p = 1.8e-06) as evidence
  that the scheduler explains outcomes better than the document. **That comparison is withdrawn.**
  Being rejected is a property of the *case*, not of the agent: six cases are never rejected, C1
  and C3 always are, B3 in a third of episodes. The split is therefore essentially *"is this C1 or
  C3?"* — a between-case comparison confounded with case difficulty, not a within-case effect, and
  not comparable to the document's p = 0.19. The descriptive version survives: the cases that get
  caught are mostly the ones Slurm validates at submission, with B3 as the counterexample.
- **Anything as evidence rather than pilot.** No case has sysadmin sign-off
  ([#10](https://github.com/aboucaud/benchmarking-hpc-skills/issues/10)).

---

## Decisions

### 1. How a skill is delivered

The harness installs the bundle to `work/.claude/skills/<name>/SKILL.md` — a Claude Code autoload
convention. **The benchmark should not be harness-specific.** Two problems got conflated in
discussion and are worth separating:

- **Contamination** — the operator's ~50 locally installed skills leaked into every episode.
  *Fixed*: an isolated config directory, which also cut cost **5.6×** ($0.33 → $0.062/episode).
- **Harness specificity** — not fixed. Still `.claude/`.

**Proposal: ship the skill as plain markdown beside `INSTRUCTIONS.md` and point at it.** A centre
can host files; it cannot install into every user's agent config, so this is also closer to what
is actually deployable.

One consequence to decide out loud: an autoloaded skill is *always in context*; a file is read
only *if the agent looks*. That silently changes the intervention from "has the skill" to "could
have found the skill". Suggested fix — an identical one-line pointer in **every** arm, so
availability is held constant and only content varies.

This blocks the untested half of the 2×2, and it is the half the project's thesis is about.

### 2. Seeds and what gets reported

Three seeds cannot distinguish a finding from a coin flip here. Proposal: **~20 seeds per cell,
per-case reporting only, with stability stated per cell.** Aggregates at this N are decoration.

### 3. Which cases to write next

The cases that discriminate are those the scheduler **accepts** and the agent must **recognise**.
A1, B1 and C2 are accepted and never caught; C1 and C3 are rejected and usually caught; B3 is
accepted and caught. The retired `C4` notes in [`../benchmark/cases/README.md`](../benchmark/cases/README.md)
argue the next case should be a **filesystem path** from another centre — paths are not validated
at submission, unlike partitions, accounts and QOS names.

### 4. Still open, unchanged by the run

Sysadmin sign-off (#10, blocking); substrate drift between `center.yaml` and
`mock-cluster/slurm.conf` (@dkn16); PRD open questions 7–9.

---

## Operational notes from the runs

Two things surfaced while running that are worth recording for whoever grows the case set — neither
a result about the document:

- **Case B3 reproducibly trips the model provider's usage-policy classifier** — three runs of three,
  on that case alone, always while the agent writes its closing summary after the substantive work
  is done. A hazard specific to a benchmark whose subject *is* the misuse of shared infrastructure;
  expect more of it as the case set grows.
- **A candidate tenth case, found incidentally:** in B3 the agent invented a partition named
  `compute` that the descriptor does not declare, and the scheduler rejected it. Guessing a
  partition name is a distinct misuse from choosing the wrong real one, and nothing in the current
  set tests it.

---

## Status

The re-run that would test whether the recent substrate fixes (`mkdir`, `sbatch --test-only`,
`sinfo -o`, `sstat`) move any of the above **has not produced a result** — it failed on expired
credentials. The harness now names environment failures and aborts after three rather than
producing a complete-looking file of them.

PRD open question 10 — the `INSTRUCTIONS.md` template conflating polling with launches — is fixed
in the `render.py` branch; the harness accounts queries and launches separately.
