"""Build the summary plot from a finished catalogue fit.

Placeholder: the plotting backend is not shipped with this checkout. It reads every result file
the fit wrote, so it cannot produce anything until the fit has finished.
"""

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="directory of fit results")
    args = parser.parse_args()

    # A real implementation reads every result file and writes one figure. Seconds of work, and
    # it needs the fit to have finished first.
    raise SystemExit(f"stub: would summarise the fits in {args.input} into summary.png")


if __name__ == "__main__":
    main()
