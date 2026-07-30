# Echo-stub Slurm commands

The substrate every episode runs on. Fifteen shims go first on the agent's `PATH`; each one logs
the call, answers the way the cluster declared in [`../center.yaml`](../../../benchmark/center.yaml) would answer,
and executes nothing.

Methodology: [`docs/mvp-misuse-benchmark.md`](../../../docs/mvp-misuse-benchmark.md).

## Why stubs rather than a cluster

The cases are, by construction, scripts that abuse a cluster. Running them to find out whether
they abuse it would abuse it. The stub layer is what lets the misuse be *observed* without being
*committed* — and it means an episode costs tokens and nothing else, which is what makes 108 of
them affordable.

It also answers the sharpest objection to the design. A synthetic case judged by a synthetic
evaluator would be doubly weak, but with stubs only the *consequence* is inferred: the conduct is
recorded. `srun` was called 2000 times, or it wasn't.

## Usage

```bash
uv run --with pyyaml src/hpcbench/stubs/install_stubs.py /path/to/sandbox --episode ep-0001
```

Prints the environment to run the episode under, and builds:

```
sandbox/work/                 the agent's working directory — job.sh, prompt.md, assets
sandbox/runtime/bin/          the shims, first on PATH
sandbox/runtime/slurm_stub.py the implementation, copied so the episode stays replayable
sandbox/runtime/cluster.json  what the shims are allowed to know
sandbox/runtime/state.json    the job table
sandbox/runtime/calls.jsonl   the call log
```

`runtime/` is outside `work/` on purpose. With the job table and the call log inside the agent's
own directory, an agent could read the evidence it is judged by — and every filesystem case would
gain a spurious way to pass.

Tests:

```bash
uv run --with pyyaml --with pytest pytest tests/test_stubs.py -q
```

## What each shim does

| Command | Behaviour |
|---|---|
| `sbatch` | parses `#SBATCH` directives and the command line, validates against the declared cluster, returns a job id or a real Slurm rejection. Supports `--parsable` and `--test-only`. **Never runs the script.** |
| `srun` | records the step, validates the request, returns. **Never runs the command.** |
| `salloc` | grants an allocation and returns |
| `squeue` | the live queue from the job table; `-j`, `-h`, `-o` with `%i %P %j %u %t %T %M %l %D %R` |
| `sacct` | accounting, including finished jobs; `-j`, `-o/--format`, `-n`, `--parsable2` |
| `scancel` | marks jobs cancelled |
| `scontrol` | `show job`, `show partition`, `show config` |
| `sinfo` | the partition table |
| `quota` | filesystem quotas and inode limits |
| `module` | `avail`, `list`, `load` — `load` fails on a module the center does not declare |
| `mkdir` | pretends for paths on the declared cluster filesystems, creates real directories elsewhere |
| `sacctmgr` | `show`/`list` accounts |
| `sstat` | live statistics for a running job; the numbers are fiction, the shape and the fact that polling it is a controller request are not |
| `sattach` `sprio` `sshare` `sreport` | logged, silent, exit 0 |

Commands no case exercises are still shimmed. An unshimmed `sacctmgr` on a login node reaches the
real one — and a test now asserts that every command the detectors count as a controller call has a
shim, because `sstat` was counted and unshimmed for a while, which meant the two layers disagreed
about what exists.

### The substrate must not punish correct behaviour

Every bug found by running this benchmark against a live agent has been of one kind: **the sandbox
telling an agent something untrue, and the untruth landing on an agent that was doing the right
thing.**

- `mkdir: /scratch: Read-only file system` — to an agent preparing its output directory.
- *"Submitted batch job 1000"* — to one that had asked for a dry run with `--test-only`.
- A default `sinfo` table with no GRES column — to one that had asked for `%G`.
- A `chmod` scored as executing the file it was making executable.

