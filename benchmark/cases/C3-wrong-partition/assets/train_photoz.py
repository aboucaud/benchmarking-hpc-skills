"""Train the photometric-redshift network, data-parallel across GPUs.

Stub. Nothing in this benchmark executes — it exists so `job.sh` does not refer to a file that
isn't there, and so an agent inspecting the workload can confirm the job genuinely needs GPUs.
That matters for this case: the defect is the partition, not the request. An agent that "fixes"
the script by dropping `--devices` to fit a CPU-only partition has made the failure quieter
rather than fixing it, and this file is what makes that visible.
"""

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="training image directory")
    parser.add_argument("--devices", type=int, required=True, help="GPUs for data parallelism")
    parser.add_argument("--checkpoint-dir", type=Path, required=True, help="where to checkpoint")
    args = parser.parse_args()

    if args.devices < 1:
        raise SystemExit("train_photoz.py requires at least one GPU; there is no CPU code path")

    # A real implementation builds the model, wraps it for data parallelism across
    # args.devices GPUs, and trains for ~11 h, checkpointing each epoch.
    raise SystemExit(
        f"stub: would train on {args.input} across {args.devices} GPUs, "
        f"checkpointing to {args.checkpoint_dir}"
    )


if __name__ == "__main__":
    main()
