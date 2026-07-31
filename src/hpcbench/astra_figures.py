"""One audit figure per case, written where MySTRA resolves it.

    uv run --with matplotlib src/hpcbench/astra_figures.py

Reads `benchmark/results/<universe>/per_case_grid/per_case_grid.csv` — the artifact
`astra_results.py` already produced — and writes one SVG per case to

    benchmark/results/<universe>/<case-output-id>/<case-output-id>.svg

so each case can be embedded in the report by reference and read on its own.

The figure is built for *auditing*, not for looking impressive, which drives three choices:

**The four condition rows are always drawn, in a fixed order.** A missing cell is drawn as
an empty row rather than skipped, because a silently absent condition and a condition that
scored zero look identical once a row disappears.

**The denominator is drawn, not just the rate.** Every bar is annotated `k/n`, and `n` is
the number of episodes that could be *scored*, which is not always the number that ran. A
bar at "100%" over one scored episode is not the same claim as one over three, and a
proportion alone cannot tell you which you are looking at.

**The stratifiers sit next to the bar, never inside it.** `unstable`, `norun` and
`rejected` each describe a different reason a rate may not mean what it appears to, and
each is the kind of thing that gets averaged away the moment it is folded into a single
number:

- `unstable` — the seeds in this cell disagreed with each other.
- `norun`    — the agent submitted nothing; the defect was averted and no science happened.
- `rejected` — the scheduler pushed back, so the agent may have learned from the rejection
               rather than from the intervention under test.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hpcbench.paths import BENCHMARK  # noqa: E402

RESULTS = BENCHMARK / "results"

# Fixed order, always drawn. Index 0 is the reference arm: no document, no skills.
CONDITIONS = [
    ("absent", "none", "no doc · no skills"),
    ("absent", "good", "no doc · skills"),
    ("present", "none", "doc · no skills"),
    ("present", "good", "doc · skills"),
]

INK = "#1d2433"
MUTED = "#6b7688"
BAR_BG = "#e6e9ef"
BAR = "#3f7f5f"
BAR_ZERO = "#c2c8d2"
FLAG = "#b3541e"


def output_id(case: str) -> str:
    """`A1-srun-loop` -> `case_a1_srun_loop`, the ASTRA output id and the artifact dir."""
    return "case_" + case.lower().replace("-", "_")


def draw(case: str, rows: list[dict], path: Path) -> None:
    # Imported here, not at module scope: `output_id` is a pure string helper the test suite
    # and the report both need, and requiring a plotting library to ask what a case's output
    # id is would put matplotlib into CI for no reason.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    by_condition = {(r["doc"], r["skills"]): r for r in rows}
    family = rows[0]["family"]

    figure, axes = plt.subplots(figsize=(7.6, 3.0))
    axes.set_xlim(0, 1.34)
    axes.set_ylim(-0.7, len(CONDITIONS) - 0.3)
    axes.invert_yaxis()
    axes.axis("off")

    axes.text(0, -0.62, case, fontsize=12.5, fontweight="bold", color=INK, family="DejaVu Sans")
    axes.text(0.42, -0.62, f"family {family}", fontsize=9, color=MUTED, family="DejaVu Sans")

    for index, (doc, skills, label) in enumerate(CONDITIONS):
        row = by_condition.get((doc, skills))
        axes.text(-0.02, index, label, fontsize=8.5, color=MUTED, ha="right", va="center",
                  family="DejaVu Sans")

        # The track is drawn for every condition, present or not.
        axes.add_patch(Rectangle((0, index - 0.22), 1.0, 0.44, color=BAR_BG, zorder=1))

        if row is None:
            axes.text(0.5, index, "not run", fontsize=8, color=MUTED, ha="center", va="center",
                      style="italic", zorder=3, family="DejaVu Sans")
            continue

        scored, prevented = int(row["scored"]), int(row["prevented"])
        if scored:
            fraction = prevented / scored
            axes.add_patch(Rectangle((0, index - 0.22), max(fraction, 0.004), 0.44,
                                     color=BAR if prevented else BAR_ZERO, zorder=2))
            axes.text(1.04, index, f"{prevented}/{scored}", fontsize=9, color=INK,
                      va="center", family="DejaVu Sans")
        else:
            # Nothing scoreable. Distinct from 0/n, and it must not read as a zero bar.
            axes.text(0.5, index, "nothing scored", fontsize=8, color=FLAG, ha="center",
                      va="center", zorder=3, family="DejaVu Sans")
            axes.text(1.04, index, f"0/{row['episodes']}", fontsize=9, color=MUTED,
                      va="center", family="DejaVu Sans")

        flags = []
        if int(row["unstable"]):
            flags.append("seeds disagree")
        if int(row["norun"]):
            flags.append(f"{row['norun']}x submitted nothing")
        if int(row["rejected"]):
            flags.append(f"{row['rejected']}x scheduler rejected")
        if int(row["needs_review"]):
            flags.append(f"{row['needs_review']}x needs review")
        if flags:
            axes.text(1.19, index, " · ".join(flags), fontsize=7.2, color=FLAG, va="center",
                      family="DejaVu Sans")

    figure.subplots_adjust(left=0.17, right=0.995, top=0.97, bottom=0.03)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Format follows the suffix: SVG for the site, PNG when someone wants a slide.
    figure.savefig(path, format=path.suffix.lstrip("."), bbox_inches="tight",
                   transparent=path.suffix == ".svg")
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="active_full_matrix")
    args = parser.parse_args()

    grid = RESULTS / args.universe / "per_case_grid" / "per_case_grid.csv"
    if not grid.exists():
        print(f"no grid at {grid} — run astra_results.py first", file=sys.stderr)
        return 1

    rows = list(csv.DictReader(grid.open()))
    cases: dict[str, list[dict]] = {}
    for row in rows:
        cases.setdefault(row["case"], []).append(row)

    for case, case_rows in sorted(cases.items()):
        name = output_id(case)
        draw(case, case_rows, RESULTS / args.universe / name / f"{name}.svg")
        print(f"  {name}.svg")

    print(f"{len(cases)} case figures under {RESULTS / args.universe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
