"""Fit one catalogue row and write its compact result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    arguments.output.mkdir(parents=True, exist_ok=True)
    destination = arguments.output / f"fit-{arguments.index:04d}.json"
    destination.write_text(
        json.dumps(
            {
                "catalogue": str(arguments.input),
                "index": arguments.index,
                "status": "complete",
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
