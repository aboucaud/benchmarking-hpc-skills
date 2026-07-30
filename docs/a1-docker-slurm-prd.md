# PRD: Docker Slurm Benchmark and A1 `srun`-Loop Test

**Status:** Draft

**Implementation base:** `lfnothias/episode-harness`

**Overview reference:** `aboucaud/prd`

## Outcome

Run benchmark agents inside a disposable Docker Slurm login node and
cross-validate the A1 `srun`-loop case against a real Slurm controller.

The operator or harness SSHes to `login` as `demo_user` and starts Codex there:

- manual: interactive `codex`;
- automated: headless `codex exec --json`.

A root-only observer records scheduler misuse and stops A1 before more than
four `srun` attempts reach `slurmctld`. Docker runtime evidence supplements,
but does not replace, the existing static detector, agent command log, and L2
judge.

## Goals

- Make the mock cluster compatible with all nine current benchmark cases.
- Keep one login node at 1 CPU/2 GB and two CPU nodes at 2 CPUs/4 GB each.
- Use cheap deterministic stand-ins instead of production-scale workloads.
- Run Codex inside the login node, using real local Slurm clients.
- Preserve the existing documentation/skills 2×2 experiment.
- Qualify A1's bad and reference fixtures before running a model.
- Prevent the synthetic misuse test from becoming real controller load.

## Non-goals

- Measuring production Slurm performance or failure thresholds.
- Running 2-TB, 500,000-file, CUDA, MPI-scale, or multi-hour workloads.
- Building a production rate limiter or adversarial security sandbox.
- Treating observer cancellation as an agent repair.
- Replacing echo-stub episodes for the full large-N study.

## Phase 0: align the cluster with every case

This is the first implementation milestone. Do not build the A1 observer on
the current hand-written Docker scheduler configuration.

[`benchmark/center.yaml`](../benchmark/center.yaml) is the source of truth for
documentation, stubs, and detectors. Docker must also consume its generated
configuration:

- [`benchmark/generated/mock-cluster.conf`](../benchmark/generated/mock-cluster.conf)
- [`benchmark/generated/mock-cluster-gres.conf`](../benchmark/generated/mock-cluster-gres.conf)

The first change set must:

1. replace `short`/`regular`/`long` with `standard`, `extended`, `accel`, and
   `debug`;
2. provision `demo_user` (UID 5001) and account `proj_astro`;
3. preserve the descriptor's default partition, time limits, node ceilings,
   and GPU capability;
4. provide `/home`, `/scratch`, `/archive`, Python, and module compatibility;
5. set `MaxArraySize >= 2001`;
6. resolve the descriptor/Docker Slurm-version mismatch;
7. make `render.py check` and `render.py drift` required preflights.

### Topology

| Service | Role | Physical limit |
|---|---|---:|
| `login` | SSH, Codex, Slurm clients | 1 CPU, 2 GB |
| `c1`, `c2` | CPU compute | 2 CPUs, 4 GB each |
| `c3` | benchmark-only fake accelerator | 2 CPUs, 4 GB |
| `slurmctld`, `slurmdbd` | scheduler/accounting | small fixed limits |
| `observer` | root-only safety/evidence | small fixed limit |

`c3` is enabled for C2/C3 and advertises four GPUs without a physical GPU.
It must be distinct from `standard`; otherwise C3's bad GPU request could
succeed on the CPU partition.

Slurm may advertise production-shaped CPUs and GPUs while Docker enforces the
small physical limits. These are scheduler-behavior tests, not performance
tests. Prefer advertised resources over rewriting case inputs.

B2's node count is normalized from eight to two because its benchmark defect is
the output filesystem, not topology selection. The same two-node fixture is
used by stubs and Docker, so no hidden per-episode adapter is needed. A1
requires no resource normalization.

### Cheap workload contract

Support programs must parse the real arguments and optionally write one small
result manifest, but never perform the nominal work. Per submitted fixture:

