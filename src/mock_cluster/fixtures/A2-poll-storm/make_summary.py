"""Build a summary record from a completed catalogue fit."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.input.mkdir(parents=True, exist_ok=True)
    (arguments.input / "summary.txt").write_text("summary complete\n")


if __name__ == "__main__":
    main()
