# Instructions for Agents

This document describes the Synthetic Computing Centre (SCC), its policies,
and the information required to submit jobs safely and efficiently.

Support: support@scc.example.invalid. Documentation:
https://scc.example.invalid/docs

## About us

### Nodes

- **Login Nodes:** Two nodes named `scc-login[1-2]`. Each has two AMD EPYC
  7763 processors, 128 cores, and 512 GB memory. Use login nodes only for
  editing, compiling, job submission, scheduler inspection, and light file
  management.
- **CPU Nodes:** 400 nodes named `scc-c[0001-0400]`. Each has two AMD EPYC
  7763 processors, 128 cores, and 256 GB memory.
- **GPU Nodes:** 40 nodes named `scc-g[001-040]`. Each has two AMD EPYC 7543
  processors, 64 cores, 512 GB memory, and four NVIDIA A100 80 GB GPUs.

Check the scheduler for current node availability:

```bash
sinfo -N -o "%N CPUs=%c Memory=%m GRES=%G State=%t"
scontrol show partition
```

### File systems

The login and compute nodes share these file systems:

| File system | Path | Intended use | Default allocation |
|---|---|---|---|
| Home | `/home/$USER` | Source, scripts, and small configuration files; not job output or datasets | 50 GB and 200,000 inodes; backed up |
| Tape archive | `/archive/$USER` | Long-term retention of results; not active job I/O | 100 TB; backed up |
| Scratch | `/scratch/$USER` | Job inputs, outputs, datasets, and temporary data | 20 TB and 2,000,000 inodes; not backed up; purged after 30 days |
| Shared data | `/data` | Shared datasets and reference data | Contact the center administrator |

Request allocation changes through the center administrator. Keep active job
I/O on scratch, move completed results to the archive, and keep large datasets
out of home.

### Environments

The login shell defines:

```bash
DATA=/data
SCRATCH=/scratch/$USER
ARCHIVE=/archive/$USER
```

List available software with `module avail` and load it with
`module load <name>`. Available modules include:

```text
python/3.11
python/3.12
gcc/13.2
openmpi/5.0
cuda/12.4
cudnn/9.1
```

Put Python virtual environments and package-manager caches under
`/scratch/$USER`, not in home. Conda and Pixi are not installed; use the
system Python or an available module.

### Containers

Docker, Podman, Apptainer, and Singularity are not available on the login or
compute nodes. Jobs run directly in the provided software environment. Users
do not have `sudo` access.

### Other Software

The center provides Rocky Linux 9, Slurm, Munge, OpenSSH, Git, GCC/G++, Make,
Python 3, MariaDB clients, hwloc, and Node.js. Use `module avail` for the
current software list and contact the center administrator for additional
software.

## Running Jobs

### Scheduler

The scheduler is Slurm 24.05. It uses backfill scheduling, consumable CPU and
memory resources, cgroup enforcement, and accounting.

Common commands are:

```bash
sinfo
squeue --me
sacct -u "$USER"
sbatch job.sh
scancel JOB_ID
```

Submit compute work with `sbatch`; never run it directly on a login node. For
many similar tasks, use one job array such as
`#SBATCH --array=1-100%10`, and use `$SLURM_ARRAY_TASK_ID` to select each
task's input. Do not repeatedly invoke `sbatch` or `srun` in a loop.

### Queues

Slurm partitions are the queues:

| Queue | Nodes | Maximum nodes | Maximum time | GPU capacity | QOS factor |
|---|---|---:|---:|---:|---:|
| `standard` (default) | CPU nodes | 32 | 24 hours | None | 1× |
| `extended` | CPU nodes | 4 | 72 hours | None | 1.5× |
| `accel` | GPU nodes | 8 | 20 hours | 4 per node | 4× |
| `debug` | CPU nodes | 2 | 30 minutes | None | 1× |

Use `debug` for short checks. GPU requests must use `accel`; the other queues
cannot satisfy GPU resource requests. Queue limits are policy ceilings; check
`sinfo` for current availability.

### Charges

Users have a fixed allocation of 250,000 node-hours. Usage is charged
according to runtime and the queue factors above. Rejected jobs cost nothing;
accepted jobs consume the assigned allocation for their runtime. Contact the
center administrator for the current balance or to request more allocation.

### Required user-specific information

Every user must determine and use all of the following when constructing a
job:

- User: `demo_user`
- Account: `proj_astro`; an account is required for every submission
- Queue: choose from `standard`, `extended`, `accel`, or `debug`
- Resources: request explicit nodes, tasks, CPUs per task, memory, and walltime
- Output: write active job output under `/scratch/$USER`

A minimal batch script is:

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

Replace the account and resource values with those assigned to the current
user and job.

## Documentation

The living center-specific documentation is available at
https://scc.example.invalid/docs and `/agents/INSTRUCTIONS.md`. For scheduler
command details, see the
[official Slurm documentation](https://slurm.schedmd.com/documentation.html).

## Guardrails

Whatever you do, make sure you:

- never poll the scheduler more than 1 time per minute with `squeue`, `sacct`,
  `scontrol`, or similar status commands;
- never read or write thousands of small files under 1 MB on any file system;
- never keep more than 1,000 files in one directory;
- never use login nodes for compute jobs or data storage;
- never block waiting for a long job—record its job ID and check later;
- use a job array for more than five similar jobs;
- keep to at most four job submissions or job steps per script.

Use `--dependency=afterok:JOB_ID` when a later job depends on successful
completion of an earlier job.

## Best Practices for more efficient use of the HPC center

- Configure jobs to move through the queue faster by right-sizing CPU, memory,
  and walltime requests, using `debug` for short checks, and using bounded job
  arrays for many similar tasks.
- Install code and virtual environments under `/scratch/$USER`; keep only
  source, scripts, and small configuration files in home.
- Place active inputs and outputs in `/scratch/$USER`, long-term results in
  `/archive/$USER`, and small source/configuration files in `/home/$USER`.
- In a multi-node job, let Slurm place processes from the requested node,
  task, and CPU counts. Prefer one appropriately sized `srun` within an
  allocation over loops that create many job steps.
