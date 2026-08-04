"""Extract fixed-size cutouts around catalogue sources.

Placeholder: the cutout backend is not shipped with this checkout. The output layout is selected
on the command line; the options below are the ones it supports.
"""

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)

    layout = parser.add_mutually_exclusive_group()
    layout.add_argument(
        "--one-file-per-source",
        action="store_true",
        help="one ~120 kB FITS file per source, flat in --outdir",
    )
    layout.add_argument(
        "--chunk-size",
        type=int,
        help="aggregate cutouts into one HDF5 container per CHUNK_SIZE sources, "
        "with an index table mapping source id to container and offset",
    )
    layout.add_argument(
        "--shard-depth",
        type=int,
        help="one file per source, sharded across SHARD_DEPTH levels of subdirectory",
    )

    args = parser.parse_args()
    raise SystemExit(f"stub: would extract cutouts from {args.catalogue} into {args.outdir}")


if __name__ == "__main__":
    main()
