#!/bin/bash
#SBATCH --job-name=extract-cutouts
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --time=08:00:00
#SBATCH --output=/scratch/%u/cutouts/slurm-%j.out

# Extract a 64x64 pixel cutout around each source in the detection catalogue.
# 500,000 sources, ~120 kB per cutout.

module load python/3.11

CATALOGUE=/scratch/$USER/cutouts/input/detections.parquet
OUTDIR=/scratch/$USER/cutouts/output
mkdir -p "$OUTDIR"

python extract_cutouts.py \
    --catalogue "$CATALOGUE" \
    --outdir "$OUTDIR" \
    --one-file-per-source \
    --workers 64

echo "wrote cutouts to $OUTDIR"
