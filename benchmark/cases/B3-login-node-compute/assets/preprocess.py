#!/usr/bin/env python3
"""Bounded preprocessing stand-in."""

import argparse


parser = argparse.ArgumentParser()
parser.add_argument("--raw", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--workers", required=True, type=int)
args = parser.parse_args()
print(f"preprocessing fixture requested {args.workers} workers")
