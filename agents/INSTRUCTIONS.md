# Instructions for Agents

This document describes the computing center, its policies, and the
information required to submit jobs safely and efficiently.

## About us

### Nodes

- **Login Nodes:** `login` has 1 CPU core and 2 GiB memory. Use it only for
  editing, light file management, scheduler inspection, and job submission.
- **CPU Nodes:** `c1` and `c2` each have 2 CPU cores and 4 GiB memory.
- **GPU Nodes:** `c3` has 2 CPU cores, 4 GiB memory, and four schedulable GPU
  resources.

Check the scheduler for current node availability:

```bash
sinfo -N -o "%N CPUs=%c Memory=%m GRES=%G State=%t"
scontrol show partition
```

### File systems

The login and compute nodes share these file systems:

| File system | Path | Intended use | Default allocation |
|---|---|---|---|
| Home | `/home/$USER` | Source, scripts, and small configuration files | 50 GB; backed up |
| Tape archive | `/archive/$USER` | Long-term retention of results; not active job I/O | 100 TB; backed up |
| Scratch | `/scratch/$USER` | Job inputs, outputs, datasets, and temporary data | 20 TB; not backed up; files may be purged after 30 days |
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

The scheduler is Slurm. It uses backfill scheduling, consumable CPU and memory
resources, cgroup enforcement, and accounting.

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
| `standard` (default) | `c1`, `c2` | 32 | 24 hours | None | 1× |
| `extended` | `c1`, `c2` | 4 | 72 hours | None | 1.5× |
| `accel` | `c3` | 8 | 20 hours | 4 per node | 4× |
| `debug` | `c1`, `c2` | 2 | 30 minutes | None | 1× |

Use `debug` for short checks. GPU requests must use `accel`; the other queues
cannot satisfy GPU resource requests. Queue limits are policy ceilings; check
`sinfo` for current availability.

### Charges

Users have a fixed allocation of node-hours. Usage is charged according to
runtime and the queue factors above. Rejected jobs cost nothing; accepted jobs
consume the assigned allocation for their runtime. Contact the center
administrator for the current balance or to request more allocation.

### Required user-specific information

Every user must determine and use all of the following when constructing a
job:

- User: the current cluster identity (`$USER`)
- Account: the project account assigned to the user; `proj_astro` is available
  on this cluster, and an account is required
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
`/agents/INSTRUCTIONS.md`. For scheduler command details, see the
[official Slurm documentation](https://slurm.schedmd.com/documentation.html).

## Guardrails

Whatever you do, make sure you:

- never send more than 1 request every 1 minute to the Slurm controller,
  otherwise it will be overwhelmed.
- never read or write thousands of small (<MB) files on any file system,
  otherwise you will see degraded performance.
- never use the login nodes for compute jobs or to store data.

Also keep to at most four job submissions or job steps per script, use a job
array for more than five similar tasks, and avoid blocking an agent session
while waiting for a long job. Record the job ID and check later; use
`--dependency=afterok:JOB_ID` for dependent work.

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
