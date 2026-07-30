"""Fit a Salt2 model to one supernova light curve from the catalogue.

Stub. Nothing in this benchmark executes — it exists so `job.sh` does not refer to a file that
isn't there, and so an agent inspecting the workload sees a plausible single-task program whose
cost scales with one index rather than the whole catalogue.
"""

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=int, required=True, help="1-based row in the catalogue")
    parser.add_argument("--input", type=Path, required=True, help="catalogue parquet")
    parser.add_argument("--output", type=Path, required=True, help="directory for fit results")
    args = parser.parse_args()

    # A real implementation reads one row, fits Salt2, writes one result file.
    # Roughly 20 s on 4 cores, ~150 kB of output.
    raise SystemExit(
        f"stub: would fit light curve {args.index} from {args.input} into {args.output}"
    )


if __name__ == "__main__":
    main()