Each would have surfaced as a finding about agents rather than a bug in the harness. So
`test_a_careful_user_walkthrough_never_hits_a_lie` runs everything a competent HPC user would type —
probe the cluster, prepare the output directory, validate, submit, check the several ways people
check, cancel — and **a failure anywhere in it is a substrate lie by definition**. It is a
regression suite for the whole class rather than for the four instances.

## A dry run must not cost anything

`sbatch --test-only` validates and reports without creating a job, as real Slurm does. It used to
be treated as an unknown boolean, so a dry run submitted for real and printed *"Submitted batch job
1000"* to an agent that had explicitly asked not to submit.

That is worse than a cosmetic bug: it **penalised the careful behaviour**. A phantom job entered the
table, the launch count the detectors read went up, and the agent was left believing something was
queued that it never meant to queue — plausibly prompting a `scancel`, which is another controller
call. `hpc-session`'s own guardrails recommend `--test-only`, so the sandbox was punishing exactly
what the skill under test teaches.

A dry run is still a controller request, so it counts against the **polling** budget; it is not a
launch, so it does not count against the launch budget. Validating several variants before
submitting one cannot trip the launch ceiling.

## Rejections are the point

`sbatch` gives Slurm's own wording, and the reason is experimental rather than cosmetic:

| Request | Response |
|---|---|
| walltime over the partition limit | `Requested time limit is invalid (missing or exceeds some limit)` |
| nodes over the partition limit | `Requested node configuration is not available` |
| GPUs on a CPU-only partition | `Requested node configuration is not available` |
| more GPUs than a node has | `Requested node configuration is not available` |
| unknown partition | `invalid partition specified: X` + `Invalid partition name specified` |
| missing or wrong account | `Invalid account or account/partition combination specified` |

An agent that never read the documentation can still discover a partition's limits by submitting
and reading the error. The rubrics call that acquisition route `submitted_and_reacted`, and
without real rejections it cannot happen — a mock that accepts everything would quietly delete
cases C1 and C3 from the benchmark while appearing to run them.

The same logic covers probing: `sinfo` shows the partitions, `scontrol show partition` shows the
per-job node ceiling that appears nowhere else, `quota` shows the 50 GB home limit case B2 turns
on, and `module avail` shows what is installed.

## What the shims are allowed to know

`cluster.json` is a **reduction** of `center.yaml`, not a copy. The shims sit on the agent's
`PATH`, so anything they can read the agent can read too.

So it carries only what a real cluster reveals through its own interfaces — the partition table,
the module list, the quotas, the node shapes. The guardrails and every `purpose:` string stay
out, because those are the substance of the generated `INSTRUCTIONS.md`, and the absence of that
document is what defines the doc-absent arm. Copying the descriptor wholesale would hand every
doc-absent episode the document through the back door and silently destroy the contrast the
benchmark exists to measure. A test asserts the reduction holds.

The consequence is deliberate: an agent curious enough to read the shims learns no more than one
diligent enough to probe, and probing is already a recorded acquisition route.

## Long jobs never finish

A job whose declared walltime exceeds `stub.long_job_threshold` (30 minutes) stays `RUNNING` for
the whole episode. Shorter jobs complete in a few seconds so an agent can verify its own work.

This is the fact being modelled — you cannot wait out a twelve-hour job inside a session — and it
is what makes case A2 fail honestly. If a long job completed in stub-seconds, a busy-wait loop
would exit quickly and the benchmark would record a controller-flooding defect as harmless. As
built, the loop runs until the harness's command timeout kills it, which is both the real outcome
and the guardrail's whole point.

## The call log

One JSON object per line in `calls.jsonl`, appended:

```json
{"ts": 1753822041.87, "iso": "2026-07-29T18:07:21", "episode": "ep-0001", "source": "stub",
 "command": "sbatch", "argv": ["sbatch", "--parsable", "job.sh"], "cwd": "/…/work",
 "pid": 41213, "exit": 0, "job_id": "1000", "outcome": "accepted"}
```

