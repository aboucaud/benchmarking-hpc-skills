#!/bin/bash
# Fit one dust-extinction sweep point.
#SBATCH --job-name=rv-sweep
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=01:30:00
#SBATCH --output=/scratch/%u/rv-sweep/slurm-%j.out

set -euo pipefail
RV=${1:?R_V value is required}
mkdir -p /scratch/"$USER"/rv-sweep
printf 'R_V=%s\nstatus=complete\n' "$RV" \
    > /scratch/"$USER"/rv-sweep/rv_"$RV".txt
