"""Prepare raw classifier exposures for training."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    arguments = parser.parse_args()

    # The installed command keeps this development dataset bounded. Placement
    # must still follow the center's compute-node policy.
    time.sleep(2)
    arguments.out.mkdir(parents=True, exist_ok=True)
    (arguments.out / "manifest.json").write_text(
        json.dumps(
            {
                "raw": str(arguments.raw),
                "workers": arguments.workers,
                "status": "complete",
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
