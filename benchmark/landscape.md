# Benchmarking landscape: measuring whether HPC instructions/skills help agents

Research notes for the benchmarking workstream (owner: @aboucaud). Goal: decide *how* to
measure whether a standardized `INSTRUCTIONS.md` + consuming skills actually improve an
agent's experience and efficiency on an HPC platform, and on what stack to build it.

**Punchline**: no off-the-shelf benchmark measures the thing we care about — whether
standardized instructions make the agent a *better cluster citizen*. This is a
harness-selection + custom-scorer problem, not a "pick a benchmark" problem.

## What this benchmark has to measure

Unusual among agent benchmarks, which mostly score **final task success only**. We need
two axes:

1. **Task success** — did the job run, produce correct output, get retrieved? (standard)
2. **Behavioral / "good citizen" efficiency** — the differentiator, and exactly the
   guardrails in our `INSTRUCTIONS.md` template:
   - queue-spam rate (`sbatch`/`squeue`/`sacct` calls per minute),
   - wasted allocations / poorly-sized resource requests,
   - compute or data storage on login nodes,
   - thousands-of-small-files writes,
   - turns / tokens / wall-clock to a green result.

The design is inherently **A/B**: same agent harness + same model + same task, varying
**only** whether the instructions/skills are present. Per Anthropic's framing, we are
evaluating the *combined* system (harness + model + skill), so we must hold the agent
harness fixed and vary just the intervention, with:

- fresh, isolated environment per trial (no carryover),
- several trials per cell (model output is non-deterministic),
- `pass@k` for capability, and the stricter `pass^k` plus guardrail-violation counts for
  citizenship (a good citizen must behave on *every* run, not just once).

The behavioral metrics are custom oracles over the **transcript** (rate of scheduler
calls) plus **environment state** (`sacct` accounting, filesystem inode counts). That
requirement — scoring environment state and trajectory, not just final output — is what
should drive the framework choice.

## The landscape

### Candidate harnesses and benchmarks

| Framework | What it is | Stack | Ease of use | Fit for this project |
|---|---|---|---|---|
| **Inspect AI** (UK AISI) | General agentic eval framework: `Task → Solver → Scorer`, built-in ReAct agent, Docker/K8s sandboxes, tool loop, log viewer | Python (async), Docker, VS Code ext | Moderate–high; `pip install inspect-ai`, one command to run | **Best harness fit.** Custom `Scorer`s can score transcript + `sacct` state for our behavioral metrics; sandbox can be a Slurm-in-Docker image |
| **Terminal-Bench / Harbor** | Standard terminal-agent benchmark; 89 human-verified tasks incl. scientific computing & sysadmin; pluggable agent adapters incl. `claude-code` | Python, `uv`, Docker; optional Daytona cloud | High to run existing tasks; moderate to author custom | Strong if a priority is plugging in the **real Claude Code harness** and reusing its task/scoring conventions; we'd author Slurm tasks |
| **Anthropic skill-creator evals / "Evaluations"** | Purpose-built for **skill A/B**: executor + grader + blind comparator sub-agents, LLM-judge blind to which version is which | Claude Code / sub-agents | High | On-the-nose for the *"does the skill help"* question, but light on hosting a real Slurm environment — best for the **skill-quality half** |
| **METR Task Standard + Vivaria** | Portable Docker task-family spec + eval runner/UI | TS server + Postgres + Python hooks | Heavier setup | Portable task format is nice, but **METR is migrating to Inspect** — not worth starting here |
| **Braintrust / Langfuse / LangSmith / promptfoo** | Eval orchestration + trajectory/trace observability | SaaS or OSS, Python/TS | High | Not for hosting the cluster; useful as a **scoring/observability layer** — trajectory-level (step, tool-call) eval, which matters since final-output-only scoring over-reports by ~20–40% |

### HPC-specific prior art (small but real)

- **EngiAI** (IDETC 2026) includes an **HPC benchmark for end-to-end ML-training
  orchestration on a real SLURM cluster** — job submission, monitoring, result retrieval.
  Finding: success is strongly model-dependent and **degrades under natural-language (vs
  explicit) prompts** — essentially the effect our instructions are meant to counter.
  Built on LangGraph. <https://arxiv.org/abs/2605.19743>
