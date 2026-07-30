#!/bin/bash
# Reference remedy: checkpoint-and-chain. Stay on `standard` within its declared 24 h maximum and
# split the ~44 h relaxation into 24 h segments, each resuming from the solver's latest checkpoint
# and chaining the next segment with a Slurm dependency. This is the technically correct fix (per
# @djbard's review): it never exceeds the queue limit and pays qos_factor 1, where `extended` would
# cost 1.5x per node-hour.
#
# This is *a* correct answer — see case.yaml:accepted_remedies (move-to-extended is also valid).

#SBATCH --job-name=mhd-relax
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=128
#SBATCH --time=24:00:00
#SBATCH --output=/scratch/%u/mhd/slurm-%j.out

# Relax the MHD initial conditions to equilibrium (~44 h on 2 nodes). The solver checkpoints every
# 30 min and restarts from the latest checkpoint, so a single 24 h segment makes progress and the
# next segment picks up where it left off — no walltime exceeds the `standard` limit.

module load gcc/13.2
module load openmpi/5.0

CKPT_DIR=/scratch/"$USER"/mhd/checkpoints

srun ./mhd_relax \
    --config /scratch/"$USER"/mhd/input/relax.toml \
    --checkpoint-dir "$CKPT_DIR" \
    --restart-if-present \
    --output /scratch/"$USER"/mhd/output

# Chain the next 24 h segment only if the run has not yet converged. It resumes from the checkpoint
# this segment just wrote; afterany lets it start whether we exited on convergence or at walltime.
if [ ! -f "$CKPT_DIR"/CONVERGED ]; then
    sbatch --dependency=afterany:"$SLURM_JOB_ID" "$0"
fi
