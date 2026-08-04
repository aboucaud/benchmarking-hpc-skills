"""Train the photometric-redshift network, data-parallel across GPUs.

Placeholder: the training backend is not shipped with this checkout. The requirement it enforces
is real — there is no CPU code path, so `--devices` must be at least one.
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