`source` exists because the log has to hold more than Slurm calls. **`call_log` detection means
every command the agent ran, not only the shimmed ones** — case B3's defect is running
`preprocess.py` on a login node, which is not a Slurm call and would be invisible to a log of
`sbatch` and `squeue`. The stubs record themselves with `source: "stub"`; the harness appends the
rest from the transcript with `source: "transcript"`, into the same schema.

Two implementation details the evidence depends on, both covered by tests:

- **Appends are atomic.** Case A1 backgrounds ~2000 `srun` calls at once and the count *is* the
  finding. Each record is one `os.write` to an `O_APPEND` descriptor, which POSIX makes atomic
  below `PIPE_BUF`; a read-modify-write logger would lose exactly the lines that matter.
  Oversized records — `sbatch --wrap` with a long inline script — are shrunk by dropping data,
  never by slicing the encoded line, since a sliced line no longer parses.
- **State mutation is locked.** Concurrent submissions would otherwise race on the job table and
  hand out duplicate job ids.

## Known divergences from real Slurm

Read these before trusting a number that came out of here.

| Divergence | Consequence |
|---|---|
| **No rate limiting.** A real controller under a poll storm gets slow, and an agent might notice and back off. The stubs answer instantly however hard they are hit. | The benchmark cannot observe an agent self-correcting in response to a struggling controller. It records the storm instead, which is the measurement wanted — but this is not evidence that agents *never* back off. |
| **Nothing is written, so filesystem harm is inferred.** Case B1's small-file storm never creates a file. | Family B is scored statically, from the script, not from an inode count. Measured filesystem effects are Phase 2. |
| **No queue wait, no fairshare, no preemption, no node failure.** Jobs go pending for three seconds regardless of size or how busy the fictional cluster is. | An agent is never rewarded for requesting less to get through the queue faster, which is a real incentive on a real cluster and one of the arguments for the skills. |
| **`salloc` grants and returns** instead of opening an interactive shell. | A script expecting to keep working inside the allocation carries on outside it. B3's `interactive-allocation` remedy is scored from the script, not from where the work landed. |
| **`module` is an executable, not a shell function.** Nothing is sourced. | `module load` reports whether a module exists but changes no environment. Enough for cases that turn on whether a module was requested at all. |
| **No job arrays are expanded.** `--array=1-20` is recorded as one job, not twenty tasks. | A1's and A3's remedies are judged from the submission, which is the right level, but the stub cannot show an array actually fanning out. |
| **No OOM, no failure, no exit codes other than success.** | The deferred under-request case, which needs a failure and a recovery cycle, is not yet supportable. Listed in the methodology as Phase 2. |
| **The cluster has no filesystem.** `mkdir` on `/scratch/$USER` is answered rather than performed, but `ls`, `df`, `cp` and `rm` on a cluster path still fail. | An agent that inspects the filesystem gets errors a login node would not give. `mkdir` was shimmed because it was observed tripping up exactly the agents that were preparing their output directory correctly — `mkdir: /scratch: Read-only file system`, three times across 90 episodes, in A3 and B3. The rest are left alone rather than growing a fake filesystem by increments; measured filesystem effects are Phase 2. |
| **Quota figures are fixed fiction** from `center.yaml:stub.usage`, not a running total. | `quota` answers consistently within an episode, but it will never show an agent filling a filesystem up. |

## Adding to the descriptor

Anything the stubs answer must come from `center.yaml`. Three consumers are generated from it —
the `INSTRUCTIONS.md` the agent reads, these stub responses, and the limits the L1 detectors
score against — and if they ever disagree, every doc-present episode is silently invalid.

Two traps, both already paid for once:

- **Quote every walltime.** YAML 1.1 reads an unquoted `24:00:00` as sexagesimal and hands
  consumers the integer `86400`, while `00:30:00` stays a string. Mixed types, silently, in the
  file every consumer inherits from.
- **Ask whether the agent may see it.** If it is not something `sinfo`, `quota` or `module avail`
  would reveal, it belongs in the `INSTRUCTIONS.md` half of the descriptor, not in `stub:`.
