"""Materialize judged episode records into the results layout MySTRA reads.

    uv run --with pyyaml src/hpcbench/astra_results.py results/episodes-*.judged.jsonl

MySTRA never scans the results tree. It computes each artifact's location deterministically
from the output id declared in `astra.yaml`:

    benchmark/results/<universe-id>/<output-id>/<output-id>.<ext>

so this writes exactly that and nothing else. The prose in `benchmark/pages/` then pulls
numbers by reference instead of restating them.

Why this exists at all: this project has already been bitten once by a number read out of
its own report by eye — a case's marks were counted as ten when there were three. A report
that interpolates every value from the record it came from cannot make that mistake. That
is the whole argument for the MySTRA layer, so this script is deliberately the *only* place
results become prose-facing numbers.

Two rules it follows, both about not becoming a second source of truth:

1. **The endpoint is `report.endpoint_of`, imported, never reimplemented.** A second
   implementation of "did this episode prevent the defect" would drift from the harness's,
   and the published number would stop being the harness's number.

   Using `judge.combine` directly here was wrong and briefly produced a rate of 1.0. Under
   `--l1-pass-only` the L1 failures carry no L2 block, so `combine` returns `None` for them
   — "not scored on both layers" — and the denominator silently collapses to the L1 passes,
   nearly all of which passed L2. `endpoint_of` is the reporter's own reading: judged
   episodes use their endpoint block, unjudged L1 failures fall back to their L1 verdict,
   because an L1 failure is already a failure. That fallback is the difference between a
   published 100% and the real number.
2. **Nothing is aggregated that the harness reports separately.** Excluded, accidental and
   needs-review episodes travel as their own columns rather than being folded into a rate,
   because that separation is the finding, not presentation.

And one rule about what may be aggregated at all: **records that disagree about which
intervention they ran are not pooled.** This is the point where episodes stop being episodes
and become a published number, so it is the last point at which "these are two experiments"
can still be said. `--allow-mixed-intervention` exists for the case where someone genuinely
wants the pooled view, and it makes them say so in the command line.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

# The entry-point bootstrap used by every module here: run by path, with `src` on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hpcbench.harness.provenance import audit  # noqa: E402
from hpcbench.harness.report import endpoint_of, is_scoreable  # noqa: E402
from hpcbench.paths import BENCHMARK  # noqa: E402

RESULTS = BENCHMARK / "results"


def rows_from(records: list[dict]) -> list[dict]:
    """One row per (case, document arm, skills arm), aggregated over seeds.

    Seeds are replication, not a treatment: a cell is the set of seeds that ran it. The
    per-seed spread is kept as `unstable`, because a cell whose seeds disagree is the one
    fact about this benchmark that must never be averaged away — six of eighteen cells
    moved across seeds in an earlier run, which is what puts single-seed results below
    interpretability rather than merely low-powered.
    """
    cells: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for record in records:
        condition = record["condition"]
        doc = "present" if condition["doc"] else "absent"
        cells[(record["case"], doc, condition["skills"])].append(record)

    rows = []
    for (case, doc, skills), episodes in sorted(cells.items()):
        verdicts = [episode.get("endpoint") or {} for episode in episodes]
        prevented = [endpoint_of(episode) for episode in episodes]

        scored = [p for p in prevented if p is not None]
        passed = sum(1 for p in scored if p)
        # `unstable` asks whether the seeds in this cell agreed at all, which is a different
        # question from the rate: 1/3 and 2/3 are both unstable, 0/3 and 3/3 are not.
        unstable = len(set(scored)) > 1

        rows.append({
            "case": case,
            "family": episodes[0]["family"],
            "doc": doc,
            "skills": skills,
            "episodes": len(episodes),
            "scored": len(scored),
            "prevented": passed,
            "rate": round(passed / len(scored), 4) if scored else "",
            "unstable": int(unstable),
            "l1_pass": sum(1 for e in episodes if e["l1"].get("prevented")),
            "needs_review": sum(1 for p in prevented if p is None),
            "judged": sum(1 for e in episodes if "endpoint" in e),
            "fixed_by_accident": sum(1 for v in verdicts if v.get("fixed_by_accident")),
            "regression": sum(1 for v in verdicts if v.get("regression")),
            "excluded": sum(1 for e in episodes if not is_scoreable(e)),
            # Carried because the harness reports them separately, and for the same reason.
            # `norun` is the inaction failure mode: the defect was averted and the researcher
            # got no science, which is neither a pass nor a failure. `rejected` is scheduler
            # pushback, which explains the doc-absent arm better than the document does — any
            # rate quoted without it is quoting the scheduler.
            "norun": sum(
                1 for e in episodes
                if is_scoreable(e) and e.get("evidence")
                and not e["evidence"].get("workload_submitted")
                and not e["l1"].get("prevented_without_running")
            ),
            "rejected": sum(
                1 for e in episodes if (e.get("evidence") or {}).get("submissions_rejected")
            ),
        })
    return rows


def write_artifact(universe: str, output_id: str, suffix: str) -> Path:
    directory = RESULTS / universe / output_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{output_id}{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episodes", type=Path, help="a *.judged.jsonl from judge.py")
    parser.add_argument("--universe", default="full_matrix_stubs",
                        help="universe id; must match a file in benchmark/universes/")
    parser.add_argument("--focal-doc", default="present",
                        help="document arm the scalar metric summarises")
    parser.add_argument("--focal-skills", default="none")
    parser.add_argument("--allow-mixed-intervention", action="store_true",
                        help="publish anyway when the records disagree about which document or "
                             "skill bundle they ran against; the disagreement is still reported")
    args = parser.parse_args()

    records = [json.loads(line) for line in args.episodes.read_text().splitlines() if line.strip()]
    if not records:
        print(f"no records in {args.episodes}", file=sys.stderr)
        return 1

    # Before anything is aggregated. A rate over two interventions is not a rate over either, and
    # the labels cannot show it: #29's two documents both said `doc-present` for the whole pilot.
    provenance = audit(records)
    for problem in provenance.problems:
        print(f"mixed intervention — {problem}", file=sys.stderr)
    if provenance.problems and not args.allow_mixed_intervention:
        print("refusing to publish a pooled rate over more than one experiment; re-run per "
              "intervention, or pass --allow-mixed-intervention to publish it anyway",
              file=sys.stderr)
        return 1

    rows = rows_from(records)

    grid = write_artifact(args.universe, "per_case_grid", ".csv")
    with grid.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    focal = [r for r in rows if r["doc"] == args.focal_doc and r["skills"] == args.focal_skills]
    scored = sum(r["scored"] for r in focal)
    prevented = sum(r["prevented"] for r in focal)

    endpoint = write_artifact(args.universe, "prevented_rate", ".json")
    endpoint.write_text(json.dumps({
        "value": round(prevented / scored, 4) if scored else None,
        "unit": "fraction of scored episodes",
    }, indent=2) + "\n")

    # A second scalar, deliberately separate: the count of cells whose seeds disagreed.
    # Reported beside the rate rather than inside it.
    unstable = write_artifact(args.universe, "unstable_cells", ".json")
    unstable.write_text(json.dumps({
        "value": sum(r["unstable"] for r in rows),
        "unit": f"cells of {len(rows)} whose seeds disagreed",
    }, indent=2) + "\n")

    # Published beside the numbers, not merely checked before them.
    #
    # A universe file pins which *option* of each decision ran — `document: present`. It has no
    # way to say which document that was, and the option id stayed `present` across the rewrite
    # that changed the intervention (#29). This artifact is the missing half: the page that
    # quotes a rate can name the material the rate was measured on.
    manifest = write_artifact(args.universe, "intervention_manifest", ".json")
    manifest.write_text(json.dumps({
        "episodes": len(records),
        "stamped": provenance.stamped,
        # Named `unstamped`, and counted, because an absent stamp is unknown rather than
        # matching. A reader that treats missing as agreement gets a clean bill of health for
        # exactly the records that cannot support one.
        "unstamped": len(provenance.unstamped),
        "document_sha256": sorted(provenance.values["document_sha256"]),
        "skills_sha256": sorted(provenance.values["skills_sha256"]),
        # Keyed `<substrate>/<case>` because the value is only comparable within a substrate —
        # the two deliver `prompt.md` differently, so an unchanged case stamps two digests.
        "case_files_sha256": {
            f"{substrate}/{case}": sorted(seen)
            for (substrate, case), seen in sorted(provenance.case_files.items())
        },
        "mixed": provenance.problems,
    }, indent=2) + "\n")

    print(f"universe {args.universe}: {len(records)} episodes -> {len(rows)} cells")
    print(f"  {grid.relative_to(BENCHMARK.parent)}")
    print(f"  {endpoint.relative_to(BENCHMARK.parent)}  "
          f"({prevented}/{scored} in doc-{args.focal_doc} skills-{args.focal_skills})")
    print(f"  {unstable.relative_to(BENCHMARK.parent)}")
    print(f"  {manifest.relative_to(BENCHMARK.parent)}  "
          f"({provenance.stamped} stamped, {len(provenance.unstamped)} unstamped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
