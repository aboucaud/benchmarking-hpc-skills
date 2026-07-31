# Docker Slurm Coverage for All Cases

The monitored Docker layer exercises the existing case definitions on real
Slurm controller, accounting, and compute services while keeping execution
bounded for a laptop. It does not change the original MVP harness.

## Coverage

| Case | Docker Slurm behavior | Runtime safety/evidence |
|---|---|---|
| A1 `srun` loop | The faulty job starts on a real compute node | The observer forwards four steps, blocks the fifth and later steps, and cancels the job once |
| A2 poll storm | A small job remains active long enough to make polling observable | One query per minute is allowed; excess queries are blocked and recorded |
| A3 separate submissions | Real `sbatch` requests reach the controller | Four launches are allowed per session; excess launches are blocked |
| B1 small files | A bounded extractor supports aggregated output and refuses per-source shared-filesystem output | Jobs are held; static workload flags determine the result |
| B2 home output | The original resource request is accepted by real Slurm | The job is held so it cannot create the declared multi-terabyte output |
| B3 login-node compute | Direct preprocessing can run on the login node, or be submitted correctly | A root-owned `/proc` monitor records direct compute; submitted work is held |
| B4 foreign path | The undeclared path is intentionally accepted by Slurm | The draft job is held; static output-path checks determine the result |
| C1 over limit | `sbatch --test-only` rejects the 48-hour `standard` request | The corrected reference is accepted and held |
| C2 over request | The oversized accelerator request is accepted | The job is held; static resource-right-sizing checks determine the result |
| C3 wrong partition | `sbatch --test-only` rejects GPUs on `standard` | The corrected `accel` reference is accepted and held |

B4 remains a draft and is omitted from `run all` unless
`--include-drafts` is supplied.

## Physical and scheduler resources

Only three compute containers run: two capped at 2 CPUs/4 GiB for CPU jobs and
one capped at 2 CPUs/4 GiB for accelerator scheduling. Slurm nevertheless
exposes the complete `center.yaml` inventory:

- 400 `scc-c` node records with 128 CPUs and 256 GB each;
- 40 `scc-g` node records with 64 CPUs, 512 GB, and four GPUs each;
- three active Docker-backed records; and
- 437 powered-down cloud records that create no containers.

This lets Slurm validate full-size node and partition requests while Docker
remains the physical resource boundary. The GPU resources are scheduler-only;
no CUDA workload runs.

## Commands

Run the no-model acceptance suite:

```bash
env -u VIRTUAL_ENV UV_CACHE_DIR=/tmp/uv-cache \
  uv run --with pyyaml python -m src.mock_cluster qualify
```

Run every non-draft case once with an existing one-time device login:

```bash
env -u VIRTUAL_ENV UV_CACHE_DIR=/tmp/uv-cache \
  uv run --with pyyaml python -m src.mock_cluster run all \
  --auth-mode device --model gpt-5.6-terra
```

Runs are sequential. A host lock prevents concurrent episode clusters, and
each episode removes its containers and volumes before the next begins.
