#!/usr/bin/env python3
"""Bounded stand-in for one light-curve fit."""

import argparse


parser = argparse.ArgumentParser()
parser.add_argument("--index", required=True, type=int)
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
print(f"validated light-curve fit {args.index}")
