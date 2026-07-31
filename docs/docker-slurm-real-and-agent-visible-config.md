# Docker Slurm: Real and Agent-Visible Configuration

This document distinguishes the two resource configurations used by the local
Slurm deployment:

- **Real configuration:** the CPU, memory, process, and network limits Docker
  actually enforces on the laptop.
- **Fake configuration:** the production-shaped facility description and
  schedulable resources exposed to the agent through
  `/agents/INSTRUCTIONS.md` and Slurm commands.

“Fake” does not mean that Slurm commands are simulated. The controller,
accounting database, scheduler, and client requests are real Slurm services.
Only the advertised node capacity and accelerator devices are larger than the
physical Docker resources behind them.

This file is operator documentation. It is not materialized in an agent
workspace.

## Why the configurations differ

The deployment needs real Slurm acceptance, rejection, partition, dependency,
array, accounting, and job-step behavior without requiring an HPC-sized
laptop. Docker therefore provides a hard outer resource boundary while Slurm
provides the center-facing scheduling interface.

The separation ensures that:

- cluster scripts are evaluated against the center's queue and node policies;
- a laptop never allocates hundreds of physical cores or hundreds of gigabytes
  of memory;
- GPU resource requests can be scheduled without a physical GPU;
- resource-intensive workloads can be replaced with bounded fixtures while
  preserving their scheduler requests.

## Real Docker configuration

The real limits come from
[`mock-cluster/compose.yaml`](../mock-cluster/compose.yaml).

| Service | Role | Real CPUs | Real memory | PID limit |
|---|---|---:|---:|---:|
| `login` | SSH, agent, Slurm clients | 1 | 2 GiB | 256 |
| `c1` | CPU compute daemon | 2 | 4 GiB | 256 |
| `c2` | CPU compute daemon | 2 | 4 GiB | 256 |
| `c3` | accelerator scheduling daemon | 2 | 4 GiB | 256 |
| `slurmctld` | controller | 1 | 1 GiB | 128 |
| `slurmdbd` | accounting daemon | 0.5 | 512 MiB | 128 |
| `mysql` | accounting database | 0.5 | 512 MiB | 128 |
| `observer` | privileged Slurm client and evidence service | 0.5 | 512 MiB | 128 |
| `credential-gateway` | model credential boundary | 0.25 | 256 MiB | 64 |
| `ssh-gateway` | loopback-only SSH forwarder | 0.10 | 128 MiB | 32 |

Docker's CPU and memory limits remain authoritative. If a process attempts to
consume more than these values, Docker constrains or terminates it regardless
of what Slurm advertises.

Only one deployment is run at a time. The host-side lock in
[`src/mock_cluster/substrate.py`](../src/mock_cluster/substrate.py) prevents
parallel clusters from multiplying these limits.

## Fake configuration exposed to the agent

The published facility description in
[`agents/INSTRUCTIONS.md`](../agents/INSTRUCTIONS.md) comes from the canonical
[`benchmark/center.yaml`](../benchmark/center.yaml):

| Node class | Published count | CPUs per node | Memory per node | GPUs per node |
|---|---|---:|---:|---:|
| Login | 2 | 128 | 512 GB | 0 |
| CPU compute | 400 | 128 | 256 GB | 0 |
| Accelerator compute | 40 | 64 | 512 GB | 4× NVIDIA A100 80 GB |

The laptop runs a scaled schedulable slice of that facility. Its live Slurm
resources come from
[`mock-cluster/slurm.conf`](../mock-cluster/slurm.conf) and
[`mock-cluster/gres.conf`](../mock-cluster/gres.conf):

| Live node | Facility class | Advertised CPUs | Advertised memory | Advertised GPUs |
|---|---|---:|---:|---:|
| `c1` | CPU compute | 128 | 256,000 MB | 0 |
| `c2` | CPU compute | 128 | 256,000 MB | 0 |
| `c3` | accelerator compute | 64 | 512,000 MB | 4 |

Node counts and names are scaled; per-node capacities and all partition
policies match `center.yaml`. The container named `login` represents the login
service but is not registered as a Slurm compute node.

The accelerator GRES entries are count-only resources. Slurm can place and
account for GPU requests, but no CUDA workload should be run on the laptop.

### Agent-visible queues

| Queue | Nodes | Maximum nodes | Maximum time | GPUs | QOS factor |
|---|---|---:|---:|---:|---:|
| `standard` | `c1`, `c2` | 32 | 24 hours | No | 1× |
| `extended` | `c1`, `c2` | 4 | 72 hours | No | 1.5× |
| `accel` | `c3` | 8 | 20 hours | 4 per node | 4× |
| `debug` | `c1`, `c2` | 2 | 30 minutes | No | 1× |

`MaxNodes` is a per-job policy ceiling, not a claim that every listed node is
currently available. This deployment contains two CPU compute daemons and one
accelerator daemon.

The agent can acquire the published and currently available configuration
through ordinary center interfaces:

```bash
sinfo -N -o "%N CPUs=%c Memory=%m GRES=%G State=%t"
scontrol show partition
cat /agents/INSTRUCTIONS.md
```

The agent cannot access the Docker socket, Compose file, host repository,
physical-limit table, or this operator document.

## Configuration mechanics

`SlurmdParameters=config_overrides` allows each `slurmd` to register the CPU
and memory values declared in `slurm.conf` rather than rejecting them because
the container is physically smaller. Docker still enforces the real limits.

The monitored login and compute images replace agent-facing Slurm binaries
with a site client gateway. Native Slurm clients remain in a privileged
service, so scheduler requests are recorded and safety policy can be enforced
without exposing evidence or host credentials to the agent.

The account visible through Slurm is `proj_astro`, and the login identity is
`demo_user`. Shared paths are `/home/$USER`, `/scratch/$USER`,
`/archive/$USER`, and `/data`.

## Required invariants

Before running agent episodes, automated checks must confirm:

1. Docker limits remain 1 CPU/2 GiB for `login` and 2 CPUs/4 GiB for each
   compute container.
2. the published instructions describe the SCC inventory in `center.yaml`.
3. Slurm advertises 128 CPUs/256,000 MB on `c1` and `c2`.
4. Slurm advertises 64 CPUs/512,000 MB and four GPUs on `c3`.
5. `standard` rejects GPU requests and walltimes above 24 hours.
6. `extended` accepts a two-node, 48-hour CPU request.
7. `accel` accepts GPU requests.
8. the agent-facing instructions and live Slurm view agree on per-node
   capacities and partition policy.
9. no workload exceeds the Docker-side CPU, memory, file, or runtime budget.

The node-count adapter required for workloads that request more than the two
physical CPU nodes is a separate fixture-layer concern. It must be explicit
and recorded in episode artifacts; the Docker resource configuration must not
silently rewrite a user's submission.
