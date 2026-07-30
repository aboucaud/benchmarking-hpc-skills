#!/bin/bash
#SBATCH --job-name=shear-catalogue
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=128
#SBATCH --time=08:00:00
#SBATCH --output=/scratch/%u/lensing/slurm-%j.out

# Measure shear for the DR3 tiles and write one catalogue per tile.
# 512 tiles, ~1.5 GB each.

module load python/3.11

INDIR=/scratch/$USER/lensing/dr3
OUTDIR=/scratch/$USER/lensing/catalogues
mkdir -p "$OUTDIR"

srun python measure_shear.py \
    --tiles "$INDIR/tiles.txt" \
    --exposures "$INDIR" \
    --output-dir "$OUTDIR"

echo "catalogues written to $OUTDIR"
