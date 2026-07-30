#!/usr/bin/env bash
#SBATCH --job-name=summarise-fixture
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:01:00
#SBATCH --output=/scratch/%u/lightcurve-fit/summary-%j.out
set -euo pipefail

echo "summary fixture complete"
