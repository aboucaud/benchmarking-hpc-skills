#!/usr/bin/env python3
"""Give this substrate's stored records the intervention stamp they can still support.

    uv run --with pyyaml src/mock_cluster/backfill.py results/<run>/episodes-*.jsonl

The stamp landed after these runs, so the 90 Docker records carry no `intervention` block. They
are not lost, though, and that is the whole point of this script: this substrate has written
`evidence.input_sha256` — a per-file hash of everything materialized into the workspace — since
PR #22, and the stamp is a roll-up of exactly that. The recovery is arithmetic on data already
in the file, not a re-run and not a guess.

**The echo stub's 108 records cannot be recovered and never will be.** Nothing hashed the
material while it existed, and the material has since changed twice (#29 rewrote the document,
and the fixture pass rewrote nine files the agent reads). Those records stay unstamped, the
audit keeps reporting them as unknown, and the honest statement about that matrix is that it
measured an experiment no checkout can reconstruct.

Two things this refuses to do:

  - **Write in place.** `results/` is append-only by convention, and a provenance record that
    silently rewrote the evidence it describes would be self-refuting. Output is a new file.
  - **Derive a stamp for anything but this substrate.** A record without `input_sha256` has
    nothing to derive from, and inventing `null` fields for it would convert "we cannot say"
    into a stamp that reads as "no document was given" — the exact confusion the audit's
    unstamped count exists to prevent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE.parent))

from mock_cluster.episode import intervention_from_digests  # noqa: E402

SUBSTRATE = "docker-slurm"


def backfill(records: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Return the records with `intervention` filled in where it can be, plus a tally.

    Never overwrites an existing stamp. A record written by a current harness already carries the
    stamp taken at materialization time, which is the primary evidence; recomputing it from the
    digests would replace a measurement with a derivation of one.
    """
    tally = {"stamped": 0, "already": 0, "no_digests": 0, "wrong_substrate": 0}
    output = []
    for record in records:
        result = dict(record)
        digests = (record.get("evidence") or {}).get("input_sha256")
        if record.get("intervention"):
            tally["already"] += 1
        elif record.get("substrate") != SUBSTRATE:
            tally["wrong_substrate"] += 1
        elif not isinstance(digests, dict) or not digests:
            tally["no_digests"] += 1
        else:
            result["intervention"] = intervention_from_digests(digests)
            tally["stamped"] += 1
        output.append(result)
    return output, tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("episodes", type=Path, help="a docker-slurm episodes*.jsonl")
    parser.add_argument("--out", type=Path, default=None,
                        help="output path; defaults to <input>.stamped.jsonl beside the input")
    arguments = parser.parse_args()

    records = [
        json.loads(line) for line in arguments.episodes.read_text().splitlines() if line.strip()
    ]
    if not records:
        print(f"no records in {arguments.episodes}", file=sys.stderr)
        return 1

    output, tally = backfill(records)
    destination = arguments.out or arguments.episodes.with_suffix(".stamped.jsonl")
    if destination.exists():
        print(f"{destination} exists; refusing to overwrite", file=sys.stderr)
        return 1
    destination.write_text("".join(json.dumps(record) + "\n" for record in output))

    print(f"{len(records)} records -> {destination}")
    print(f"  {tally['stamped']} stamped from evidence.input_sha256")
    for key, message in (
        ("already", "already stamped, left as written"),
        ("no_digests", "no input_sha256 to derive from — left unstamped"),
        ("wrong_substrate", f"not {SUBSTRATE} — left unstamped, nothing to derive from"),
    ):
        if tally[key]:
            print(f"  {tally[key]} {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
