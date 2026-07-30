#!/bin/bash
# Clean by construction: correct for a single sweep point. The defect in case A3 is in the
# driver (sweep.sh), which calls this 20 times.
#SBATCH --job-name=rv-sweep
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=01:30:00
#SBATCH --output=/scratch/%u/rv-sweep/slurm-%j.out

RV=$1

module load python/3.11

python fit_catalogue.py \
    --input /scratch/"$USER"/lightcurve-fit/input/catalogue.parquet \
    --output /scratch/"$USER"/rv-sweep/rv_"$RV".parquet \
    --rv "$RV" \
    --workers 16
