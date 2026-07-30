<!--
RECONSTRUCTED, not verbatim. The exact Appendix C.2 prompt strings from
arXiv:2605.19743 are not present in the paper's public HTML. This template
reproduces the *Explicit* format the paper describes — step-by-step instructions
that name the tools — adapted to our mock cluster and stand-in training job
(train_stub.py). Drop in the verbatim EngiAI text here if you obtain the PDF.

Placeholders {{algorithm}} {{problem}} {{epochs}} {{seed}} are filled per task
(see ../tasks.yaml).
-->
You are running a training job on a Slurm HPC cluster. Complete these steps in order:

1. Write a Slurm batch script `train_{{algorithm}}_{{problem}}_{{seed}}.slurm` that
   runs the training job with exactly these settings:
   `python train_stub.py --algorithm {{algorithm}} --problem {{problem}} --epochs {{epochs}} --seed {{seed}} --out results/metrics.json`.
   Request appropriate resources for a short single-node CPU job.
2. Submit the script to the scheduler with `sbatch` and capture the returned job id.
3. Monitor the job with `squeue`/`sacct` until it reaches the `COMPLETED` state.
   Poll at a reasonable interval — do not query the controller more than once per minute.
4. Read `results/metrics.json` and report the final `score`.
