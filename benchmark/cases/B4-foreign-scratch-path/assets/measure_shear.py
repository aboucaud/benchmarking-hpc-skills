#!/usr/bin/env python3
"""Measure shear per tile and write one catalogue each. Stand-in for the real pipeline."""

import argparse
import pathlib

parser = argparse.ArgumentParser()
parser.add_argument("--tiles", required=True)
parser.add_argument("--exposures", required=True)
parser.add_argument("--output-dir", required=True)
arguments = parser.parse_args()

destination = pathlib.Path(arguments.output_dir)
destination.mkdir(parents=True, exist_ok=True)

for tile in pathlib.Path(arguments.tiles).read_text().split():
    (destination / f"{tile}_shear.fits").write_bytes(b"")
    print(f"wrote {tile}")
