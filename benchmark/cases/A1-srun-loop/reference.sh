#!/bin/bash
# Reference remedy: job-array. One controller request for the array, one step per task.
# This is *a* correct answer — see case.yaml:accepted_remedies for the others.
#
# Walltime drops from the whole-catalogue budget to a per-task budget, which is the
# consequence an agent should notice and adjust rather than copy across unchanged.

#SBATCH --job-name=lightcurve-fit
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --array=1-2000%50
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=00:05:00
#SBATCH --output=/scratch/%u/lightcurve-fit/slurm-%A_%a.out

module load python/3.11

INDIR=/scratch/$USER/lightcurve-fit/input
OUTDIR=/scratch/$USER/lightcurve-fit/output
mkdir -p "$OUTDIR"

python fit_lightcurve.py \
    --index "$SLURM_ARRAY_TASK_ID" \
    --input "$INDIR/catalogue.parquet" \
    --output "$OUTDIR"
