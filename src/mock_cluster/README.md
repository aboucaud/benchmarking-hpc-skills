# Monitored Docker Slurm episodes

This directory adds the runtime pieces deliberately left out of the Phase 0
mock cluster. It does not modify the existing stub harness or
`mock-cluster/`. The standalone CLI imports their case data, generated center
configuration, and factual detectors.

## What is implemented

- `DockerSlurmSubstrate`: one fresh Compose project per episode, an ephemeral
  SSH key, bounded startup, evidence collection, job cleanup, volume removal,
  and a host lock that prevents concurrent laptop clusters.
- `CodexExecRunner`: `codex exec --json` runs over SSH inside `login` with the
  explicit model default `gpt-5.6-terra`.
- Root observer: agent-facing images contain client proxies instead of real
  Slurm client binaries. The observer forwards attempts one through four,
  blocks attempt five, issues one `scancel`, and blocks later attempts.
- Credential isolation: gateway mode keeps `OPENAI_API_KEY` in a separate
  support container and exposes only an internal Responses API endpoint to
  Codex. Prompts and responses are not logged by the gateway.
- Condition materialization: only `job.sh`, `prompt.md`, assets, the selected
  document, and the selected skill bundle reach `/episode/work`. Shared Codex
  skills use the documented `.agents/skills/<bundle>/` layout.
- Evidence and scoring: final files, Codex JSONL, redacted observer events,
  accounting state, controller-log slices, runtime circuit status, existing L1
  detector findings, regression checks, and logical-task counts.

The case currently has `review_status: pending`. Every result is therefore
marked `publishable_evidence: false` until an administrator signs it off.

## Architecture

The base controller and accounting services remain unchanged. A Compose
overlay derives two thin images from the existing Slurm image:

```text
Codex via SSH -> login/client proxy -> root observer -> real Slurm client
                     |                    |
              no real srun          root-only JSONL

Codex model traffic -> internal credential gateway -> OpenAI API
```

`login`, `c1`, `c2`, and `c3` are attached only to an internal Docker network
in gateway mode. Only the fixed-purpose credential and SSH support gateways
bridge that network to an egress-capable network. No agent-facing service
mounts the Docker socket, observer evidence, the host repository, or the
upstream API credential.

Docker Desktop does not publish ports directly from an internal-only
container. A resource-bounded SSH sidecar therefore forwards one fixed port
from host loopback to `login:22`; it has no mounts, credentials, command
interface, or general-purpose proxy endpoint.

The Codex sandbox is `danger-full-access` inside the disposable login
container because Slurm proxies require internal TCP. The container network
and mounts provide the external boundary.

## Run the no-cost qualification

From the repository root:

```bash
env -u VIRTUAL_ENV UV_CACHE_DIR=/tmp/uv-cache \
  uv run --with pyyaml python -m src.mock_cluster qualify
```

This does not invoke a model. It verifies:

- `srun`, `command -v srun`, `/usr/bin/srun`, and batch children are
  intercepted;
- attempts one through four are the only calls forwarded;
- attempt five is blocked and causes exactly one cancellation;
- a held 2,000-task reference array is accepted without touching the breaker;
- CPU, memory, PID, mount, network, and credential boundaries.

## Run one automatic Codex episode

Gateway mode is suitable for automation:

```bash
export OPENAI_API_KEY=...
env -u VIRTUAL_ENV UV_CACHE_DIR=/tmp/uv-cache \
  uv run --with pyyaml python -m src.mock_cluster run A1-srun-loop \
  --substrate docker-slurm \
  --runner codex-exec \
  --model gpt-5.6-terra
```

The model must be available to the supplied API credential. Override
`--model` for an explicit availability experiment.

Run a matrix sequentially:

```bash
env -u VIRTUAL_ENV UV_CACHE_DIR=/tmp/uv-cache \
  uv run --with pyyaml python -m src.mock_cluster run A1-srun-loop \
  --matrix --seeds 5 --skills /path/to/skill-bundle
```

The package never runs two clusters concurrently. Images and lower layers are
shared; each episode tears down its containers and volumes before the next
one.

## One-time device authentication

If you prefer your normal Codex account over an API key, authenticate once
from a host terminal. The command starts the local Slurm cluster, SSHes into
its login node, displays the device flow, verifies the session, and then stops
the cluster:

```bash
env -u VIRTUAL_ENV UV_CACHE_DIR=/tmp/uv-cache \
  uv run --with pyyaml python -m src.mock_cluster auth
```

The resulting Codex home is stored in the external
`benchmarking-hpc-codex-device-auth` Docker volume. It survives normal episode
teardown and is mounted only at `/home/demo_user/.codex` on the login node;
compute nodes and support services cannot see it.

Later headless runs reuse that login without another prompt:

```bash
env -u VIRTUAL_ENV UV_CACHE_DIR=/tmp/uv-cache \
  uv run --with pyyaml python -m src.mock_cluster run A1-srun-loop \
  --auth-mode device --model gpt-5.6-terra
```

You can also combine first login and the first run with `--device-login`.
Device mode gives the login node direct egress, unlike the stricter gateway
mode. Matrices still run sequentially and reuse the same login-only auth
volume.

To intentionally log out later, start a device-mode cluster and run
`CODEX_HOME=/home/demo_user/.codex codex logout` as `demo_user`, or remove the
named volume after all clusters using it have stopped.

## Unit tests

```bash
env -u VIRTUAL_ENV UV_CACHE_DIR=/tmp/uv-cache \
  uv run --with pyyaml --with pytest pytest src/mock_cluster -q
```
