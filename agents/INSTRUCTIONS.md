# Instructions for Agents

This is a local Docker Slurm cluster for testing and benchmark episodes. It
models the scheduler interface and policies of a larger HPC system, but it is
not a production cluster and must not be used for performance measurements.

## About us

### Nodes

- **Login Nodes:** `login` has a Docker limit of 1 CPU and 2 GiB memory. Use it
  only for editing, light file management, scheduler inspection, and job
  submission. The default local test identity is `demo_user`, but all guidance
  in this document applies to the current logged-in user. In benchmark
  episodes, the working directory is `/episode/work`.
- **CPU Nodes:** `c1` and `c2` each have a Docker limit of 2 CPUs and 4 GiB
  memory. Slurm advertises 128 CPUs and 3,800 MiB schedulable memory per node so
  synthetic benchmark requests can be validated on a laptop.
- **GPU Nodes:** `c3` has a Docker limit of 2 CPUs and 4 GiB memory. Slurm
  advertises 64 CPUs, 3,800 MiB schedulable memory, and four GPU GRES. These
  GPUs are scheduler-only stand-ins; there is no physical GPU or CUDA execution
  environment.

Inspect the scheduler's resource view with:

```bash
sinfo -N -o "%N CPUs=%c Memory=%m GRES=%G State=%t"
scontrol show partition
```

For deployment details, see the
[mock-cluster documentation](../src/mock_cluster/README.md).

### File systems

The login and compute nodes share disposable Docker volumes:

| File system | Path | Intended use | Modeled allocation |
|---|---|---|---|
| Home | `/home/$USER` | Source, scripts, and small configuration files | 50 GB; backed up |
| Tape archive | `/archive/$USER` | Long-term results; never active job I/O | 100 TB; backed up |
| Scratch | `/scratch/$USER` | Job inputs, outputs, datasets, and temporary data | 20 TB; not backed up; 30-day purge policy |
| Shared data | `/data` | General shared test data | No enforced quota |
| Episode workspace | `/episode/work` | Files materialized for the current benchmark episode | Disposable |

Docker does not enforce the modeled quotas, backups, or purge timers. Fresh
episodes remove their ordinary cluster volumes, so retained output must be
collected by the host-side runner.

### Environments

The login shell defines:

```bash
DATA=/data
SCRATCH=/scratch/$USER
ARCHIVE=/archive/$USER
EPISODE_WORK=/episode/work
```

Use `module avail` to list modeled software and `module load <name>` to select
it. Advertised modules are:

```text
python/3.11
python/3.12
gcc/13.2
openmpi/5.0
cuda/12.4
cudnn/9.1
```

These module entries validate cluster-facing scripts but do not install
alternate toolchains. Put Python virtual environments and package-manager
caches under `/scratch/$USER`, not in home. Conda and Pixi are not installed;
use the system Python or software already provided by the container.

### Containers

Docker, Podman, Apptainer, and Singularity are not available inside the login
or compute nodes. Jobs run directly in disposable Rocky Linux containers. The
agent user has no `sudo` access and cannot access the host Docker socket.

### Other Software

The cluster includes Rocky Linux 9, Slurm, Munge, OpenSSH, Git, GCC/G++, Make,
Python 3, MariaDB clients, hwloc, Node.js, and Codex. Codex runs headlessly as
the logged-in user on the login node; it is not installed on compute nodes.

For runner, authentication, and qualification commands, see the
[mock-cluster documentation](../src/mock_cluster/README.md).

## Running Jobs

### Scheduler

The scheduler is Slurm. It uses backfill scheduling, consumable CPU and memory
resources, cgroup enforcement, and MariaDB-backed accounting.

Common commands are:

```bash
sinfo
squeue --me
sacct -u "$USER"
sbatch job.sh
scancel JOB_ID
```

Submit compute through `sbatch`, not on the login node. For many similar tasks,
use one job array such as `#SBATCH --array=1-100%10`; use
`$SLURM_ARRAY_TASK_ID` to select each task's input. Do not repeatedly invoke
`sbatch` or `srun` in a loop.

### Queues

In this mock cluster, Slurm partitions are the queues:

| Queue | Nodes | Maximum nodes | Maximum time | GPU capacity | Charge factor |
|---|---|---:|---:|---:|---:|
| `standard` (default) | `c1`, `c2` | 32 | 24 hours | None | 1× |
| `extended` | `c1`, `c2` | 4 | 72 hours | None | 1.5× |
| `accel` | `c3` | 8 | 20 hours | 4 per node | 4× |
| `debug` | `c1`, `c2` | 2 | 30 minutes | None | 1× |

Use `debug` for short checks. GPU requests must use `accel`; other queues
cannot satisfy GPU GRES requests.

### Charges

This disposable cluster records accounting data but does not incur real
charges. The default fixture models a 250,000 node-hour allocation, charged
using the queue factors above. Every user must use their assigned allocation
and account. Rejected jobs cost nothing; accepted jobs consume the modeled
allocation for their runtime.

### Required user-specific information

Every user must determine and use all of the following when constructing a
job:

- User: the current cluster identity (`$USER`); the mock default is
  `demo_user`
- Account: the account assigned to that user; the mock default is
  `proj_astro`, and an account is required
- Queue: choose from `standard`, `extended`, `accel`, or `debug`
- Resources: request explicit nodes, tasks, CPUs per task, memory, and walltime
- Output: write active job output under `/scratch/$USER`

For the default mock account, a minimal batch script is:

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

## Documentation

This file is the agent-facing cluster guidance. Host-side deployment,
authentication, automated episode, and qualification instructions are in the
[mock-cluster README](../src/mock_cluster/README.md).

The scheduler is the source of truth for live state:

```bash
sinfo
scontrol show partition
```

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
