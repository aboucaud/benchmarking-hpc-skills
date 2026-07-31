#!/bin/bash
#SBATCH --job-name=fit-summary
#SBATCH --account=proj_astro
#SBATCH --partition=debug
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --output=/scratch/%u/lightcurve-fit/summary-%j.out

python make_summary.py --input /scratch/"$USER"/lightcurve-fit/output