- maximum 10 seconds;
- maximum one sustained physical CPU;
- maximum 256 MB resident memory;
- maximum 1 MB new data and ten new files;
- no real CUDA or large MPI execution.

| Case | Required Docker behavior |
|---|---|
| A1 | Accept CPU job/2,000-task array; stop bad loop at attempt five |
| A2 | Keep fit alive briefly to expose rapid polling; summary is a no-op |
| A3 | Accept array syntax; stop repeated submissions after detection |
| B1 | Write one manifest, never 500,000 files |
| B2 | Record output root, never write snapshots |
| B3 | Record direct login execution, never use 64 cores/200 GB |
| C1 | Reject 48 h on `standard`; accept it on `extended` |
| C2 | Accept fake-GPU requests on `accel`; run no CUDA |
| C3 | Reject GPU request on `standard`; accept it on `accel` |

Before model runs, every unchanged and reference fixture must be exercised.
Each must be accepted or rejected for its declared reason, stay inside the
cheap-workload budget, leave the controller healthy, and clean up fully.
Unsupported cases must be explicit; they cannot silently fall back to stubs.

## Codex runs inside `login`

The login image contains a pinned Codex CLI. Codex runs as `demo_user` with:

- `gpt-5.6-terra` as the default benchmark model, recorded per episode;
- `/episode/work` containing only condition-visible files;
- an ephemeral home and `CODEX_HOME`;
- real local Slurm commands;
- selected documentation and skills only;
- no Docker socket, host home, withheld files, observer data, or SSH key.

The Codex process counts against the login node's 1-CPU/2-GB limit. Scientific
work must still be submitted to compute nodes.

### Manual workflow

The preparation command creates a fresh cluster and prints its SSH endpoint:

```bash
uv run --with pyyaml src/hpcbench/harness/episode.py A1-srun-loop \
  --substrate docker-slurm --runner prepare --keep

ssh -i <episode-key> -p <episode-port> demo_user@localhost
codex -C /episode/work
```

After Codex exits, the host collector retrieves artifacts, cancels jobs, and
removes the Compose project:

```bash
mock-cluster/bin/collect-agent-run <episode-id>
```

Interactive runs are exploratory unless their complete transcript is captured.

### Automated workflow

Add a `CodexExecRunner` and a separate `DockerSlurmSubstrate`. The desired CLI
is:

```bash
uv run --with pyyaml src/hpcbench/harness/episode.py A1-srun-loop \
  --substrate docker-slurm --runner codex-exec \
  --matrix --seeds 5 --skills /path/to/skill-bundle
```

For each episode the harness:

1. starts and preflights a fresh cluster;
2. materializes the condition on `login`;
3. SSHes to `login` as `demo_user`;
4. starts `codex exec` there and sends `prompt.md` over stdin;
5. streams JSONL events back to the harness;
6. collects final files and Slurm/observer evidence;
7. scores, health-checks, and tears down the cluster.

The remote command is equivalent to:

```bash
codex exec --model "${CODEX_MODEL:-gpt-5.6-terra}" \
  --json --ephemeral --ignore-user-config --ignore-rules \
  --skip-git-repo-check \
  --cd /episode/work -
```

Prefer the `workspace-write` sandbox. If it blocks internal Slurm traffic, a
less restrictive Codex sandbox is allowed only inside the disposable,
externally constrained login container.

Do not expose a long-lived API credential to agent commands. Use a
credential-isolating API proxy or equivalent. Login egress is limited to the
model API path and required internal Slurm services.

## Root observer and A1 circuit breaker

The observer runs as root in a dedicated service and writes an agent-invisible
volume. It does not mount the Docker socket.

It observes:

- login-node Slurm clients for agent conduct and A2/A3 containment;
- compute-node `srun` for A1 job-step containment.

For each A1 job:

1. attempts one through four may reach real `srun`;
2. attempt five is recorded and blocked before `slurmctld`;
3. the observer issues exactly one `scancel`;
4. later attempts are rejected locally;
5. cancellation and terminal state are recorded.

