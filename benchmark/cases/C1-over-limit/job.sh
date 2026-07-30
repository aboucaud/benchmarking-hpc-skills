#!/bin/bash
#SBATCH --job-name=mhd-relax
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=128
#SBATCH --time=48:00:00
#SBATCH --output=/scratch/%u/mhd/slurm-%j.out

# Relax the MHD initial conditions to equilibrium. Takes about 44 h on 2 nodes.
# The solver checkpoints every 30 min and can restart from the latest checkpoint.

module load gcc/13.2
module load openmpi/5.0

srun ./mhd_relax \
    --config /scratch/"$USER"/mhd/input/relax.toml \
    --checkpoint-dir /scratch/"$USER"/mhd/checkpoints \
    --output /scratch/"$USER"/mhd/output
