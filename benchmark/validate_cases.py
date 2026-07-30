#!/usr/bin/env python3
"""Check the misuse cases are internally coherent and consistent with center.yaml.

    uv run --with pyyaml benchmark/validate_cases.py

This is *not* the L1 detector set. It verifies the properties the review gate depends on, so a
reviewer can spend their attention on whether a defect is realistic rather than on whether the
scaffolding is self-consistent:

  - every case has the required files
  - case.yaml declares provenance, a defect, detection signals, remedies and regressions
  - exactly one remedy is marked is_reference, and at least two are listed (a single accepted
    remedy is the likeliest route to false negatives)
  - reference.sh is valid against the declared cluster: real account, real partition, within that
    partition's limits, GPUs only where the partition has them
  - no script loads an undeclared module
  - only B2, where it is the defect, writes bulk output to $HOME

The doctored job.sh is deliberately *not* checked against the limits — violating something is its
purpose.

Becomes a pytest once the toolchain in PR #2 lands on main.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

BENCHMARK = Path(__file__).resolve().parent
REQUIRED_FILES = {"case.yaml", "job.sh", "prompt.md", "reference.sh", "rubric.md"}
REQUIRED_KEYS = (
    "family",
    "title",
    "provenance",
    "injected_defect",
    "detection",
    "accepted_remedies",
    "forbidden_regressions",
)


def sbatch_directives(text: str) -> dict[str, str]:
    """Extract #SBATCH long options from a script."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"#SBATCH\s+--([a-z-]+)(?:[= ](.*))?$", line.strip())
        if match:
            found[match.group(1)] = (match.group(2) or "").strip()
    return found


def to_hours(value: str) -> float:
    """Parse a Slurm HH:MM:SS walltime into hours."""
    parts = [int(part) for part in str(value).split(":")]
    parts += [0] * (3 - len(parts))
    return parts[0] + parts[1] / 60 + parts[2] / 3600


def check_reference_against_cluster(
    name: str, ref: str, partitions: dict[str, dict], account: str
) -> list[str]:
    """The reference remedy must be a script that would actually be accepted."""
    problems: list[str] = []
    directives = sbatch_directives(ref)
    if not directives:
        return problems  # driver script, not a batch script

    if "account" in directives and directives["account"] != account:
        problems.append(f"{name}: reference account {directives['account']!r} != {account!r}")

    partition = directives.get("partition")
    if partition and partition not in partitions:
        problems.append(f"{name}: reference partition {partition!r} not declared in center.yaml")
        return problems
    if not partition:
        return problems

    limits = partitions[partition]
    if "time" in directives and to_hours(directives["time"]) > to_hours(limits["max_time"]):
        problems.append(
            f"{name}: reference time {directives['time']} exceeds "
            f"{partition} maximum {limits['max_time']}"
        )
    if "nodes" in directives and int(directives["nodes"]) > limits["max_nodes"]:
        problems.append(
            f"{name}: reference nodes {directives['nodes']} exceeds "
            f"{partition} maximum {limits['max_nodes']}"
        )
    if directives.get("gres", "").startswith("gpu") and not limits["gpus"]:
        problems.append(f"{name}: reference requests GPUs on non-GPU partition {partition!r}")
    return problems


def check_case(directory: Path, partitions: dict[str, dict], account: str,
               modules: set[str]) -> tuple[list[str], str]:
    name = directory.name
    problems: list[str] = []

    missing = REQUIRED_FILES - {path.name for path in directory.iterdir()}
    if missing:
        return [f"{name}: missing {sorted(missing)}"], ""

    spec = yaml.safe_load((directory / "case.yaml").read_text())
    if spec.get("id") != name:
        problems.append(f"{name}: case.yaml id is {spec.get('id')!r}, expected {name!r}")
    problems += [f"{name}: case.yaml missing {key}" for key in REQUIRED_KEYS if not spec.get(key)]

    remedies = spec.get("accepted_remedies") or []
    references = sum(1 for remedy in remedies if remedy.get("is_reference"))
    if references != 1:
        problems.append(f"{name}: {references} remedies marked is_reference, expected exactly 1")
    if len(remedies) < 2:
        problems.append(
            f"{name}: only {len(remedies)} accepted remedy — judging an agent wrong for a "
            f"different valid fix is the likeliest false negative"
        )

    detection = spec.get("detection") or {}
    declared = sorted(set(detection) & {"static", "call_log"})
    if not declared:
        problems.append(f"{name}: detection declares neither static nor call_log")

    reference = (directory / "reference.sh").read_text()
    job = (directory / "job.sh").read_text()
    problems += check_reference_against_cluster(name, reference, partitions, account)

    for text, label in ((reference, "reference.sh"), (job, "job.sh")):
        for module in re.findall(r"module load (\S+)", text):
            if module not in modules:
                problems.append(f"{name}: {label} loads undeclared module {module!r}")

    if "$HOME" in reference:
        problems.append(f"{name}: reference.sh writes to $HOME")
    if name != "B2-home-output" and re.search(r"OUTDIR=\$HOME", job):
        problems.append(f"{name}: job.sh writes output to $HOME but is not the B2 case")

    summary = (
        f"  {name:26s} family {spec.get('family')}  remedies {len(remedies)}  "
        f"regressions {len(spec.get('forbidden_regressions') or [])}  "
        f"detect {'+'.join(declared)}"
    )
    return problems, summary


def main() -> int:
    center = yaml.safe_load((BENCHMARK / "center.yaml").read_text())
    partitions = {partition["name"]: partition for partition in center["partitions"]}
    account = center["account"]["name"]
    modules = set(center["modules"])

    directories = sorted(path for path in (BENCHMARK / "cases").iterdir() if path.is_dir())
    print(f"checking {len(directories)} cases against center.yaml\n")

    problems: list[str] = []
    for directory in directories:
        case_problems, summary = check_case(directory, partitions, account, modules)
        problems += case_problems
        if summary:
            print(summary)

    print()
    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("all cases consistent with center.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
