#!/bin/bash
# Reference remedy: output to scratch, the filesystem declared for job I/O, with an explicit note
# that scratch is purged after 30 days so the results need archiving.
#
# This is *a* correct answer — see case.yaml:accepted_remedies.

#SBATCH --job-name=nbody-snapshots
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=8
#SBATCH --ntasks-per-node=128
#SBATCH --time=18:00:00
#SBATCH --output=/scratch/%u/nbody/slurm-%j.out

module load gcc/13.2
module load openmpi/5.0

INDIR=/scratch/$USER/nbody/input
OUTDIR=/scratch/$USER/nbody/output
mkdir -p "$OUTDIR"

srun ./nbody \
    --initial-conditions "$INDIR/ics.hdf5" \
    --steps 2000 \
    --snapshot-every 10 \
    --output-dir "$OUTDIR"

echo "snapshots written to $OUTDIR"
echo "NOTE: scratch is purged 30 days after last access. Copy anything you need to keep to"
echo "      /archive/$USER before then."
