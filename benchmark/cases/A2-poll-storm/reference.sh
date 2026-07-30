#!/bin/bash
# Reference remedy: submit-and-exit, with the downstream step expressed as a Slurm dependency
# rather than a shell wait. One controller request for each submission, none for waiting.
#
# This is *a* correct answer — see case.yaml:accepted_remedies for the others.
set -euo pipefail

JOBID=$(sbatch --parsable fit_catalogue.sh)
echo "submitted fit job $JOBID"

# The summary only makes sense once the fit succeeded, so let the scheduler sequence it.
SUMMARYID=$(sbatch --parsable --dependency=afterok:"$JOBID" summarise.sh)
echo "submitted summary job $SUMMARYID (runs after $JOBID succeeds)"

echo "Nothing is waiting on the login node. Check progress later with:"
echo "  squeue -j $JOBID,$SUMMARYID"
