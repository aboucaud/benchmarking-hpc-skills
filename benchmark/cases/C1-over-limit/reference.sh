#!/bin/bash
# Reference remedy: move to the `extended` partition, whose declared maximum is 72 h. Valid here
# only because the job needs 2 nodes and `extended` caps at 4.
#
# Trade-off worth stating: extended carries qos_factor 1.5, so this costs 1.5x per node-hour
# against the allocation. The checkpoint-and-chain remedy avoids that at the cost of complexity.
#
# This is *a* correct answer — see case.yaml:accepted_remedies.

#SBATCH --job-name=mhd-relax
#SBATCH --account=proj_astro
#SBATCH --partition=extended
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=128
#SBATCH --time=48:00:00
#SBATCH --output=/scratch/%u/mhd/slurm-%j.out

module load gcc/13.2
module load openmpi/5.0

srun ./mhd_relax \
    --config /scratch/"$USER"/mhd/input/relax.toml \
    --checkpoint-dir /scratch/"$USER"/mhd/checkpoints \
    --output /scratch/"$USER"/mhd/output
