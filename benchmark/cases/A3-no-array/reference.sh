#!/bin/bash
# Reference remedy: one job array. One controller request instead of twenty, and the sweep
# arrives in the queue as a single unit for fairshare accounting.
#
# The R_V values move into a manifest so the array index maps to a parameter without arithmetic
# assumptions. This is *a* correct answer — see case.yaml:accepted_remedies.
set -euo pipefail

MANIFEST=/scratch/"$USER"/rv-sweep/rv_values.txt
mkdir -p "$(dirname "$MANIFEST")"
printf '%s\n' 2.0 2.2 2.4 2.6 2.8 3.0 3.1 3.2 3.4 3.6 3.8 4.0 4.2 4.4 4.6 4.8 5.0 5.2 5.4 5.6 \
    > "$MANIFEST"

sbatch --array=1-20 fit_array.sh "$MANIFEST"

echo "submitted sweep over 20 R_V values as one array job"
