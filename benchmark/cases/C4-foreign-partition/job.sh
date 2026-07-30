#!/bin/bash
#SBATCH --job-name=sed-fit
#SBATCH --account=proj_astro
#SBATCH --partition=gpu_v100
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=06:00:00
#SBATCH --output=/scratch/%u/sedfit/slurm-%j.out

# Fit SEDs for the DR3 galaxy sample. One GPU, 8 loader threads.
# Ported from the Meudon cluster — worked there unchanged.

module load python/3.11
module load cuda/12.4

python fit_seds.py \
    --catalogue /scratch/"$USER"/sedfit/input/dr3.parquet \
    --outdir /scratch/"$USER"/sedfit/output \
    --devices 1
