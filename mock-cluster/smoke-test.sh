#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
compose=(docker compose --project-directory "${script_dir}" -f "${script_dir}/compose.yaml")

if ! "${compose[@]}" ps --status running --services | grep -Fxq login; then
    echo "The mock Slurm cluster is not running." >&2
    echo "Start it with: docker compose up -d --build" >&2
    exit 1
fi

echo "Waiting for three schedulable compute nodes ..."
deadline=$((SECONDS + 120))
while (( SECONDS < deadline )); do
    ready_nodes="$(
        "${compose[@]}" exec -T login \
            sinfo --noheader --Node --format='%N|%T' 2>/dev/null \
            | awk -F'|' '$2 == "idle" || $2 == "allocated" || $2 == "mixed" {
                print $1
            }' \
            | sort -u \
            | paste -sd, - \
            || true
    )"
    if [ "${ready_nodes}" = "scc-c0001,scc-c0002,scc-g001" ]; then
        break
    fi
    sleep 2
done

if [ "${ready_nodes:-}" != "scc-c0001,scc-c0002,scc-g001" ]; then
    echo "The compute nodes did not register within 120 seconds." >&2
    "${compose[@]}" ps
    exit 1
fi

echo "Checking the benchmark identity, Codex, modules, partitions, and case limits ..."
"${compose[@]}" exec -T --user demo_user login bash -lc '
    set -euo pipefail

    test "$(id -u)" = "5001"
    codex --version
    command -v codex-benchmark >/dev/null
    grep -Fxq "model = \"${CODEX_MODEL}\"" "${HOME}/.codex/config.toml"
    codex_exec_help="$(codex exec --help)"
    grep -Fq -- "--model" <<< "${codex_exec_help}"
    grep -Fq -- "--skip-git-repo-check" <<< "${codex_exec_help}"
    module load python/3.11 gcc/13.2 openmpi/5.0 cuda/12.4
    module_output="$(module avail)"
    grep -Fxq python/3.11 <<< "${module_output}"

    test "$(sinfo --noheader --format="%P" | sed "s/*//" | sort -u | paste -sd, -)" \
        = "accel,debug,extended,standard"
    slurm_config="$(scontrol show config)"
    grep -Eq "MaxArraySize[[:space:]]*=[[:space:]]*2001" <<< "${slurm_config}"
    association="$(
        sacctmgr --noheader --parsable2 show association \
            where user=demo_user account=proj_astro \
            format=User,Account
    )"
    grep -Fxq "demo_user|proj_astro" <<< "${association}"

    if sbatch --test-only --account=proj_astro --partition=standard \
        --time=48:00:00 --wrap=true >/dev/null 2>&1; then
        echo "standard incorrectly accepted C1 walltime" >&2
        exit 1
    fi
    sbatch --test-only --account=proj_astro --partition=extended \
        --nodes=2 --time=48:00:00 --wrap=true >/dev/null

    if sbatch --test-only --account=proj_astro --partition=standard \
        --gres=gpu:1 --wrap=true >/dev/null 2>&1; then
        echo "standard incorrectly accepted C3 GPU request" >&2
        exit 1
    fi
    sbatch --test-only --account=proj_astro --partition=accel \
        --gres=gpu:1 --wrap=true >/dev/null

    sbatch --test-only --account=proj_astro --partition=standard \
        --array=1-2000%50 --wrap=true >/dev/null
'

echo "Submitting a two-node smoke-test job ..."
"${compose[@]}" exec -T --user demo_user login bash -lc '
    set -euo pipefail
    cd /data

    job_id="$(
        sbatch \
            --parsable \
            --wait \
            --account=proj_astro \
            --partition=standard \
            --nodes=2 \
            --ntasks=2 \
            --ntasks-per-node=1 \
            --output="smoke-%j.out" \
            --wrap="srun hostname"
    )"

    state="$(sacct --noheader --allocations --jobs="${job_id}" --format=State \
        | awk "NF { print \$1; exit }")"
    test "${state}" = "COMPLETED"
    grep -Fxq scc-c0001 "smoke-${job_id}.out"
    grep -Fxq scc-c0002 "smoke-${job_id}.out"

    printf "Job %s completed on both compute nodes:\\n" "${job_id}"
    sort "smoke-${job_id}.out"
'

echo "Submitting a fake-GPU smoke-test job ..."
"${compose[@]}" exec -T --user demo_user login bash -lc '
    set -euo pipefail
    cd /data

    job_id="$(
        sbatch \
            --parsable \
            --wait \
            --account=proj_astro \
            --partition=accel \
            --gres=gpu:1 \
            --output="gpu-smoke-%j.out" \
            --wrap="hostname"
    )"
    test "$(tr -d "[:space:]" < "gpu-smoke-${job_id}.out")" = "scc-g001"
    printf "Job %s completed on the accelerator scheduling node.\\n" "${job_id}"
'

echo "Mock Slurm cluster is ready."
