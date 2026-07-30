#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "Removing the mock Slurm containers and all cluster data ..."
docker compose \
    --project-directory "${script_dir}" \
    -f "${script_dir}/compose.yaml" \
    down --volumes --remove-orphans
