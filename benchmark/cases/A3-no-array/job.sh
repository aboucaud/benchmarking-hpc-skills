#!/bin/bash
# sweep.sh — scan the dust-extinction prior over 20 values.
set -euo pipefail

RV_VALUES="2.0 2.2 2.4 2.6 2.8 3.0 3.1 3.2 3.4 3.6 3.8 4.0 4.2 4.4 4.6 4.8 5.0 5.2 5.4 5.6"

for rv in $RV_VALUES; do
    sbatch fit_one.sh "$rv"
done

echo "submitted sweep over 20 R_V values"
