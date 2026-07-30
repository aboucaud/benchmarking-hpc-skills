#!/bin/bash
# Reference remedy: preprocessing becomes its own job, and training waits on it via a Slurm
# dependency. Nothing heavy runs on the login node, and the ordering is enforced by the scheduler
# rather than by the driver blocking.
#
# This is *a* correct answer — see case.yaml:accepted_remedies.
set -euo pipefail

PREPID=$(sbatch --parsable preprocess.sh)
echo "submitted preprocessing job $PREPID"

TRAINID=$(sbatch --parsable --dependency=afterok:"$PREPID" train.sh)
echo "submitted training job $TRAINID (runs after $PREPID succeeds)"
