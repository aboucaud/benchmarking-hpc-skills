#!/usr/bin/env bash
#SBATCH --job-name=preprocess-fixture
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --time=00:01:00
#SBATCH --output=/scratch/%u/classifier/preprocess-%j.out
set -euo pipefail

python preprocess.py \
    --raw /scratch/"$USER"/classifier/raw \
    --out /scratch/"$USER"/classifier/prepped \
    --workers 64
