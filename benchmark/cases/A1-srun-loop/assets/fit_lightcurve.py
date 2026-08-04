"""Fit a Salt2 model to one supernova light curve from the catalogue.

Placeholder: the Salt2 backend is not shipped with this checkout. The interface is the real one —
one catalogue row per invocation, selected by `--index`.
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
