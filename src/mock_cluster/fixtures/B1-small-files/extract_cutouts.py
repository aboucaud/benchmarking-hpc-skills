"""Extract cutouts into indexed containers suitable for shared storage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    layout = parser.add_mutually_exclusive_group(required=True)
    layout.add_argument("--one-file-per-source", action="store_true")
    layout.add_argument("--chunk-size", type=int)
    layout.add_argument("--shard-depth", type=int)
    arguments = parser.parse_args()

    if arguments.one_file_per_source or arguments.shard_depth is not None:
        raise SystemExit(
            "per-source output is disabled on shared storage; use --chunk-size"
        )
    if not arguments.chunk_size or arguments.chunk_size < 1:
        raise SystemExit("--chunk-size must be positive")

    arguments.outdir.mkdir(parents=True, exist_ok=True)
    (arguments.outdir / "containers.index.json").write_text(
        json.dumps(
            {
                "catalogue": str(arguments.catalogue),
                "chunk_size": arguments.chunk_size,
                "workers": arguments.workers,
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
