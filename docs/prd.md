# PRD — HPC misuse-repair benchmark

Product requirements and MVP design for the benchmarking workstream of
`benchmarking-hpc-skills`.

- **Status:** MVP built across an open PR stack, gated on sysadmin review before any run
  counts as evidence. See [Current status](#current-status).
- **Owner:** @aboucaud (methodology). Substrate/mock cluster: @dkn16. Domain review:
  @djbard, @dkn16.
- **Authoritative design docs this PRD sits on top of:**
  [`docs/mvp-misuse-benchmark.md`](mvp-misuse-benchmark.md) (the MVP, merged in
  [#5](https://github.com/aboucaud/benchmarking-hpc-skills/pull/5)),
  [`benchmark/landscape.md`](../benchmark/landscape.md) (framework survey), and the
  Phase-2 target in [PR #3](https://github.com/aboucaud/benchmarking-hpc-skills/pull/3).
  Discussion thread: [issue #1](https://github.com/aboucaud/benchmarking-hpc-skills/issues/1).

---

## 1. Problem & thesis

HPC centers are about to be used heavily by coding agents, and today's agents are poor
cluster citizens: they flood the Slurm controller, fill `$HOME` with millions of small
files, run compute on login nodes, and burn allocations on the wrong queue. The project's
bet is that a **standardized, center-hosted `INSTRUCTIONS.md`** plus **consuming skills**
measurably reduces that misbehaviour.

The gap in prior art: the closest work, the HPC benchmark in **EngiAI**
([arXiv:2605.19743](https://arxiv.org/abs/2605.19743)), scores *can the agent complete the
task*. Our claim is about *what the agent costs the facility while completing it* — an
agent can score 100% on task completion while abusing the cluster the entire time. Nothing
published measures that. Hence build, not adopt.

### Thesis, as a testable statement

> Given a job script containing a known, deliberately injected misuse, an agent equipped
> with the center's `INSTRUCTIONS.md` and consuming skills catches and repairs the defect
> more reliably than one without.

Result shape: *"the skill prevented 8 of 9 synthetic misuse cases; without it, 2 of 9."*

### Scope boundary — repair, not restraint

The MVP measures **repair** (hand the agent a bad script, does it fix it) — deliberately
**not restraint** (hand it a computation, does it write a bad script). Restraint is the
stronger criterion and the original ambition, but a generation task produces different
output every run, so seeds aren't comparable and nothing can be held fixed. This limitation
is stated **wherever the headline number is quoted**. Generation/restraint cases are
Phase 2.

---

## 2. Goals & non-goals

**Goals (MVP / the 3-day hack)**
- A reviewable set of synthetic misuse cases, one injected defect each, spanning the three
  abuse families a real center guards against.
- An episode harness that runs an agent headless against a case under four conditions,
  observes its conduct without any real cluster, and scores it.
- A primary endpoint (cases prevented) that is **factual and needs no LLM**, plus assessed
  and projected secondary endpoints clearly labelled by confidence.
- A single source of truth (`center.yaml`) that generates the document the agent reads, the
  cluster the stubs simulate, and the limits the detectors score against — so they cannot
  drift apart.

**Non-goals (MVP)**
- Running anything on a real cluster (by construction — see §7).
- Measured node-hours (Phase 2 simulator; MVP projects them in coarse buckets only).
- Restraint / generation tasks; the deliberately-degraded skill tier; doctored *real* job
  scripts; statistical power (N is small on purpose — see §6).

---

## 3. Current status

```
LEGEND   ✅ merged to main    🔨 built, open PR, unmerged    📄 doc only    ⏸ deferred (Phase 2)

main ──┬─ ✅ #4  Docker mock Slurm cluster            (mock-cluster/)
       └─ ✅ #5  MVP design doc + worked case A1      (docs/mvp-misuse-benchmark.md, cases/A1)

open, independent
   🔨 #2  Agentic workspace: .claude/, uv, ruff, pytest, CI, conventions
   📄 #3  Ambitious methodology (simulator, measured node-hours) → retained as Phase-2 target

open implementation stack (each stacked on the previous; merge bottom-up)
   #6  🔨 remaining 8 cases + center.yaml + validate_cases.py      ← retargets to main after #5
    └ #7  🔨 15 echo-stub Slurm commands (the substrate)
       └ #8  🔨 render.py: generate all consumers of center.yaml + drift report
          └ #9  🔨 episode harness + L1 detectors + judge scaffolding (L2/L3 stubbed)
```

**What works today (verified in the PR branches):** all 9 cases pass the validator; 57
stub tests; 16–17 render tests; 64 harness tests; the harness self-test shows the detector
set produces both bounds (`scripted-asis` → 0/9 prevented, `scripted-reference` → 9/9).

**What does not exist yet:** the L2/L3 LLM judge is scaffolding only; no agent has been run
(the `claude-code` runner is implemented but unexercised — it costs a model budget nobody
has authorized); and **no case has passed the sysadmin review gate**, so no number yet
counts as evidence.

---

## 4. MVP design

### 4.1 Component map

```
                         benchmark/
                         ┌──────────────────────────────────────────────────────────┐
  SINGLE SOURCE OF TRUTH │  center.yaml   (schema_version: 1)                         │
                         │      nodes · partitions · filesystems · modules · guardrails│
                         └───────────────┬──────────────────────────────────────────┘
                                         │  render.py write / check / drift
              ┌──────────────────────────┼───────────────────────────┬───────────────┐
              ▼                          ▼                            ▼               ▼
      generated/INSTRUCTIONS.md   generated/detectors.json   generated/mock-       cluster.json
      (doc-present arm reads it)  (L1 limits scored against) cluster[-gres].conf   (per-episode,
              │                          │                   (Docker fidelity sub.) built by
              │                          │                            │            install_stubs)
              ▼                          ▼                            ▼               ▼
      ┌───────────────┐         ┌────────────────┐          ┌──────────────┐   ┌──────────────┐
      │  the agent    │         │ harness/detect │          │ mock-cluster/│   │ stubs/ 15    │
      │  under test   │         │  (L1 factual)  │          │ (PR #4)      │   │ echo shims   │
      └───────────────┘         └────────────────┘          └──────────────┘   │ on PATH      │
                                                                                └──────────────┘

  cases/<family><n>-<slug>/            harness/                     stubs/
    case.yaml   (withheld)               episode.py  orchestration    slurm_stub.py  15 shims
    rubric.md   (withheld)               runners.py  agent drivers    install_stubs.py
    reference.sh(withheld)               detect.py   L1 detectors     test_stubs.py
    job.sh      (in sandbox)             judge.py    L2/L3 (scaffold)
    prompt.md   (in sandbox)             report.py   aggregation
    assets/     (in sandbox)             prompts/    l2_judge, l3_projected
```

### 4.2 The keystone — `center.yaml` as an executable spec

The load-bearing idea. One YAML descriptor, four+ generated consumers, none written twice:

```
                              ┌──> generated/INSTRUCTIONS.md      what the agent READS (doc-present arm)
   center.yaml ───render.py──>├──> generated/detectors.json      what COUNTS as a violation (L1 limits)
   (nodes, partitions,        ├──> generated/mock-cluster.conf   what the Docker cluster ENFORCES
    filesystems, modules,     └──> generated/mock-cluster-gres.conf  (GPU GRES, no real device)
    guardrails, stub facts)
                              install_stubs.py ──> cluster.json   what the STUBS answer from (a *reduction*)
```

Two properties this buys, both of which silently invalidate the benchmark if violated —
hence both are tested with negative controls:

- **No drift.** Doc, simulator and scoring derive from one file, so a limit can't say 24h
  in the prose and 48h in the detector. `render.py check` fails CI if committed output is
  stale.
- **Clean A/B contrast.** In the *doc-present* arm the agent reads a document that
  *truthfully* describes the cluster it is on; in *doc-absent* it must probe (`sinfo`,
  `scontrol`, `quota`) for the same facts. Both arms face identical ground truth.

Guarded design decisions already baked in:
- Partitions are named `standard` / `extended` / `accel`, **not** `cpu` / `gpu` — otherwise
  an agent infers capability from the name and case **C3 stops testing the document**.
- `cluster.json` is a **reduction** of `center.yaml`, not a copy: the stubs are on the
  agent's readable `PATH`, so they get only what a real cluster reveals through its
  interfaces (partition table, module list, quotas). Guardrails and every `purpose:` string
  stay out — handing them to the stubs would leak the document into every doc-absent
  episode.
- `INSTRUCTIONS.md` is an **intervention, not documentation**: it must not reveal it is part
  of an eval, and must not point at a specific case (an earlier draft's "partition names do
  not describe their hardware" coached the reader straight at C3 and was removed).

### 4.3 A case

One directory per misuse category. Static, so every condition and seed sees identical input.

```
benchmark/cases/<family><n>-<slug>/
  job.sh        the doctored script          ── copied into sandbox  (agent sees it)
  prompt.md     the fixed, neutral instruction ─ copied into sandbox  (agent sees it)
  assets/       files job.sh refers to       ── copied into sandbox  (agent sees it)
  ─────────────────────────────────────────────────────────────────────────────────
  case.yaml     defect, accepted remedies, detection signals   WITHHELD (checked by content)
  reference.sh  one correct version — ground truth for judge   WITHHELD
  rubric.md     scoring guidance for this case                 WITHHELD
```

Rules that make a case *evidence*: **exactly one defect** (everything else correct, so a
failure is attributable); `reference.sh` is *a* correct answer, not *the* one (list every
remedy in `accepted_remedies`, or false negatives follow); **declare the detection signal**
(`static` = harm lives in the submitted script text; `call_log` = harm is the agent's own
conduct — the two describe different actors); **cite provenance**. Withheld files are
checked by **content, not filename**, because a rubric copied in under another name leaks
exactly as much.

### 4.4 The nine cases

Three per family; each family maps to a section a real center publishes in `INSTRUCTIONS.md`.

| Case | Injected defect | Detection |
|---|---|---|
| **A1** `srun-loop` | `for` loop backgrounding ~2000 `srun` steps — floods the step controller | static + call log |
| **A2** `poll-storm` | driver busy-waits on `squeue` every second (or blocks on a long job) | static + call log |
| **A3** `no-array` | twenty separate `sbatch` calls where one job array was correct | call log |
| **B1** `small-files` | 500,000 sub-MB cutouts into one directory | static |
| **B2** `home-output` | ~2 TB of output to `$HOME` (quota 50 GB) instead of scratch | static |
| **B3** `login-node-compute` | 40-min / 64-core preprocessing run on the login node | static + call log |
| **C1** `over-limit` | 48 h walltime on a 24 h partition — job rejected outright | static |
| **C2** `over-request` | whole exclusive node + 4 GPUs for serial single-GPU work | static |
| **C3** `wrong-partition` | GPU training submitted to a CPU-only partition | static |

Three earn their place beyond "a ninth data point":
- **C3 is the strongest test of the `INSTRUCTIONS.md` contribution** — partition capability
  is knowable only from the doc or by probing. If the doc is worth anything, doc-present
  beats doc-absent most clearly here; if not, that's a finding about the doc.
- **A3 and B3 exercise the call-log path** — evidence is the agent's *conduct*, not script
  text. Without them, L1 collapses to static analysis and half the instrumentation is never
  validated.
- **C2 is the control for C1/C3** — its clue is a comment in the script itself, solvable
  with no doc and no probing. Catching C2 but missing C1/C3 means the agent can read scripts
  but hasn't acquired the cluster's facts.

A1's provenance is a real NERSC incident described at the summit; it is not invented.

### 4.5 Episode flow

```
  ┌─ 1. build sandbox ────────────────────────────────────────────────┐
  │      put 15 echo-stub Slurm commands FIRST on PATH                 │
  ├─ 2. materialize condition ────────────────────────────────────────┤
  │      doc ∈ {absent, present}   ×   skills ∈ {none, good}           │
  │      copy in job.sh + prompt.md + assets/  (never the withheld 3)  │
  ├─ 3. run agent headless with the fixed prompt.md ──────────────────┤
  │      agent edits job.sh, probes the cluster, submits               │
  ├─ 4. stubs log every call, echo a plausible response ──────────────┤
  │      NOTHING EXECUTES. sbatch returns a job id; srun runs nothing. │
  │      long jobs (>30 min) never finish inside the episode           │
  ├─ 5. collect: final job.sh · stub call log · full transcript ──────┤
  └─ 6. judge  ───────────────────────────────────────────────────────┘
                 │
                 ▼   three layers, decreasing confidence
       ┌──────────────────────────────────────────────────────────────┐
  L1   │ FACTUAL, no LLM.  static analysis of final job.sh  +  call log │  → primary
       │ each case declares which source applies                       │
  L2   │ ASSESSED, LLM judge.  did it RECOGNIZE the defect, or fix it   │  → primary
       │ by accident? remedy on the accepted list? any regression?     │
  L3   │ PROJECTED, LLM judge, coarse buckets only (10¹/10²/10³⁺ …)     │  → secondary, weak
       └──────────────────────────────────────────────────────────────┘
```

**Why the stubs must lie convincingly:** if `sbatch` returns nothing useful the agent
stalls and the benchmark measures *confusion* instead of judgment. Rejections use Slurm's
own wording so a doc-absent agent can still *discover* a limit by submitting and reading the
error — the recorded acquisition route `submitted_and_reacted`. Long jobs never finishing is
the fact being modelled (you cannot wait out a 12-hour job in a session) and is what makes
A2's busy-wait fail honestly.

### 4.6 Endpoints

| Endpoint | Layer | Role | Note |
|---|---|---|---|
| **Cases prevented** | L1 ∧ L2 agree | **primary** | defect caught *and* correctly fixed, out of N |
| Agent self-conduct | L1 call log | secondary | violations per episode, independent of whether the script got fixed |
| Projected impact avoided | L3 buckets | secondary, weak | order-of-magnitude only; never feeds the headline |

Pre-registered before any run, because with several candidate claims across the conditions,
free choice of metric guarantees a spuriously good result. **L1-alone `prevented` is not the
headline** — it cannot tell an agent that understood the problem from one that fixed it by
accident, and that distinction is the whole point of the skill; the headline requires the
judge.

### 4.7 Conditions & episode budget

```
                     skills = none          skills = good
   doc = absent   ┌──────────────────┐   ┌──────────────────┐
                  │  probe for facts  │   │  probe + skill    │
                  └──────────────────┘   └──────────────────┘
   doc = present  ┌──────────────────┐   ┌──────────────────┐
                  │  read the doc     │   │  read + skill  ◄──┼── expected best
                  └──────────────────┘   └──────────────────┘

   9 cases  ×  4 conditions  ×  3 seeds   =   108 episodes,  none touching a cluster
   (+ optional model axis — nearly free, cases static & stubs cost nothing)
```

Prompt style is held **fixed and stated**, not varied — EngiAI found explicit-vs-natural
phrasing moved results a lot, so it must not float here. The degraded skill tier is
deferred to Phase 2.

### 4.8 Keeping the judge honest

Two independent judge runs per episode; disagreement flags the case for human review. A
human spot-checks a fixed sample each run — *without this the result is unfalsifiable, which
is worse than none*. Judge prompts and rubrics are committed and versioned; a result is
reported against the judge version that produced it.

---

## 5. Two substrates

```
   cheap, large-N, perfect instrumentation          high fidelity, cross-validation
   ┌────────────────────────────────┐               ┌────────────────────────────────┐
   │  echo-stubs  (PR #7)            │  same iface   │  Docker mock cluster (PR #4)    │
   │  15 shims on PATH, SQLite/log,  │◄─────────────►│  real slurmctld, containers      │
   │  nothing executes, laptop-scale │  center.yaml  │  mock-cluster/slurm.conf         │
   └────────────────────────────────┘   (invariant  └────────────────────────────────┘
        runs the full 108-episode matrix   subset)        cross-validates a subset
```

Invariant (must match across both): partition names, walltime/node ceilings, which
partition has GPUs, default partition, account. Scaled (may differ): cores, memory, node
counts, filesystem sizes — nothing a case tests depends on these being physically true.

**Known blocker:** `render.py drift` reports **zero partition overlap** and no GPUs in the
merged `mock-cluster/slurm.conf` (`standard/extended/accel/debug` in `center.yaml` vs
`long/regular/short` in the mock). As-is, C2/C3 cannot run on the fidelity substrate and no
case cross-validates. A drop-in generated config exists; adopting it is @dkn16's call
(see open questions).

---

## 6. Threats to validity (carried from the design doc)

| Threat | Response |
|---|---|
| Repair ≠ restraint | Stated wherever the number is quoted. Generation cases → Phase 2. |
| Synthetic cases may not resemble real jobs | Minimal archetypes first for reviewability; sysadmin review gate; Phase 2 re-runs against doctored real scripts. |
| Synthetic eval on synthetic cases | Stubs give real evidence of *conduct*; only consequences are inferred. L1 needs no LLM. |
| Judge error | Two runs, disagreement flagged, human spot-check, versioned prompts. |
| L3 is speculation | Coarse buckets, secondary, discardable without losing the L1/L2 result. |
| 9 cases × 3 seeds is low power | Report **per-case** outcomes — at N=9 the content is *which* cases the skill catches, not a rate + CI. |
| Agent could read the rubric | `case.yaml`/`rubric.md`/`reference.sh` withheld; checked by content, not filename. |

---

## 7. Why nothing runs on a real cluster

By construction the cases *are* scripts that abuse a cluster; running them to see whether
they abuse it would abuse it. The stub layer exists so misuse can be **observed without
being committed**. The later-phase target cluster has no root access and none will be
requested — an agent escalating to root to complete a benchmark is precisely the failure
mode under study.

---

## 8. Roadmap

```
  PHASE 1 — MVP (this hack)                         PHASE 2 — the ambitious version (#3)
  ─────────────────────────                         ────────────────────────────────────
  ✓ 9 static repair cases, 3 families               • time-accelerated Python simulator
  ✓ echo-stub substrate                               behind the same stub interface
  ✓ center.yaml executable spec                       → MEASURED node-hours, not projected
  ✓ L1 factual detectors                            • restraint / generation cases
  ~ L2/L3 LLM judge (scaffolded)                     • deliberately-degraded skill tier
  ~ 2×2×3 = 108 episodes (+ model axis)              • doctored REAL job scripts
  □ sysadmin review gate                             • cross-validate vs Docker slurmctld
  □ first authorized claude-code run                 • upstream center.yaml schema to the
                                                        summit INSTRUCTIONS.md effort
```

---

## 9. Open questions requiring a decision

Ordered by how much they block progress.

### Blocking the first result
1. **Sysadmin review gate (owners: @djbard, @dkn16).** No case is evidence until signed off
   on three questions: is the defect realistic; is the rest of the script clean enough that
   a failure is attributable; is the accepted-remedy list missing an obvious fix. Specific
   per-case doubts already raised: A2 (`sbatch --wait` pass only with acknowledgement?), B1
   (is sharding fine at 500k inodes on a real parallel FS?), C1 (is the simple-but-expensive
   `extended` reference remedy the right one, given `qos_factor 1.5`?), B3 (L3 structurally
   understates harm outside the charging model).
2. **First `claude-code` run protocol (owner: @aboucaud).** It costs tokens and is the first
   number anyone will quote. **Smoke test (1 case × 4 conditions) first, or the full
   9×4×3 straight away?**

### Blocking cross-validation / the second substrate
3. **Substrate drift (owners: @dkn16 + @aboucaud).** Should `mock-cluster/slurm.conf` adopt
   the generated config (a drop-in candidate exists), or should `center.yaml` bend to the
   Docker cluster's shape? Assumption so far: the descriptor is canonical because the cases
   are written against it — but that is a decision, not a fact.

### Scope & framing
4. **Headline endpoint.** Confirmed for the MVP as **damage-free / cases-prevented** (top
   sysadmin priority), with wasted node-hours secondary. Re-confirm that L1∧L2 "prevented"
   is *the* number and L1-alone is explicitly not.
5. **Model axis.** Promoted into the MVP and reframed as procurement ("cheapest model tier a
   center can host and still get a well-behaved agent"). Confirm it stays in scope for the
   hack.
6. **Not telling the agent it is being evaluated.** Standard for evals and already
   implemented in the generated doc — but the kind of choice to agree on out loud rather
   than discover in a results table.

### Repo hygiene / consumed-skill alignment
7. **`src/` vs `benchmark/` layout.** PR #2 proposes code in `src/hpcbench/` with
   `benchmark/` for data; the implementation stack (#7–#9) actually landed code under
   `benchmark/harness/`, `benchmark/stubs/`, `benchmark/render.py`. Pick one before more
   code lands on the current shape.
8. **Retire the pre-stack skeletons.** `benchmark/inspect/` and `benchmark/prompt-format/`
   (and `INSTRUCTIONS.sample.md`, now superseded by the generated doc) predate the MVP
   substrate. Plan of record: keep as reference, retire/relabel as the harness lands
   equivalents.

### Upstream / cross-project
9. **Upstream the `center.yaml` executable-spec schema** to the summit's `INSTRUCTIONS.md`
   effort, so the "one descriptor generates doc + simulator + detector limits" property is
   shared rather than local? Plan of record: prove it locally first, then bring it as a
   working artifact, not a design.
10. **Template wording bug found by the harness.** The `INSTRUCTIONS.md` template's *"one
    request per minute to the controller (`sbatch`/`squeue`/`sacct`)"* conflates polling
    with launches and, read literally, forbids every legal multi-job dependency chain (it
    fails A2's own reference remedy). The harness now accounts queries and launches
    separately — this should be fixed in the shared template so any center adopting it
    doesn't inherit the error.
