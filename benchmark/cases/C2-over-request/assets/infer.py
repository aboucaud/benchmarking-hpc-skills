"""Run the trained classifier over the validation set.

Placeholder: the inference backend is not shipped with this checkout. What it would use is fixed
in the constants below — one device, one data-loading worker.
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
