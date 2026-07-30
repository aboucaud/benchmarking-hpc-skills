# Benchmark methodology

How this repo measures whether HPC skills make coding agents better cluster citizens.

Status: **Phase-2 target.** This is the ambitious version — a time-accelerated simulator and
*measured* node-hours. It is **superseded for the hack** by the MVP
([`mvp-misuse-benchmark.md`](mvp-misuse-benchmark.md)), which answers a narrower question with
echo-stubs and projected node-hours; this document is kept as the direction of travel, not current
guidance. Discussion in [issue #1](https://github.com/aboucaud/benchmarking-hpc-skills/issues/1).

## What we're measuring, and why it isn't task completion

The project's claim is that publishing an `INSTRUCTIONS.md` and giving agents HPC skills
makes them behave better on a cluster. Today nothing measures that.

The closest prior art is the HPC benchmark in **EngiAI**
([arXiv:2605.19743](https://arxiv.org/abs/2605.19743)): a four-step Slurm orchestration task
— generate an sbatch script, submit it, monitor it, evaluate the result — scored 70%
step-completion / 15% config-correctness / 15% metric-extraction, over 10 seeds and two
models. Its authors note it reports no confidence intervals, no significance tests, no
sensitivity analysis, and no token or wall-clock accounting.

The deeper mismatch is what it asks. EngiAI asks **can the agent complete the task**. This
project's complaint — "agents are incompetent cluster citizens" — is about **what the agent
costs the facility while completing it**. An agent can score full marks on EngiAI while
hammering the controller with `squeue`, filling `$HOME` with a million small files, and
burning a week of allocation on a queue it should never have used.

So the benchmark measures harm and waste, and treats task completion as a gate rather than a
score.

## Endpoints

Priority order set by the project leads: avoid damage first, avoid wasted node-hours second.

### Co-primary 1 — damage-free episode rate

Fraction of episodes with **zero** violations across detector families A, B and C. Binary, so
no arbitrary weighting between incommensurable harms, and it answers the question an admin
actually asks: did the agent misbehave at all?

### Co-primary 2 — wasted node-hours per completed task

Charged node-hours minus minimum-necessary, decomposed into over-request, failed-job burn,
idle-in-allocation, and resubmission burn.

*Minimum-necessary* is a fixed reference cost committed in each task spec: the node-hours a
hand-written reference solution consumes, measured once at the same scale factor. It is a
per-task constant, never derived from the agent's own run — otherwise an agent that simply
does less work scores well.

Holm correction across the two primaries.

### Pre-registered secondaries

Per-family violation counts and severities; hand-holding (nudges to completion); simulated
wall-clock to verified result; tokens consumed. Reported with intervals, but not used to
support the headline claim.

Naming the primaries before any runs happen is deliberate. With several candidate claims
across six conditions, free choice of metric after the fact guarantees a spuriously
significant result.

## Detector families

Grouped to mirror the sections of the `INSTRUCTIONS.md` template, so every detector traces
back to a rule a center actually publishes.

### A. Controller load

- Slurm requests per minute: peak, and count of minutes exceeding the declared threshold
  (template default: one per minute).
- Blocking holds: wall-clock spent inside `watch`, `srun` or `salloc` waiting on a
  long-running job instead of submitting and polling later.
- Array-job omission: N separate `sbatch` calls for parametrically identical work where one
  array job was correct.

### B. Filesystem abuse

- Small-file storms: files under 1MB created per second and per episode, size-bucketed.
- Wrong filesystem: bulk data written to `$HOME` or another non-scratch path.
- Quota breaches against declared allocations.
- Login-node compute: measurable CPU consumed on the login node.

### C. Queue and resource misuse

- Wrong partition or QOS for the job type.
- Queue-limit violation: exceeding declared max-nodes or max-time, so the job is rejected and
  a full turnaround is wasted.
- Missing or wrong account.
- Over-request: charged for CPU, GPU, memory or walltime that went unused.
- Under-request: OOM or timeout, costing the burn plus a resubmission.

### Detection limitation

File **writes and creates** are reliably observable via FSEvents/inotify, sampled per second.
**Reads** of thousands of small files are not, without root-level tracing. Family B therefore
covers writes fully and reads only by inspecting the agent's tool-call trace. Stated here
rather than papered over.

## Architecture

### 1. Center descriptor: one YAML, three consumers

The `INSTRUCTIONS.md` template already declares node inventory, filesystems, queue limits,
charging policy and guardrails. Rather than hand-writing that prose and separately hard-coding
the same facts into a simulator and a scorer, a single YAML descriptor generates all three:

```
center.yaml ──┬──> INSTRUCTIONS.md   (what the agent reads, in the "doc present" arm)
              ├──> simulator config  (what the cluster actually enforces)
              └──> detector limits   (what counts as a violation)
```

Three consequences:

- In the `doc present` arm the agent reads a document that **truthfully** describes the
  cluster it is on; in `doc absent` it must probe for the same facts. Both arms face identical
  ground truth, so the contrast is clean.
- Violation thresholds derive from declared limits rather than being invented per detector.
  Doc, simulator and scoring cannot drift apart.
- Any center that writes a conforming descriptor can be simulated and benchmarked. This turns
  the template from prose into an **executable spec** — arguably a larger contribution than
  the A/B result itself.

### 2. Time-accelerated Slurm simulator

Shim executables (`sbatch`, `squeue`, `sacct`, `scancel`, `sinfo`, `srun`, `salloc`, `module`)
on the episode's `PATH`, backed by SQLite state. Every invocation is logged with real time,
simulated time, argv, cwd and caller pid. A clock scale factor means a two-week campaign runs
in minutes, so long-run behaviour is measured rather than only extrapolated. Queue waits are
sampled from a declared distribution; failures are injected per declared rules.

No container runtime required, so anyone can run the matrix on a laptop.

**Why the node-hour figures aren't invented.** Submitted scripts genuinely execute in a
sandbox at pilot scale, and the simulator measures true peak RSS and CPU time from the
subprocess. The task spec declares a production scale factor; charged node-hours are
measured-usage × scale, plus queue wait. *Requested vs used* — the core waste measurement — is
therefore observed, not modelled. It also puts the `estimate` skill's pilot-and-extrapolate
loop under honest test rather than taking its word for it.

A simulated filesystem layout (`/home`, `/scratch`, `/tape`, with quotas) and a
login-node/compute-node distinction make family B detectable.

This complements rather than replaces the Docker Slurm mock in `mock-cluster/`: the simulator
gives cheap large-N runs and perfect instrumentation, the Docker mock gives fidelity. Plan is
to cross-validate a subset of episodes against it behind the same interface.

### 3. Episode harness

For each `(task, condition, seed)`: build an isolated sandbox, materialize the condition,
launch the agent headless, capture the transcript, run verifiers, emit one `episode.json`.
Resumable, so a half-finished matrix continues instead of restarting.

Verifiers live **outside** the sandbox. An agent that can read its own grading criteria is
measuring nothing.

Hand-holding needs a human stand-in to be measurable at all, so the harness uses a
deterministic **lazy user**: whenever the agent stops short of the goal it receives a
scripted, content-free nudge ("continue"), and the nudge count is the metric. Reproducible,
and it maps to the real complaint that agents need babysitting.

### 4. Scoring and campaign projection

Correctness is a deterministic rubric gate, not an LLM judge: an episode that fails the gate
contributes its costs but earns no benefit.

Projection feeds per-episode unit costs into a fully parameterized campaign profile — jobs per
campaign, job-size mix, failure rate, queue-wait distribution, cost per node-hour, researcher
hourly rate — and reports savings as ranges, with one-at-a-time tornado sensitivity and a
Monte Carlo over the joint parameter space. Every knob ships with a documented default and a
plausible range. There is no hidden anchor dataset; the honest position is "here is the model
and here are its assumptions", not a single authoritative number nobody can defend.

## Experimental design

**Conditions — 6 cells.** `doc ∈ {absent, present}` × `skills ∈ {none, degraded, good}`.

The `degraded` tier is a deliberately vague skill with no guardrails and no estimation step.
It exists to prove discriminative power: a harness that cannot separate a mediocre skill from
a good one is only measuring skill *presence*, and any later claim that a specific skill is
worth adopting would be unsupported.

**Tasks — 4, escalating**, each targeting a documented failure mode:

1. **Discovery and hello job** — load a module, submit to the right partition with a valid
   account, report state. The documented baseline failure: `lc run` dies on module load.
2. **Resource estimation** — pilot-and-extrapolate to a declared production scale, then submit
   with correct resources. Scores over- and under-request directly.
3. **Twenty-job campaign** — array job versus twenty `sbatch` calls, with polite polling.
   Where controller load and blocking holds surface.
4. **OOM diagnosis and recovery** — detect via `sacct`, diagnose, resubmit corrected rather
   than blindly. Measures avoided burn.

**Budget.** 4 tasks × 3 seeds × 6 cells = 72 episodes.

**Statistics.** Paired by `(task, seed)` across conditions, with paired bootstrap confidence
intervals on every metric. Prompt style is held **fixed and stated** rather than varied:
EngiAI found explicit-versus-natural phrasing moved results substantially, so it should not
float here as an uncontrolled nuisance factor.

72 episodes is not a lot of statistical power. Effect sizes get reported with intervals, and
the limitation gets stated rather than glossed.

## Threats to validity

| Threat | Response |
|---|---|
| Simulator fidelity — node-hour figures are semi-synthetic | Guardrail counts are real call logs, and they are the primary endpoint. Cross-validate a subset against the Docker mock; label projected figures as projections throughout. |
| Headless agent runs aren't the interactive experience | Hand-holding is explicitly a proxy (nudge count) and stays a secondary endpoint. |
| Reward hacking on verifiers | Verifiers held outside the sandbox; task prompts describe goals, not grading. |
| Low power at 72 episodes | Paired design; report intervals, not just point estimates. |
| Skills may degrade across model releases | Not addressed by the 6-cell matrix. A model axis is deferred until the matrix shows signal — see open questions. |

## Open questions

1. Is `damage-free episode rate` the right primary, or should the headline be the continuous
   wasted-node-hours figure?
2. Should the descriptor schema be shared with the Docker mock in `mock-cluster/`, so both
   substrates read the same `center.yaml`?
3. Worth proposing the descriptor schema upstream to the summit's `INSTRUCTIONS.md` template
   effort, so the executable-spec property isn't local to this harness?
4. Add a model axis (Opus 5 / Sonnet 5 / Haiku 4.5) to test the "skills degrade across model
   releases" gap from `docs/context.md`? It multiplies the run budget several times over.
