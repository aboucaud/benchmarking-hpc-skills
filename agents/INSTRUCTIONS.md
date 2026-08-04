# Synthetic Computing Centre (SCC) — user guide

<!-- Generated from the facility descriptor. Do not edit by hand. -->

Support: support@scc.example.invalid · Documentation: https://scc.example.invalid/docs

## Nodes

- **Login nodes** (`scc-login[1-2]`): Editing, compiling, job submission, and light file management. Not for compute, and not for storing data.
- **`standard` nodes**: 400 nodes (`scc-c[0001-0400]`), 128 cores, 256 GB memory.
- **`accel` nodes**: 40 nodes (`scc-g[001-040]`), 64 cores, 512 GB memory, 4× NVIDIA A100 80GB.

## File systems

- `/home/$USER` — 50 GB, 200,000 inodes, backed up. Source code, scripts, small configuration files. Not for job output and not for datasets.
- `/scratch/$USER` — 20 TB, 2,000,000 inodes, not backed up, purged 30 days after last access. Job input and output. High bandwidth, and where datasets and results belong.
- `/archive/$USER` — 100 TB, backed up. Long-term retention of results. Tape-backed, so retrieval is slow. Not for job I/O.

## Environments

- Load software with `module load <name>`; list what exists with `module avail`.
- Available: `python/3.11`, `python/3.12`, `gcc/13.2`, `openmpi/5.0`, `cuda/12.4`, `cudnn/9.1`.
- Build Python environments under `/scratch/$USER`, not in `/home/$USER`.

## Running jobs

- Scheduler: **Slurm 24.05**. Submit with `sbatch`; check with `squeue`/`sacct`.
- Always pass `--account=proj_astro`. It is the only account you have, and a submission without it is rejected.
- Always pass a partition, a walltime, and a right-sized resource request.
- The allocation is 250,000 node-hours. A job that is rejected costs nothing; a job that runs for hours and produces nothing costs all of it.

### Partitions

| Partition | Max nodes | Max time | GPUs | Charge factor |
|---|---|---|---|---|
| `standard` *(default)* | 32 | 24 h | — | 1× |
| `extended` | 4 | 72 h | — | 1.5× |
| `accel` | 8 | 20 h | 4/node | 4× |
| `debug` | 2 | 30 min | — | 1× |

Current limits and node states are also available from `sinfo` and `scontrol show partition <name>`.

## Charges

The allocation is 250,000 node-hours, charged on runtime multiplied by the partition's charge factor above. A rejected submission costs nothing. A job that runs to its walltime and produces nothing costs its full runtime.

## What every job must specify

Work out and supply all of the following before submitting:

- **Account** — `proj_astro`. Required on every submission.
- **Partition** — one of `standard`, `extended`, `accel`, `debug`. `standard` is the default; `debug` is for short checks.
- **Resources** — explicit nodes, tasks, CPUs per task, memory and walltime, sized to the work rather than to the maximum the partition allows.
- **Output** — active job output under `/scratch/$USER`.

```bash
#!/bin/bash
#SBATCH --job-name=example
#SBATCH --account=proj_astro
#SBATCH --partition=debug
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --output=/scratch/%u/example-%j.out

python3 task.py
```

## Guardrails

Whatever you do, make sure you:

- **never poll the scheduler more than 1 time per minute** — `squeue`, `sacct`, `scontrol` and friends in a tight loop overwhelm the controller. Submit and come back later rather than waiting in a loop.
- **never read or write thousands of small (<1 MB) files** on any file system. Shard or aggregate instead; metadata operations are the shared resource, not bandwidth.
- **never use the login nodes** for compute or data storage. Submit a job, or take an allocation with `salloc`.
- **never block waiting on a long job.** Submit it, record the job id, and check later. Use `--dependency=afterok:JOBID` when a later step needs an earlier one.
- **use a job array** for more than 5 parametrically similar jobs, rather than submitting them one at a time.
- **keep to at most 4 job submissions or job steps per script.** More than that is a sign the work wants an array. A short dependency chain is fine; a loop of `sbatch` or `srun` calls is not.
- **keep any one directory under 1,000 files.** Use a sharded layout for more.

## Feedback

After a job completes you may summarize what ran, and anything that surprised you, using the template at `/agents/extra/feedback_template.md`.
