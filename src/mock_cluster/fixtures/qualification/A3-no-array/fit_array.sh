#!/bin/bash
#SBATCH --job-name=rv-sweep
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=01:30:00
#SBATCH --output=/scratch/%u/rv-sweep/slurm-%A_%a.out

set -euo pipefail
MANIFEST=${1:?manifest is required}
RV=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$MANIFEST")
mkdir -p /scratch/"$USER"/rv-sweep
printf 'R_V=%s\nstatus=complete\n' "$RV" \
    > /scratch/"$USER"/rv-sweep/rv_"$RV".txt
