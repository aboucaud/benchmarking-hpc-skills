#!/usr/bin/env python3
"""Bounded training stand-in; performs no CUDA work."""

import argparse


parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--devices", required=True, type=int)
parser.add_argument("--checkpoint-dir", required=True)
args = parser.parse_args()
print(f"training fixture requested {args.devices} devices")
