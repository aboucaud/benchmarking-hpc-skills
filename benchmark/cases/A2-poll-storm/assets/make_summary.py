"""Build the summary plot from a finished catalogue fit.

Stub. Nothing in this benchmark executes — it exists so `job.sh` does not refer to a file that
isn't there, and because this one is reachable: it sits after the polling loop in a driver the
agent may well run. A stub keeps that harmless.

It also carries the reason the wait exists at all, which the case turns on. The remedy is to stop
busy-waiting, not to drop this step — an agent that deletes the summary to remove the loop has
silently dropped part of the workflow.
"""

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="directory of fit results")
    args = parser.parse_args()

    # A real implementation reads every result file and writes one figure. Seconds of work, and
    # it needs the fit to have finished — hence the dependency this case is about.
    raise SystemExit(f"stub: would summarise the fits in {args.input} into summary.png")


if __name__ == "__main__":
    main()
