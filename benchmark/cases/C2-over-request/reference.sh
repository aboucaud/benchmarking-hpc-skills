#!/bin/bash
# Reference remedy: request what the workload uses. One GPU, 8 cores, no exclusive hold, so the
# other three A100s on the node stay available to other jobs.
#
# `accel` carries qos_factor 4, so over-requesting here costs four times what the same mistake
# would on `standard` — worth stating when explaining the fix.
#
# This is *a* correct answer — see case.yaml:accepted_remedies.

#SBATCH --job-name=classify-inference
#SBATCH --account=proj_astro
#SBATCH --partition=accel
#SBATCH --nodes=1
#SBATCH --gres=gpu:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=03:00:00
#SBATCH --output=/scratch/%u/classifier/slurm-%j.out

module load python/3.11
module load cuda/12.4

python infer.py \
    --checkpoint /scratch/"$USER"/classifier/checkpoints/best.pt \
    --input /scratch/"$USER"/classifier/validation \
    --output /scratch/"$USER"/classifier/predictions.parquet
