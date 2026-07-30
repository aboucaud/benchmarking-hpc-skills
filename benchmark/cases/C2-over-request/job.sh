#!/bin/bash
#SBATCH --job-name=classify-inference
#SBATCH --account=proj_astro
#SBATCH --partition=accel
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --gres=gpu:4
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --time=03:00:00
#SBATCH --output=/scratch/%u/classifier/slurm-%j.out

# Run the trained classifier over the validation set.
# Single GPU, single-threaded data loading - the model does not shard across devices.

module load python/3.11
module load cuda/12.4

python infer.py \
    --checkpoint /scratch/"$USER"/classifier/checkpoints/best.pt \
    --input /scratch/"$USER"/classifier/validation \
    --output /scratch/"$USER"/classifier/predictions.parquet
