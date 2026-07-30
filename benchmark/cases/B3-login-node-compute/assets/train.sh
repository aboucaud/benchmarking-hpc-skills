#!/bin/bash
# Clean by construction: correct. The defect in case B3 is in the driver, not here.
#SBATCH --job-name=train-classifier
#SBATCH --account=proj_astro
#SBATCH --partition=accel
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=gpu:1
#SBATCH --time=04:00:00
#SBATCH --output=/scratch/%u/classifier/slurm-%j.out

module load python/3.11
module load cuda/12.4

python train.py \
    --input /scratch/"$USER"/classifier/prepped \
    --checkpoint-dir /scratch/"$USER"/classifier/checkpoints
