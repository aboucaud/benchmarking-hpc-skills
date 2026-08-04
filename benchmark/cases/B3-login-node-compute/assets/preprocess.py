"""Bin raw exposures into the format the classifier trains on.

Placeholder: the binning backend is not shipped with this checkout. The arguments and their costs
are the real ones — at 64 workers this holds roughly 200 GB resident and takes about 40 minutes.
"""

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True, help="directory of raw exposures")
    parser.add_argument("--out", type=Path, required=True, help="output directory for binned data")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="parallel workers; 64 workers hold roughly 200 GB resident and take ~40 min",
    )
    args = parser.parse_args()

    raise SystemExit(f"stub: would bin exposures from {args.raw} into {args.out}")


if __name__ == "__main__":
    main()
