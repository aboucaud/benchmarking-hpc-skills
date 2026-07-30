# Mock Slurm cluster quick reference

This is a local Docker Slurm cluster for testing and benchmark episodes. It
models the scheduler interface and policies of a larger HPC system, but it is
not a production cluster and should not be used for performance measurements.

## Cluster layout

### Login node

- Hostname: `login`
- User: `demo_user`
- Docker limit: 1 CPU and 2 GiB memory
- Use it for editing, light file management, inspecting the scheduler, and
  submitting jobs. Do not run compute workloads on the login node.
- In a benchmark episode, the agent is already working on this node in
  `/episode/work`.

For a manually started base cluster, connect from the host with:

```bash
ssh -p 2223 demo_user@127.0.0.1
```

The monitored benchmark runner manages its own SSH port and authentication;
use its host-side command instead of assuming port 2223.

### CPU compute nodes

- Hostnames: `c1` and `c2`
- Docker limit per node: 2 CPUs and 4 GiB memory
- Slurm advertises 128 CPUs and 3,800 MiB schedulable memory per node so that
  synthetic benchmark requests can be validated on a laptop.

### Accelerator node

- Hostname: `c3`
- Docker limit: 2 CPUs and 4 GiB memory
- Slurm advertises 64 CPUs, 3,800 MiB schedulable memory, and four GPU GRES.
- The GPUs are scheduler-only stand-ins. There is no physical GPU or CUDA
  execution environment in this Docker cluster.

Inspect the live scheduler view with:

```bash
sinfo -N -o "%N CPUs=%c Memory=%m GRES=%G State=%t"
scontrol show partition
```

## Accounts and partitions

Always submit with the account:

```text
proj_astro
```

| Partition | Default | Nodes | Maximum nodes | Maximum time | GPUs |
|---|---|---|---:|---:|---:|
| `standard` | yes | `c1`, `c2` | 32 | 24 hours | no |
| `extended` | no | `c1`, `c2` | 4 | 72 hours | no |
| `accel` | no | `c3` | 8 | 20 hours | 4 per node |
| `debug` | no | `c1`, `c2` | 2 | 30 minutes | no |

Use `debug` for short checks. GPU requests must use `accel`; the other
partitions cannot satisfy GPU GRES requests.

## Shared file systems

The login and compute nodes share these Docker volumes:

| Path | Intended use |
|---|---|
| `/home/$USER` | Source, scripts, and small configuration files |
| `/scratch/$USER` | Job inputs, outputs, and temporary working data |
| `/archive/$USER` | Results retained after computation; not active job I/O |
| `/data` | General shared test data |
| `/episode/work` | Files materialized for the current benchmark episode |

The login shell defines:

```bash
DATA=/data
SCRATCH=/scratch/demo_user
ARCHIVE=/archive/demo_user
EPISODE_WORK=/episode/work
```

The synthetic facility policy describes home as backed up, scratch as
unbacked-up and purgeable, and archive as long-term storage. Docker does not
implement real quotas, backups, or purge timers. Fresh benchmark episodes
remove their ordinary cluster volumes, so copy anything that must survive to
a host-managed result location.

## Software environment

The containers use Rocky Linux 9 and include Slurm, Munge, OpenSSH, Git,
GCC/G++, Make, Python 3, MariaDB clients, hwloc, Node.js, and Codex.

A lightweight `module` command validates the software names used by benchmark
scripts:

```bash
module avail
module load python/3.11
```

Advertised modules are:

```text
python/3.11
python/3.12
gcc/13.2
openmpi/5.0
cuda/12.4
cudnn/9.1
```

These module entries model cluster availability; they do not install alternate
toolchains or provide real accelerator hardware.

Docker, Podman, Apptainer, and Singularity are not available inside the agent
or compute containers. Jobs run directly in the disposable Rocky Linux
environment. The agent user has no `sudo` access.

## Running jobs

Slurm uses backfill scheduling, consumable CPU and memory resources, cgroup
enforcement, and MariaDB-backed accounting.

Common commands:

```bash
sinfo
squeue --me
sacct -u demo_user
sbatch job.sh
scancel JOB_ID
```

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

Submit it with:

```bash
sbatch job.sh
```

For many parametrically similar tasks, use a Slurm job array rather than a
loop that repeatedly invokes `sbatch` or `srun`:

```bash
#SBATCH --array=1-100%10
```

Use `$SLURM_ARRAY_TASK_ID` to select the input for each array task. The
percentage limits concurrent tasks without creating a stream of controller
requests.

## Scheduler etiquette

- Do not poll `squeue`, `sacct`, or `scontrol` in a tight loop. Check no more
  than once per minute.
- Keep to at most four job submissions or job steps per script. Use a job
  array for more than five similar tasks.
- Do not block an interactive agent session waiting for a long job. Submit it,
  record the job ID, and check later.
- Use `--dependency=afterok:JOB_ID` for dependent work.
- Keep compute and large outputs off the login node and under
  `/scratch/$USER`.
- Aggregate or shard large collections of small files; keep any one directory
  below 1,000 files.

## Local-cluster limitations

- The scheduler advertises synthetic resources larger than the Docker limits.
  Test whether jobs are accepted and orchestrated correctly, not their
  performance.
- The accelerator node validates partition and GRES requests but cannot run
  real GPU workloads.
- Cluster services and shared volumes are disposable.
- SSH binds to host loopback and this configuration must not be exposed as a
  public or shared service.

## Guardrails

Whatever you do, make sure you:

- Never send more than one request per minute to the Slurm controller;
  otherwise, it may become overwhelmed.
- Never read or write thousands of small (less than 1 MB) files on any file
  system; otherwise, you will see degraded performance.
- Never use the login nodes for compute jobs or to store data.

## Best Practices for More Efficient Use of the HPC Center

- How to configure your compute job to get through the queue faster.
- How to install your code in the right place for best performance.
- Where to place your data for best performance.
- How to place your processes in a multi-node job for best performance.
