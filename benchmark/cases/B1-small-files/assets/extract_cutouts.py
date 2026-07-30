#!/usr/bin/env python3
"""Bounded cutout extractor that never creates the nominal 500,000 files."""

import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--catalogue", required=True)
parser.add_argument("--outdir", required=True)
parser.add_argument("--one-file-per-source", action="store_true")
parser.add_argument("--chunk-size", type=int)
parser.add_argument("--shard-depth", type=int)
parser.add_argument("--workers", type=int, default=1)
args = parser.parse_args()

outdir = Path(args.outdir)
outdir.mkdir(parents=True, exist_ok=True)
(outdir / "fixture-manifest.json").write_text(
    json.dumps(
        {
            "catalogue": args.catalogue,
            "mode": "one-file-per-source" if args.one_file_per_source else "aggregated",
            "chunk_size": args.chunk_size,
            "shard_depth": args.shard_depth,
            "workers_requested": args.workers,
        }
    )
    + "\n"
)
