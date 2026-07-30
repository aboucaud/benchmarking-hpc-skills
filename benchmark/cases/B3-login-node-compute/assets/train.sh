#!/usr/bin/env bash
#SBATCH --job-name=train-fixture
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:01:00
#SBATCH --output=/scratch/%u/classifier/train-%j.out
set -euo pipefail

echo "training fixture complete"
