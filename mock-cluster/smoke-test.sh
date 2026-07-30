#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
compose=(docker compose --project-directory "${script_dir}" -f "${script_dir}/compose.yaml")

if ! "${compose[@]}" ps --status running --services | grep -Fxq login; then
    echo "The mock Slurm cluster is not running." >&2
    echo "Start it with: docker compose up -d --build" >&2
    exit 1
fi

echo "Waiting for two schedulable compute nodes ..."
deadline=$((SECONDS + 120))
while (( SECONDS < deadline )); do
    idle_nodes="$(
        "${compose[@]}" exec -T login \
            sinfo --noheader --Node --states=idle --format='%N' 2>/dev/null \
            | sort -u \
            | wc -l \
            | tr -d ' ' \
            || true
    )"
    if [ "${idle_nodes}" = "2" ]; then
        break
    fi
    sleep 2
done

if [ "${idle_nodes:-0}" != "2" ]; then
    echo "The compute nodes did not become idle within 120 seconds." >&2
    "${compose[@]}" ps
    exit 1
fi

echo "Submitting a two-node smoke-test job ..."
"${compose[@]}" exec -T --user submitter login bash -lc '
    set -euo pipefail
    cd /data

    job_id="$(
        sbatch \
            --parsable \
            --wait \
            --partition=regular \
            --nodes=2 \
            --ntasks=2 \
            --ntasks-per-node=1 \
            --output="smoke-%j.out" \
            --wrap="srun hostname"
    )"

    deadline=$((SECONDS + 30))
    state=""
    while (( SECONDS < deadline )); do
        state="$(sacct --noheader --allocations --jobs="${job_id}" --format=State \
            | awk "NF { print \$1; exit }")"
        if [ "${state}" = "COMPLETED" ]; then
            break
        fi
        sleep 1
    done

    test "${state}" = "COMPLETED"
    grep -Fxq c1 "smoke-${job_id}.out"
    grep -Fxq c2 "smoke-${job_id}.out"

    printf "Job %s completed on both compute nodes:\\n" "${job_id}"
    sort "smoke-${job_id}.out"
'

echo "Mock Slurm cluster is ready."
