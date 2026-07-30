#!/bin/bash
# Reference remedy: target `accel`, the only partition declaring GPUs. This fact is not in the
# script — it comes from the queue table in the center's INSTRUCTIONS.md, or from `sinfo`.
#
# accel carries qos_factor 4, so GPU work costs 4x per node-hour against the allocation. accel nodes
# also have 64 cores rather than standard's 128, which is worth checking when a cpus-per-task value
# has been copied from a standard-partition script (16 is fine here).
#
# This is *a* correct answer — see case.yaml:accepted_remedies.

#SBATCH --job-name=train-photoz
#SBATCH --account=proj_astro
#SBATCH --partition=accel
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=gpu:2
#SBATCH --time=12:00:00
#SBATCH --output=/scratch/%u/photoz/slurm-%j.out

module load python/3.11
module load cuda/12.4

python train_photoz.py \
    --input /scratch/"$USER"/photoz/train \
    --devices 2 \
    --checkpoint-dir /scratch/"$USER"/photoz/checkpoints
