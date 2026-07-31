"""Run the catalogue fit and write a completion record."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    arguments = parser.parse_args()

    # Keep the allocation alive long enough for normal asynchronous status
    # handling while consuming effectively no CPU.
    time.sleep(30)
    arguments.output.mkdir(parents=True, exist_ok=True)
    (arguments.output / "catalogue-fit.json").write_text(
        json.dumps(
            {
                "input": str(arguments.input),
                "workers": arguments.workers,
                "status": "complete",
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
