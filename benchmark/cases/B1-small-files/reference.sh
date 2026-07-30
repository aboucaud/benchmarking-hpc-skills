#!/bin/bash
# Reference remedy: aggregate into HDF5 containers, 5,000 sources each. 500,000 small writes
# become 100 large ones, and the indexed container keeps individual sources retrievable.
#
# Note that extract_cutouts.py already offers --chunk-size, so the remedy is a flag change, not a
# rewrite. This is *a* correct answer — see case.yaml:accepted_remedies.

#SBATCH --job-name=extract-cutouts
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --time=08:00:00
#SBATCH --output=/scratch/%u/cutouts/slurm-%j.out

module load python/3.11

CATALOGUE=/scratch/$USER/cutouts/input/detections.parquet
OUTDIR=/scratch/$USER/cutouts/output
mkdir -p "$OUTDIR"

python extract_cutouts.py \
    --catalogue "$CATALOGUE" \
    --outdir "$OUTDIR" \
    --chunk-size 5000 \
    --workers 64

echo "wrote 100 indexed cutout containers to $OUTDIR"
