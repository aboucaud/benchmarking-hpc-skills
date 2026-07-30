#!/bin/bash
#SBATCH --job-name=nbody-snapshots
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=128
#SBATCH --time=18:00:00
#SBATCH --output=/scratch/%u/nbody/slurm-%j.out

# Run the N-body simulation and dump a snapshot every 10 steps.
# 2000 steps -> 200 snapshots, ~10 GB each, so ~2 TB total.

module load gcc/13.2
module load openmpi/5.0

INDIR=/scratch/$USER/nbody/input
OUTDIR=$HOME/simulations/output
mkdir -p "$OUTDIR"

srun ./nbody \
    --initial-conditions "$INDIR/ics.hdf5" \
    --steps 2000 \
    --snapshot-every 10 \
    --output-dir "$OUTDIR"

echo "snapshots written to $OUTDIR"
