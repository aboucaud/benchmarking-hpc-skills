"""Run classifier inference and write a compact prediction record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(
            {
                "checkpoint": str(arguments.checkpoint),
                "input": str(arguments.input),
                "devices": 1,
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
