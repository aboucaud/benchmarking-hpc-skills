# Mock Slurm cluster

A self-contained Slurm cluster for local benchmark development and testing. It
uses Docker Compose and does not depend on Dagster or a checkout of another
repository.

The cluster contains:

- one MariaDB instance for Slurm accounting;
- one `slurmdbd` accounting daemon;
- one internal `slurmctld` controller;
- one login node that provides SSH access and a pinned Codex CLI;
- two CPU compute nodes, `c1` and `c2`;
- one fake-accelerator node, `c3`, with scheduler-only GPU GRES;
- shared `/home`, `/scratch`, `/archive`, `/episode/work`, and `/data` volumes;
  and
- benchmark partitions generated from `benchmark/center.yaml`.

The login node is limited to one CPU and 2 GB of memory. Each compute node
is limited by Docker to two CPUs and 4 GB. Slurm advertises the larger synthetic
resource counts expected by the benchmark; the workloads are functional
stand-ins, not performance tests. The login node does not run `slurmd`.

## Requirements

- Docker Engine or Docker Desktop
- Docker Compose v2 (`docker compose`)
- Docker Desktop configured with at least 8 GB is recommended

Container memory settings are ceilings rather than reservations. The image
builds Slurm from source, so the initial build can take several minutes; the
build defaults to two compiler jobs to avoid saturating a laptop. All seven
Slurm services share the same image and its layers; Compose does not build
seven independent copies.

## Start the cluster

From this directory:

```bash
docker compose up -d --build --wait --wait-timeout 180
./smoke-test.sh
```

The smoke test waits for all three compute nodes, submits CPU and synthetic-GPU
jobs, and verifies the CPU job's accounting record.

To start without rebuilding:

```bash
docker compose up -d
```

## Use the cluster

Connect over SSH:

```bash
ssh -p 2223 demo_user@127.0.0.1
```

The local development password is `demo_user`.

Once connected:

```bash
sinfo
sbatch --account=proj_astro --partition=debug --wrap="hostname"
squeue --me
sacct
```

Alternatively, run commands without SSH:

```bash
docker compose exec --user demo_user login sinfo
docker compose exec --user demo_user login \
  sbatch --chdir=/data --output=/data/slurm-%j.out \
  --account=proj_astro --partition=debug --wrap="hostname"
```

Job scripts and output can be placed in `/data`, which is shared by the
login and compute nodes.

## Run Codex on the login node

Codex is installed in the image and runs inside `login`, not on the host.
The benchmark default is `gpt-5.6-terra`:

```bash
ssh -p 2223 demo_user@127.0.0.1
codex login --device-auth
codex -C /episode/work
```

Open the device-auth URL in the laptop browser and enter the one-time code.
Credentials are stored in the cluster's disposable home volume. Do not bake
credentials into the image or commit them.

For a headless run from the host, invoke Codex inside the login container and
capture its JSONL event log:

```bash
docker compose exec -T --user demo_user login codex-benchmark \
  < ../benchmark/cases/A1-srun-loop/prompt.md \
  > codex-events.jsonl
```

Run that command from `mock-cluster`, or from the repository root with
`docker compose --project-directory mock-cluster ...`.

The equivalent SSH command works after configuring public-key authentication:

```bash
ssh -p 2223 demo_user@127.0.0.1 codex-benchmark \
  < benchmark/cases/A1-srun-loop/prompt.md \
  > codex-events.jsonl
```

Use a key for automation because password authentication needs an interactive
prompt. In both forms, the Codex process runs inside the Slurm login node.

`codex-benchmark` runs `codex exec` in `/episode/work` with
`gpt-5.6-terra`, an ephemeral session, JSONL output, and a workspace-write
sandbox. It also skips the Git-checkout requirement because episode workspaces
are intentionally minimal. Override the model for an explicit experiment with
`CODEX_MODEL=<model> codex-benchmark`; do not rely on an operator's personal
default.

## Stop or reset the cluster

Stop the containers while retaining jobs, homes, and accounting data:

```bash
docker compose down
```

Remove all cluster state and return to a clean benchmark environment:

```bash
./reset.sh
```

`reset.sh` deletes the Docker volumes belonging to this Compose project. It
does not delete the locally built image.

## Configuration

Copy `.env.example` to `.env` to change the local image name, Slurm source
version, or host SSH port:

```bash
cp .env.example .env
```

From the repository root, `src/hpcbench/render.py` regenerates the MVP
documentation and detector artifacts from `benchmark/center.yaml`. It also
checks this Docker configuration for scheduler drift:

```bash
uv run --with pyyaml src/hpcbench/render.py write
uv run --with pyyaml src/hpcbench/render.py check
uv run --with pyyaml src/hpcbench/render.py drift
```

The renderer does not rewrite the Docker files. If the center descriptor
changes, update the mock-cluster snapshots deliberately and use `drift` to
verify their scheduler invariants.

The generated partitions are:

| Partition | Default | Nodes | Maximum time |
| --- | --- | --- | --- |
| `standard` | yes | `c1`, `c2` | 24 hours |
| `extended` | no | `c1`, `c2` | 72 hours |
| `accel` | no | `c3` | 20 hours |
| `debug` | no | `c1`, `c2` | 30 minutes |

After changing a Slurm configuration file, rebuild from clean cluster state:

```bash
./reset.sh
docker compose up -d --build --wait --wait-timeout 180
./smoke-test.sh
```

## Troubleshooting

### Cannot connect to the Docker API

If Compose reports that it cannot connect to `docker.sock`, verify that the
Docker daemon is running:

```bash
docker info
```

On macOS with Docker Desktop:

```bash
docker desktop start
```

Wait until `docker info` includes a `Server` section, then run the start
commands again.

### Inspect container health

```bash
docker compose ps
docker compose logs slurmdbd slurmctld login c1 c2 c3
```

If an earlier configuration left incompatible state behind, reset the cluster
volumes and rebuild:

```bash
./reset.sh
docker compose up -d --build --wait --wait-timeout 180
./smoke-test.sh
```

## Security

This cluster is for local testing only. `demo_user` has a known development
password but no `sudo`. SSH is bound to `127.0.0.1` by default, so it is not
exposed on the LAN. Do not deploy this configuration on a public or shared
host.

## Origin

The Docker setup was adapted from:

- <https://github.com/ascii-supply-networks/dagster-slurm>
- <https://github.com/giovtorres/slurm-docker-cluster>

See `UPSTREAM_LICENSE` for the retained upstream license and attribution.
