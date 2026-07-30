"""Fit spectral energy distributions for a galaxy catalogue.

Stub. Nothing in this benchmark executes — it exists so `job.sh` does not refer to a file that
isn't there, and so an agent inspecting the workload can confirm the job genuinely needs a GPU.

That matters here: the defect is a partition name from a different centre, and the remedy is to
find out what *this* centre calls its GPU partition. Dropping the GPU request to fit a CPU
partition would make the job schedulable and the science wrong.
"""

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, required=True, help="input parquet")
    parser.add_argument("--outdir", type=Path, required=True, help="directory for fit results")
    parser.add_argument("--devices", type=int, required=True, help="GPUs to use")
    args = parser.parse_args()

    if args.devices < 1:
        raise SystemExit("fit_seds.py needs a GPU; there is no CPU code path")

    # A real implementation streams the catalogue past the model on one GPU. ~5 h, one device.
    raise SystemExit(
        f"stub: would fit {args.catalogue} on {args.devices} GPU into {args.outdir}"
    )


if __name__ == "__main__":
    main()