Events include episode ID, timestamps, UID, job ID, PID/parent PID, redacted
arguments, and `forwarded`/`blocked`/`error` disposition. Reports distinguish
attempted launches from forwarded controller requests.

The real `srun` is isolated behind the proxy. Preflight verifies interception
through `srun`, `command -v srun`, `/usr/bin/srun`, and batch-job children.
Failure invalidates the episode.

Slurm corroboration consists of:

- controller logs with `DebugFlags=Steps`;
- one pre-episode `sdiag --reset` and one post-episode snapshot;
- one post-episode `sacct` capture.

`MaxStepCount`, PID limits, and a host timeout are defense in depth, not the
primary breaker.

## A1 fixture expectations

### Unchanged floor

- `sbatch` accepts and starts the job.
- The fifth `srun` attempt trips the breaker.
- At most four launches are forwarded.
- One cancellation is issued.
- Static/runtime detection fails A1.
- The controller remains healthy.

### Reference ceiling

- Slurm accepts the complete 2,000-task array with its concurrency cap.
- No launch-loop breaker trips.
- Static detection recognizes the remedy.
- Workload submission is recorded.
- The harness cancels the array after acceptance evidence; it does not wait for
  2,000 tasks to finish.

The primary endpoint remains: recognized safe repair, workload submitted, and
L1/L2 agreement. Observer evidence is a separate `source: observer` stream and
must not be double-counted with transcript evidence.

## Required artifacts

Each episode records:

- Codex JSONL transcript and recovered commands;
- initial/final workspace hashes and submitted scripts;
- image digests, Slurm/config hashes, version, and adapter provenance;
- observer JSONL and controller-log slice;
- `sdiag` delta and `sacct` records;
- attempted/forwarded/blocked counts and breaker latency;
- final job state, controller health, resource-budget result, and cleanup result.

## Implementation order

1. Adopt generated Slurm/GRES configuration.
2. Align identity, filesystems, modules, version, and array limit.
3. Add `c3` and cheap support workloads.
4. Qualify all nine scripted floors and ceilings.
5. Implement and stress-test the generalized observer/proxies.
6. Qualify A1 floor and ceiling under containment.
7. Add login-node Codex installation and headless SSH runner.
8. Run stub/Docker parity and one four-condition model smoke test.
9. Obtain Slurm-administrator review.
10. Run A1's four conditions with at least five seeds each.

## Acceptance criteria

- Generated configuration has no benchmark-invariant drift.
- All nine case fixtures pass qualification and the cheap-workload budget.
- Login and compute containers enforce their physical limits.
- Codex runs inside `login` manually and through headless SSH automation.
- Headless runs preserve structured command evidence and expose no long-lived
  credential, Docker API, host filesystem, or observer data.
- A1 floor trips exactly on attempt five and forwards at most four launches.
- A1 ceiling submits all 2,000 logical tasks without tripping the breaker.
- No workload is reduced and no repair is manufactured by the harness.
- Every episode cleans jobs, keys, state, volumes, and services.
- Existing harness tests remain green.
- No Docker result is treated as evidence before administrator sign-off.

## Deliverables

- generated configuration integration in `mock-cluster/`;
- benchmark `c3` service and fake GRES;
- cheap workload fixtures for all cases;
- root observer, client proxies, and event schema;
- `DockerSlurmSubstrate` and `CodexExecRunner`;
- Docker integration/qualification tests;
- prepare/collect helpers and mock-cluster README instructions;
- episode schema and detector support for runtime evidence.

## Open decisions

- Implement the observer/proxy in a small compiled binary or Python.
- Extend the base Compose file or use a fully resolved benchmark overlay.
- Provide localhost configuration for skills that assume a remote
  `hpc-session`; A1 itself uses local Slurm clients.

## References

- [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive/)
- [`srun`](https://slurm.schedmd.com/srun.html)
- [Slurm job launch](https://slurm.schedmd.com/job_launch.html)
- [`sdiag`](https://slurm.schedmd.com/sdiag.html)
- [`slurm.conf`](https://slurm.schedmd.com/slurm.conf.html)
