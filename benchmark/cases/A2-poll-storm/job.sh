#!/bin/bash
# run_campaign.sh — submit the catalogue fit and wait for it, then build the summary plot.
set -euo pipefail

JOBID=$(sbatch --parsable fit_catalogue.sh)
echo "submitted $JOBID"

# Wait for it to finish so the summary plot has something to read.
while squeue -j "$JOBID" -h -o %T | grep -qE 'PENDING|RUNNING|CONFIGURING'; do
    sleep 1
done

echo "job $JOBID finished, building summary"
python make_summary.py --input /scratch/"$USER"/lightcurve-fit/output
