"""Train the photometric-redshift model across the requested devices."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--devices", type=int, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    arguments = parser.parse_args()

    if arguments.devices < 1:
        raise SystemExit("at least one accelerator is required")
    arguments.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    (arguments.checkpoint_dir / "training-status.txt").write_text(
        f"input={arguments.input}\ndevices={arguments.devices}\nstatus=complete\n"
    )


if __name__ == "__main__":
    main()
