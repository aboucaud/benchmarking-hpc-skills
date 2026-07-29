# Mock Slurm cluster

A self-contained, two-node Slurm cluster for local development and testing. It
uses Docker Compose and does not depend on Dagster or a checkout of another
repository.

The cluster contains:

- one MariaDB instance for Slurm accounting;
- one `slurmdbd` accounting daemon;
- one internal `slurmctld` controller;
- one login node that provides SSH access;
- two compute nodes, `c1` and `c2`;
- shared `/home` and `/data` volumes; and
- `short`, `regular`, and `long` partitions.

The login node is limited to one CPU and 2 GB of memory. Each compute node
advertises two CPUs and 3.8 GB of memory to Slurm, while Docker limits its
container to two CPUs and 4 GB of memory. The login node does not run
`slurmd`, so Slurm jobs can execute only on `c1` and `c2`.

## Requirements

- Docker Engine or Docker Desktop
- Docker Compose v2 (`docker compose`)
- Approximately 12 GB of available memory if all containers are fully used

The image builds Slurm from source, so the initial build can take several
minutes.

## Start the cluster

From this directory:

```bash
docker compose up -d --build --wait --wait-timeout 180
./smoke-test.sh
```

The smoke test waits for both compute nodes, submits a job, and verifies its
accounting record.

To start without rebuilding:

```bash
docker compose up -d
```

## Use the cluster

Connect over SSH:

```bash
ssh -p 2223 submitter@127.0.0.1
```

The development password is `submitter`.

Once connected:

```bash
sinfo
sbatch --partition=short --wrap="hostname"
squeue --me
sacct
```

Alternatively, run commands without SSH:

```bash
docker compose exec --user submitter login sinfo
docker compose exec --user submitter login \
  sbatch --chdir=/data --output=/data/slurm-%j.out \
  --partition=short --wrap="hostname"
```

Job scripts and output can be placed in `/data`, which is shared by the
login node and both compute nodes.

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

The default topology is defined in `slurm.conf`:

| Partition | Default | Nodes | Maximum time |
| --- | --- | --- | --- |
| `short` | no | one | 30 minutes |
| `regular` | yes | two | one day |
| `long` | no | two | five days |

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
docker compose logs slurmdbd slurmctld login c1 c2
```

If an earlier configuration left incompatible state behind, reset the cluster
volumes and rebuild:

```bash
./reset.sh
docker compose up -d --build --wait --wait-timeout 180
./smoke-test.sh
```

## Security

This cluster is for local testing only. The `submitter` account has a known
password and passwordless `sudo`. SSH is bound to `127.0.0.1` by default so it
is not exposed on the LAN. Do not deploy this configuration on a public or
shared host.

## Origin

The Docker setup was adapted from:

- <https://github.com/ascii-supply-networks/dagster-slurm>
- <https://github.com/giovtorres/slurm-docker-cluster>

See `UPSTREAM_LICENSE` for the retained upstream license and attribution.
