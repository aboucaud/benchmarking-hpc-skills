#!/usr/bin/env bash
#SBATCH --job-name=fit-catalogue-fixture
#SBATCH --account=proj_astro
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:01:00
#SBATCH --output=/scratch/%u/lightcurve-fit/fit-%j.out
set -euo pipefail

# Long enough to expose a one-second polling loop, but bounded for a laptop.
sleep 5
echo "catalogue fixture complete"
