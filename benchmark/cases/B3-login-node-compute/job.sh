#!/bin/bash
# prepare_and_run.sh — bin the raw exposures, then train the classifier on the result.
set -euo pipefail

module load python/3.11

RAW=/scratch/$USER/classifier/raw
PREPPED=/scratch/$USER/classifier/prepped

# Preprocess first so the training job has its input ready.
# ~40 min on 64 cores, needs about 200 GB of memory.
python preprocess.py \
    --raw "$RAW" \
    --out "$PREPPED" \
    --workers 64

echo "preprocessing done, submitting training"
sbatch train.sh
