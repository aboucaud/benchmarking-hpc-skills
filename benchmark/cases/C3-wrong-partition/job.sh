#!/bin/bash
#SBATCH --job-name=train-photoz
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=gpu:2
#SBATCH --time=12:00:00
#SBATCH --output=/scratch/%u/photoz/slurm-%j.out

# Train the photometric-redshift network. Data-parallel across 2 GPUs.

module load python/3.11
module load cuda/12.4

python train_photoz.py \
    --input /scratch/"$USER"/photoz/train \
    --devices 2 \
    --checkpoint-dir /scratch/"$USER"/photoz/checkpoints
