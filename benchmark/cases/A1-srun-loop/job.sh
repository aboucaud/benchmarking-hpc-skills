#!/bin/bash
#SBATCH --job-name=lightcurve-fit
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=02:00:00
#SBATCH --output=/scratch/%u/lightcurve-fit/slurm-%j.out

# Fit a Salt2 model to each supernova light curve in the input catalogue.
# Catalogue has 2000 entries; each fit takes ~20 s on 4 cores.

module load python/3.11

INDIR=/scratch/$USER/lightcurve-fit/input
OUTDIR=/scratch/$USER/lightcurve-fit/output
mkdir -p "$OUTDIR"

for i in $(seq 1 2000); do
    srun -n1 --exclusive python fit_lightcurve.py \
        --index "$i" \
        --input "$INDIR/catalogue.parquet" \
        --output "$OUTDIR" &
done

wait

echo "fitted 2000 light curves"
