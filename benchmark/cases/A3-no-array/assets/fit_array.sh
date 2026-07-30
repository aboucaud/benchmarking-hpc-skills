#!/usr/bin/env bash
#SBATCH --job-name=fit-array-fixture
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:01:00
#SBATCH --output=/scratch/%u/rv-sweep/fit-%A_%a.out
set -euo pipefail

manifest="${1:?manifest argument required}"
rv="$(sed -n "${SLURM_ARRAY_TASK_ID}p" "${manifest}")"
printf 'fit fixture for R_V=%s\n' "${rv}"