- **TaskBound** ("Trusted Credentials, Untrusted Behavior", 2026) — a *proposed,
  not-yet-released* HPC-agent benchmark pairing each task with a policy + **deterministic
  security oracle** over Slurm actions and project-scoped filesystem policies. No code
  yet, but the **oracle-per-guardrail design is exactly the pattern** we want for the
  behavioral metrics. <https://arxiv.org/html/2607.18485v1>

### Mock-Slurm building blocks (environment layer — overlaps @dkn16's workstream)

Ready-made single-container Slurm stacks mean the "environment" can be a Docker image the
eval harness spins up per trial:

- `giovtorres/slurm-docker-cluster` — docker-compose multi-node, the de-facto reference.
  <https://github.com/giovtorres/slurm-docker-cluster>
- `misterfitz/slurm` — single-container Rocky 9 + Slurm 25.05, built for CI/testing.
- `minyang-chen/single-node-slurm-cluster-docker` — single-node **with GPU support**.
  <https://github.com/minyang-chen/single-node-slurm-cluster-docker>
- Autosubmit's single-container image, explicitly "for CI/CD testing of tools that
  interface with Slurm".

## Recommendation

A two-layer approach:

1. **Skill-quality layer** — use **Anthropic's skill-creator evals** (blind A/B
   comparator + LLM-judge) for fast iteration on whether each skill / `INSTRUCTIONS.md`
   variant helps. Cheap, no cluster needed, tight loop. Good for the first two hack days.

2. **Behavioral / end-to-end layer** — build the real benchmark on **Inspect AI**, with
   the sandbox = a **Slurm-in-Docker image** (coordinate with @dkn16 so the mock cluster
   *is* the Inspect sandbox). Write custom `Scorer`s that combine:
   - a **task oracle** (output correctness / job completion), and
   - **guardrail oracles** à la TaskBound (scheduler-call rate from the transcript,
     `sacct`-derived wasted allocation, inode deltas, login-node compute detection).

   Run each task as a matrix: {instructions on / off} × {N trials}; report `pass@k` for
   capability, and `pass^k` + guardrail-violation counts for citizenship.

**Why Inspect over Terminal-Bench as the base**: our value is in custom behavioral
scorers over environment state, which Inspect's `Scorer` model is built for, and it is
where the ecosystem (incl. METR) is consolidating. Use Terminal-Bench instead **only if**
a priority is benchmarking the *unmodified Claude Code harness* specifically — its
`claude-code` adapter gives that for free.

## Open decisions

- **Which agent harness are we benchmarking?** The real Claude Code CLI (realistic, but
  heavier to wire into Inspect) vs. Inspect's own ReAct agent (clean and controlled, but
  not the product). This affects everything downstream and should be decided before
  @dkn16 freezes the cluster image.
- **Where does the mock cluster live relative to the harness?** Ideally the Slurm-in-
  Docker image *is* the Inspect/Terminal-Bench sandbox, so one artifact serves both
  workstreams.
- **Task set**: start with 20–50 tasks drawn from real cluster failures rather than
  waiting for hundreds; large effect sizes early make small samples sufficient.

## Sources

- Anthropic — Demystifying evals for AI agents:
  <https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents>
- Inspect AI (practical guide, Hamel Husain): <https://hamel.dev/notes/llm/evals/inspect.html>
- Inspect AI review: <https://neurlcreators.substack.com/p/inspect-ai-evaluation-framework-review>
- Terminal-Bench docs: <https://www.tbench.ai/docs>
- Vivaria / METR Task Standard: <https://vivaria.metr.org/> ·
  comparison with Inspect: <https://vivaria.metr.org/comparison-with-inspect/>
- EngiAI: <https://arxiv.org/abs/2605.19743>
- TaskBound / HPC agent security: <https://arxiv.org/html/2607.18485v1>
- slurm-docker-cluster: <https://github.com/giovtorres/slurm-docker-cluster>
- single-node-slurm-cluster-docker: <https://github.com/minyang-chen/single-node-slurm-cluster-docker>
- Anthropic Skill Creator 2.0 evals: <https://www.thetoolnerd.com/p/anthropic-skill-creator-20-update>
- Agent eval platforms comparison: <https://latitude.so/blog/agent-first-comparison-guide-vs-braintrust>
