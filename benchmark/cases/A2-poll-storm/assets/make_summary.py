#!/usr/bin/env python3
"""Bounded stand-in for summary generation."""

import argparse


parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.parse_args()
print("summary fixture complete")
