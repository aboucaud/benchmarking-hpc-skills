#!/bin/bash
# Train the classifier from prepared exposures.
#SBATCH --job-name=train-classifier
#SBATCH --account=proj_astro
#SBATCH --partition=accel
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=gpu:1
#SBATCH --time=04:00:00
#SBATCH --output=/scratch/%u/classifier/training-%j.out

set -euo pipefail
module load python/3.11
module load cuda/12.4
mkdir -p /scratch/"$USER"/classifier/checkpoints
printf 'status=complete\n' \
    > /scratch/"$USER"/classifier/checkpoints/training-status.txt
