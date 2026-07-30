#!/usr/bin/env python3
"""Bounded inference stand-in; performs no CUDA work."""

import argparse


parser = argparse.ArgumentParser()
parser.add_argument("--checkpoint", required=True)
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.parse_args()
print("inference fixture complete")
