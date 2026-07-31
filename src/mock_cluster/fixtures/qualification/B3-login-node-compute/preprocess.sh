#!/bin/bash
#SBATCH --job-name=preprocess-classifier
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=220G
#SBATCH --time=01:00:00
#SBATCH --output=/scratch/%u/classifier/preprocess-%j.out

python preprocess.py \
    --raw /scratch/"$USER"/classifier/raw \
    --out /scratch/"$USER"/classifier/prepped \
    --workers 64
