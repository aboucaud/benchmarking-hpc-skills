#!/bin/bash
# Clean by construction: this batch script contains no defect. The defect in case A2 lives in
# the driver (run_campaign.sh), not here.
#SBATCH --job-name=fit-catalogue
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --time=06:00:00
#SBATCH --output=/scratch/%u/lightcurve-fit/slurm-%j.out

module load python/3.11

python fit_catalogue.py \
    --input /scratch/"$USER"/lightcurve-fit/input/catalogue.parquet \
    --output /scratch/"$USER"/lightcurve-fit/output \
    --workers 64
