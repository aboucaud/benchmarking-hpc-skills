"""Run the trained classifier over the validation set.

Stub. Nothing in this benchmark executes — it exists so `job.sh` does not refer to a file that
isn't there, and so an agent inspecting the workload can confirm from the code what the script's
own comment says: one device, one data-loading worker. The resource request in `job.sh` asks for
four GPUs and 64 cores. The discrepancy is the case.
"""

import argparse
from pathlib import Path

DEVICES = 1  # the model does not shard; inference runs on a single GPU
DATALOADER_WORKERS = 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True, help="trained weights")
    parser.add_argument("--input", type=Path, required=True, help="validation image directory")
    parser.add_argument("--output", type=Path, required=True, help="predictions parquet")
    args = parser.parse_args()

    # A real implementation loads the checkpoint onto one device and streams the validation set
    # past it. Roughly 2 h wall-clock, one GPU at ~80% utilisation, one core for the loader.
    raise SystemExit(
        f"stub: would run {args.checkpoint} over {args.input} on {DEVICES} device "
        f"with {DATALOADER_WORKERS} loader worker, writing {args.output}"
    )


if __name__ == "__main__":
    main()
