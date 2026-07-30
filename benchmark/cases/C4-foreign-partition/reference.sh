#!/bin/bash
# Reference remedy: find out what this centre actually calls its GPU partition and use that name.
# `sinfo` or `scontrol show partition` answers it; the published INSTRUCTIONS.md answers it too.
#
# This is *a* correct answer — see case.yaml:accepted_remedies.

#SBATCH --job-name=sed-fit
#SBATCH --account=proj_astro
#SBATCH --partition=accel
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=06:00:00
#SBATCH --output=/scratch/%u/sedfit/slurm-%j.out

module load python/3.11
module load cuda/12.4

python fit_seds.py \
    --catalogue /scratch/"$USER"/sedfit/input/dr3.parquet \
    --outdir /scratch/"$USER"/sedfit/output \
    --devices 1
