#!/usr/bin/env python3
"""One self-contained HTML page, for showing this work to people who were not in the room.

    uv run --with pyyaml python -m hpcbench.harness.report_html <episodes.jsonl> [more.jsonl] \
        --out report.html [--title "..."]

`report.py` prints the same measurement as text for someone who already knows the protocol. This
writes the version you send to another group — where the reader has to be given the caveats before
they are given a number, and where "what actually happened in this cell" has to be reachable
without opening a JSONL.

## The numbers are not recomputed here

`endpoint_of`, `cell_marks` and `CONDITION_ORDER` are imported from `report.py` rather than
reimplemented. Two report generators quietly disagreeing about what counts as *scored* is the
easiest way for a pretty page to be wrong, and the failure would be invisible — both outputs look
authoritative. Anything this module counts, `report.py` counts the same way, by construction.

## What the page is built to prevent

**Reading a number without its caveats.** The provenance band is the first thing on the page, not a
footer: episode count, subject model, judge and prompt version, spend, how many cases lack sysadmin
sign-off, whether L2 coverage is partial. Every section that carries a number restates the caveat
that binds it, in the same block.

**Mistaking one seed for a result.** Stability is the load-bearing encoding in the grid, and it is
carried three ways that are not colour: the per-seed dot strip (filled / hollow), an explicit
`flips` chip, and a stability column in the table view. At one seed a cell and a coin flip look
identical — so a one-seed cell renders as exactly one dot, which is the honest picture.

**Reading the richest arm as good conduct.** A cell containing episodes that submitted nothing says
so on its face. The defect averted because no work was done is not the same result as the defect
repaired, and folding the two together is the specific way this benchmark could flatter an
intervention.

## What is deliberately *not* here

The `was the agent pushed back on?` stratification that `report.py` still prints. Rejection at
submission is a property of the *case* — C1 and C3 are always rejected, six cases never are — so
splitting on it is a between-case comparison confounded with case difficulty, not a within-case
effect. Submission rejections appear in the per-case detail as a plain descriptive count, which is
what survives.

## Design of the visuals

Built against the `dataviz` skill. The choices it forced, recorded so they can be argued with:

- **The grid is a heatmap**, so its colour job is *sequential* — one blue hue, light→dark, the
  lightest step meaning "near zero" and receding toward the surface. Every tile prints its own
  `k/n`, and every value is in the table view, so no value is gated on the fill.
- **The arm comparison is a bar chart only when there is more than one arm to compare.** With a
  single arm it is a stat tile, because a one-bar bar chart is a stat tile wearing a costume.
- **Family is the only categorical set on the page** (three slots, validated all-pairs in both
  modes), and it is always paired with the family name in text — never colour alone.
- **Marks and outcome chips carry no colour at all.** `idle` / `norun` / `acc` / `rev` are states,
  not series and not status; giving them hues would spend the identity channel on a legend nobody
  needs and would let a chip impersonate a status.
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from math import comb
from pathlib import Path

import yaml

if __package__ in (None, ""):  # invoked as a script rather than imported
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hpcbench.harness.report import (  # noqa: E402
    CONDITION_ORDER,
    cell_marks,
    endpoint_of,
    is_scoreable,
)
from hpcbench.paths import CASES  # noqa: E402

# ------------------------------------------------------------------------------------------
# Arm names, for a reader who was not in the room
# ------------------------------------------------------------------------------------------
#
# The record labels (`doc-present_skills-good`) are internal shorthand and read as jargon on a
# slide. Two things about them mislead an outside reader specifically:
#
#   `doc-present` / `doc-absent` — "doc" is the centre-hosted `INSTRUCTIONS.md`. Absent/present
#   sounds like a property of the run; it is the intervention being tested, so it is named for
#   what it is: with or without the site's instructions.
#
#   `skills-good` — `skills` is a bundle *tier* name, and the design leaves room for a tier that
#   is deliberately poor (does a bad skill hurt?). No such arm has ever been run: every episode
#   to date is `none` or `good`, so on this page the axis is binary and "good" is a quality claim
#   with nothing to contrast against. Shown as with/without the skill. The tier machinery stays
#   in the harness — when a second tier is actually run, this mapping is where it surfaces.
#
# Display only. The record label is what the tooltip, the per-case detail and the table view
# carry, so anything on this page can still be traced back to a row in the JSONL.
CONDITION_DISPLAY = {
    "doc-absent_skills-none": ("no instructions", "no skill"),
    "doc-absent_skills-good": ("no instructions", "+ skill"),
    "doc-present_skills-none": ("instructions", "no skill"),
    "doc-present_skills-good": ("instructions", "+ skill"),
}


def condition_name(label: str) -> tuple[str, str]:
    """(document arm, skill arm) for display. Unknown labels fall back to the raw shorthand."""
    if label in CONDITION_DISPLAY:
        return CONDITION_DISPLAY[label]
    doc, _, skills = label.partition("_")
    return (doc.replace("doc-", ""), skills.replace("skills-", ""))


def condition_line(label: str) -> str:
    """The arm on one line, for places too narrow for a stacked column head."""
    doc, skill = condition_name(label)
    return f"{doc} {skill}" if skill.startswith("+") else f"{doc}, {skill}"

# ------------------------------------------------------------------------------------------
# Palette — every value from the dataviz skill's reference instance (references/palette.md).
# Nothing here is eyeballed; the validator runs recorded in the module docstring of the tests.
# ------------------------------------------------------------------------------------------

# Sequential blue ramp for the grid, six bins, light→dark. Validated: lightness monotone and
# adjacent ΔL ≥ 0.06 in both modes (`--ordinal`). The `--ordinal` light-end contrast check FAILs
# by design on both ramps — this is a *sequential* encoding, where palette.md allows the lightest
# step to recede toward the surface. The check that matters for a tile with text in it is the
# text's contrast against its own fill, computed per bin below: every bin clears 4.5:1.
HEAT_LIGHT = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#1c5cab", "#0d366b"]
HEAT_LIGHT_INK = ["#0b0b0b", "#0b0b0b", "#0b0b0b", "#0b0b0b", "#ffffff", "#ffffff"]
HEAT_DARK = ["#104281", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"]
HEAT_DARK_INK = ["#ffffff", "#ffffff", "#0b0b0b", "#0b0b0b", "#0b0b0b", "#0b0b0b"]

# Categorical, three slots (families A/B/C), validated `--pairs all` in both modes.
FAMILY_LIGHT = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}
FAMILY_DARK = {"A": "#3987e5", "B": "#d95926", "C": "#199e70"}

Z95 = 1.959963984540054

# `endpoint_of` is tri-state and the third state is not a failure — an episode that was never
# scored must never be rendered as one that was scored and lost.
VERDICT_TEXT = {True: "prevented", False: "not prevented", None: "not scored"}


def seed_key(episode: dict) -> int:
    """Sort key that keeps a seedless record first instead of raising on `None`."""
    seed = episode.get("seed")
    return -1 if seed is None else int(seed)


def family_of(meta: dict, case_id: str) -> str:
    """The family letter, escaped — it is interpolated into a CSS custom-property name."""
    return e(meta.get("family") or case_id[:1])


# ------------------------------------------------------------------------------------------
# Loading
# ------------------------------------------------------------------------------------------


def load(patterns: list[str]) -> tuple[list[dict], list[str]]:
    """Episodes, plus a note for anything that would not parse.

    The harness writes the episode file incrementally, one JSON object per line, so a run that is
    still going — or that was killed — leaves a final line that is half an object. `report.py`
    raises on it. A report that cannot open a partial run is a report you cannot use while the run
    is the thing you want to look at, so undecodable lines are skipped and *counted on the page*.
    Silently dropping them would be worse than crashing.
    """
    episodes: list[dict] = []
    notes: list[str] = []
    matched: list[str] = []
    for pattern in patterns:
        hits = sorted(glob.glob(pattern))
        matched.extend(hits or [])
        if not hits and Path(pattern).exists():
            matched.append(pattern)
    for path in matched:
        skipped = 0
        for line in Path(path).read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                episodes.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
        if skipped:
            notes.append(
                f"{Path(path).name}: {skipped} line(s) would not parse and were skipped — "
                f"expected while a run is still writing, and a reason to treat this render as "
                f"a partial view."
            )
    return episodes, notes


def load_cases() -> dict[str, dict]:
    """Case metadata from `benchmark/cases/*/case.yaml`.

    Withheld from the agent under test, fine in a report: without the injected defect written out,
    a reader cannot tell whether a case is measuring anything.
    """
    cases: dict[str, dict] = {}
    if not CASES.exists():
        return cases
    for path in sorted(CASES.glob("*/case.yaml")):
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        cases[data.get("id") or path.parent.name] = data
    return cases


# ------------------------------------------------------------------------------------------
# Statistics — computed, never asserted
# ------------------------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95% Wilson score interval. Generous here, and labelled as such where it is drawn."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact on a 2x2 table, by summing hypergeometric tails no more likely
    than the observed one. Pure stdlib; no scipy in this project's dependency list."""
    total = a + b + c + d
    if total == 0:
        return 1.0
    row1, col1 = a + b, a + c
    if row1 in (0, total) or col1 in (0, total):
        return 1.0

    def probability(x: int) -> float:
        return comb(row1, x) * comb(total - row1, col1 - x) / comb(total, col1)

    observed = probability(a)
    low, high = max(0, col1 - (total - row1)), min(row1, col1)
    return min(
        1.0,
        sum(
            probability(x)
            for x in range(low, high + 1)
            if probability(x) <= observed * (1 + 1e-9)
        ),
    )


# ------------------------------------------------------------------------------------------
# Cell assembly
# ------------------------------------------------------------------------------------------


def cell_stats(group: list[dict]) -> dict:
    """One (case, condition) cell. `scored`/`passed`/`unstable` follow `report.py` exactly."""
    scored = [episode for episode in group if endpoint_of(episode) is not None]
    passed = sum(1 for episode in scored if endpoint_of(episode))
    unstable = bool(scored) and passed not in (0, len(scored))

    tally: dict[str, int] = {}
    for episode in group:
        for mark in cell_marks(episode):
            tally[mark] = tally.get(mark, 0) + 1

    seeds = []
    for episode in sorted(group, key=lambda x: seed_key(x)):
        seeds.append(
            {
                "seed": episode.get("seed"),
                "verdict": endpoint_of(episode),
                "marks": cell_marks(episode),
                "judged": "endpoint" in episode,
                "rejected": (episode.get("evidence") or {}).get("submissions_rejected", 0),
                "validity": episode.get("validity"),
            }
        )

    nothing_submitted = sum(
        1
        for episode in group
        if is_scoreable(episode)
        and episode.get("evidence")
        and not episode["evidence"].get("workload_submitted")
    )

    return {
        "episodes": group,
        "n_total": len(group),
        "n_scored": len(scored),
        "passed": passed,
        "unstable": unstable,
        "marks": tally,
        "seeds": seeds,
        "nothing_submitted": nothing_submitted,
        "rejected": sum((e.get("evidence") or {}).get("submissions_rejected", 0) for e in group),
        "judged": sum(1 for e in group if "endpoint" in e),
    }


def heat_bin(passed: int, scored: int) -> int:
    """Six bins over the prevented rate; 0 is its own bin, so `0/n` never shares a step with
    `1/n` — the difference between "never" and "once" is the one a reader must not miss."""
    if scored == 0:
        return 0
    if passed == 0:
        return 0
    return max(1, min(5, math.ceil(passed / scored * 5)))


# ------------------------------------------------------------------------------------------
# HTML helpers
# ------------------------------------------------------------------------------------------


def e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def chip(text: str, kind: str = "") -> str:
    return f'<span class="chip {kind}">{e(text)}</span>'


def dot_strip(seeds: list[dict]) -> str:
    """Per-seed outcome, encoded by shape, never by colour.

    Filled disc = prevented, hollow ring = not, dash = present but not scored. This is the piece
    that makes a one-seed cell look like a one-seed cell: it renders as a single dot, and no
    reader can mistake it for five.
    """
    pieces = []
    for entry in seeds:
        verdict = entry["verdict"]
        if verdict is True:
            cls, label = "dot dot-on", f"seed {entry['seed']}: prevented"
        elif verdict is False:
            cls, label = "dot dot-off", f"seed {entry['seed']}: not prevented"
        else:
            cls, label = "dot dot-none", f"seed {entry['seed']}: not scored"
        pieces.append(f'<span class="{cls}" title="{e(label)}"></span>')
    return f'<span class="dots">{"".join(pieces)}</span>'


# ------------------------------------------------------------------------------------------
# CSS — assembled by concatenation so the dark declarations are written once and used twice
# (the media query for the OS setting, the attribute scope for the page's own toggle).
# ------------------------------------------------------------------------------------------


def _vars(mode: str) -> str:
    heat = HEAT_LIGHT if mode == "light" else HEAT_DARK
    ink = HEAT_LIGHT_INK if mode == "light" else HEAT_DARK_INK
    families = FAMILY_LIGHT if mode == "light" else FAMILY_DARK
    if mode == "light":
        base = """
  color-scheme: light;
  --plane: #f9f9f7;
  --surface-1: #fcfcfb;
  --surface-2: #f2f1ed;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #898781;
  --grid-line: #e1e0d9;
  --axis: #c3c2b7;
  --border: rgba(11,11,11,0.10);
  --series-1: #2a78d6;
  --track: #cde2fb;
"""
    else:
        base = """
  color-scheme: dark;
  --plane: #0d0d0d;
  --surface-1: #1a1a19;
  --surface-2: #232322;
  --text-primary: #ffffff;
  --text-secondary: #c3c2b7;
  --text-muted: #898781;
  --grid-line: #2c2c2a;
  --axis: #383835;
  --border: rgba(255,255,255,0.10);
  --series-1: #3987e5;
  --track: #104281;
"""
    lines = [base.rstrip("\n")]
    for index, (background, foreground) in enumerate(zip(heat, ink, strict=True)):
        lines.append(f"  --heat-{index}-bg: {background};")
        lines.append(f"  --heat-{index}-fg: {foreground};")
    for family, colour in families.items():
        lines.append(f"  --family-{family}: {colour};")
    # Status palette is fixed — never themed. Always shipped with an icon and a label.
    lines.append("  --status-good: #0ca30c;")
    lines.append("  --status-warning: #fab219;")
    lines.append("  --status-serious: #ec835a;")
    lines.append("  --status-critical: #d03b3b;")
    return "\n".join(lines) + "\n"


def build_css() -> str:
    dark = _vars("dark")
    return (
        ".viz-root {\n" + _vars("light") + "}\n"
        '@media (prefers-color-scheme: dark) {\n'
        '  :root:where(:not([data-theme="light"])) .viz-root {\n' + dark + "  }\n}\n"
        ':root[data-theme="dark"] .viz-root {\n' + dark + "}\n"
        + STATIC_CSS
    )


STATIC_CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
.viz-root {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--plane);
  color: var(--text-primary);
  line-height: 1.55;
  font-size: 15px;
  padding: 24px 20px 72px;
  min-height: 100vh;
}
.wrap { max-width: 1180px; margin: 0 auto; }
h1 { font-size: 27px; font-weight: 600; margin: 0 0 6px; letter-spacing: -0.01em; }
h2 { font-size: 19px; font-weight: 600; margin: 0 0 4px; letter-spacing: -0.005em; }
h3 { font-size: 15px; font-weight: 600; margin: 0 0 4px; }
p { margin: 0 0 10px; }
a { color: var(--series-1); }
.lede { color: var(--text-secondary); max-width: 74ch; margin-bottom: 4px; }
.muted { color: var(--text-muted); }
.small { font-size: 13px; }
.tiny { font-size: 12px; }
section { margin-top: 34px; }
.card {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 18px 16px;
}
.sec-head { margin-bottom: 12px; }
.sec-head .caveat-line {
  color: var(--text-secondary); font-size: 13px; max-width: 88ch; margin-top: 4px;
}
.topbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
button.theme {
  font: inherit; font-size: 13px; cursor: pointer; white-space: nowrap;
  background: var(--surface-1); color: var(--text-secondary);
  border: 1px solid var(--border); border-radius: 999px; padding: 5px 13px;
}
button.theme:hover { color: var(--text-primary); }

/* ---- provenance & caveats ------------------------------------------------------------- */
.prov { display: grid; grid-template-columns: repeat(auto-fit, minmax(178px, 1fr)); gap: 1px;
        background: var(--border); border: 1px solid var(--border); border-radius: 10px;
        overflow: hidden; margin-top: 14px; }
.prov > div { background: var(--surface-1); padding: 12px 14px; }
.prov dt { font-size: 12px; color: var(--text-muted); margin: 0 0 3px; }
.prov dd { margin: 0; font-size: 16px; font-weight: 600; }
.prov dd .unit { font-weight: 400; font-size: 13px; color: var(--text-secondary); }
.caveats { margin-top: 14px; display: flex; flex-direction: column; gap: 8px; }
.caveat {
  display: flex; gap: 10px; align-items: flex-start;
  background: var(--surface-1); border: 1px solid var(--border);
  border-left: 3px solid var(--edge, var(--axis));
  border-radius: 8px; padding: 10px 13px; font-size: 13.5px;
}
.caveat .ic { flex: 0 0 auto; font-weight: 700; font-size: 12px; letter-spacing: .04em;
  text-transform: uppercase; color: var(--text-secondary); min-width: 74px; }
.caveat b { font-weight: 600; }
.c-critical { --edge: var(--status-critical); }
.c-serious  { --edge: var(--status-serious); }
.c-warning  { --edge: var(--status-warning); }
.c-good     { --edge: var(--status-good); }

/* ---- grid ---------------------------------------------------------------------------- */
.scroll { overflow-x: auto; }
table.grid { border-collapse: separate; border-spacing: 2px; width: 100%; min-width: 780px; }
table.grid th { font-weight: 600; font-size: 12.5px; color: var(--text-secondary);
  text-align: center; padding: 0 4px 6px; vertical-align: bottom; }
table.grid th.rowhead { text-align: left; width: 246px; padding-right: 12px; }
/* Column head: the intervention in words, the record label underneath so the column can still
   be traced back to a row in the JSONL. */
.arm-doc { display: block; font-size: 13px; color: var(--text-primary); }
.arm-skill { display: block; font-weight: 500; }
.arm-raw { display: block; font-size: 10px; font-weight: 400; color: var(--text-muted);
  margin-top: 3px; }

/* ---- grid key -------------------------------------------------------------------------
   A key for reading one cell, and a colour legend. What the benchmark IS lives on the project
   page; the link to it sits in the lede. */
.method { white-space: nowrap; }
.cellkey { margin: 0 0 12px; font-size: 12.5px; line-height: 1.55;
  color: var(--text-secondary); max-width: 96ch; }
.cellkey code { font-size: 11.5px; }
.famkey { margin: 0 0 16px; }
.famkey dl { display: flex; flex-wrap: wrap; gap: 8px 24px; margin: 0; }
.fam-row { display: flex; gap: 8px; align-items: baseline; }
.fam-row > div { display: flex; gap: 6px; align-items: baseline; }
.famkey dt { font-weight: 600; font-size: 12.5px; }
.famkey dd { margin: 0; font-size: 12px; line-height: 1.5; color: var(--text-secondary); }
.fam-cases { color: var(--text-muted); font-size: 11px; }
table.grid td.rowhead {
  text-align: left; padding: 6px 12px 6px 0; font-size: 13px; vertical-align: middle;
  background: transparent;
}
.case-id { font-weight: 600; display: flex; align-items: center; gap: 7px; }
.fam-dot { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto;
  background: var(--fam, var(--axis)); }
/* block, not inline: an inline span applies padding-left only to its first line box, so a
   wrapped family/severity line loses its indent and hangs under the family dot. */
.case-sub { display: block; color: var(--text-muted); font-size: 11.5px; padding-left: 16px; }
td.cell {
  border-radius: 6px; padding: 8px 6px 7px; text-align: center; vertical-align: middle;
  background: var(--heat-0-bg); color: var(--heat-0-fg); cursor: default; min-width: 128px;
}
td.cell:focus-visible { outline: 2px solid var(--text-primary); outline-offset: 2px; }
td.cell.b0 { background: var(--heat-0-bg); color: var(--heat-0-fg); }
td.cell.b1 { background: var(--heat-1-bg); color: var(--heat-1-fg); }
td.cell.b2 { background: var(--heat-2-bg); color: var(--heat-2-fg); }
td.cell.b3 { background: var(--heat-3-bg); color: var(--heat-3-fg); }
td.cell.b4 { background: var(--heat-4-bg); color: var(--heat-4-fg); }
td.cell.b5 { background: var(--heat-5-bg); color: var(--heat-5-fg); }
td.cell.empty { background: var(--surface-2); color: var(--text-muted); }
.kn { display: block; font-size: 17px; font-weight: 600; font-variant-numeric: tabular-nums;
  line-height: 1.15; }
.dots { display: inline-flex; gap: 3px; margin-top: 5px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-on { background: currentColor; }
.dot-off { background: transparent; box-shadow: inset 0 0 0 1.5px currentColor; opacity: .8; }
.dot-none { width: 8px; height: 2px; border-radius: 1px; background: currentColor;
  opacity: .45; align-self: center; }
.cellchips { display: flex; flex-wrap: wrap; gap: 3px; justify-content: center; margin-top: 5px; }
.chip {
  display: inline-block; font-size: 10.5px; line-height: 1.5; padding: 0 6px;
  border-radius: 999px; border: 1px solid currentColor; opacity: .85; white-space: nowrap;
  font-weight: 500;
}
.chip.solid { border-color: transparent; background: rgba(127,127,127,.22); opacity: 1; }
.legend { display: flex; flex-wrap: wrap; gap: 20px; align-items: center; margin-top: 14px;
  font-size: 12.5px; color: var(--text-secondary); }
.legend .item { display: flex; align-items: center; gap: 6px; }
.ramp { display: flex; gap: 2px; }
.ramp i { width: 22px; height: 10px; border-radius: 2px; display: block; }
.key-dot { color: var(--text-primary); }

/* ---- bars --------------------------------------------------------------------------- */
.bars { margin-top: 6px; }
.bar-row { display: grid; grid-template-columns: 208px 1fr 84px; gap: 12px;
  align-items: center; padding: 9px 0; }
.bar-row + .bar-row { border-top: 1px solid var(--grid-line); }
.bar-label { font-size: 13px; }
.bar-label .sub { color: var(--text-muted); font-size: 11.5px; display: block; }
.track { position: relative; height: 30px; }
.axisline { position: absolute; left: 0; top: 0; bottom: 0; width: 1px; background: var(--axis); }
.gridline { position: absolute; top: 0; bottom: 12px; width: 1px; background: var(--grid-line); }
.gridlab { position: absolute; top: 3px; font-size: 11px; color: var(--text-muted);
  transform: translateX(-50%); }
.gridlab.edge-l { transform: none; }
.gridlab.edge-r { transform: translateX(-100%); }
.bar-row.axisrow { padding: 0 0 2px; border-top: 1px solid var(--grid-line); }
.track.axis { height: 20px; }
.track.axis .gridline { top: 0; bottom: 16px; }
.fill { position: absolute; left: 0; top: 1px; height: 18px; background: var(--series-1);
  border-radius: 0 4px 4px 0; }
.ci { position: absolute; left: 0; top: 23px; height: 2px; background: var(--text-muted);
  opacity: .75; }
.ci-cap { position: absolute; top: 19px; width: 1px; height: 10px; background: var(--text-muted);
  opacity: .75; }
.bar-value { text-align: right; font-size: 14px; font-weight: 600;
  font-variant-numeric: tabular-nums; }
.notrun { color: var(--text-muted); font-size: 12.5px; font-style: normal; }
.tile { display: inline-block; min-width: 200px; }
.tile .lab { font-size: 12.5px; color: var(--text-muted); }
.tile .val { font-size: 42px; font-weight: 600; line-height: 1.1; letter-spacing: -0.02em; }
.tile .note { font-size: 12.5px; color: var(--text-secondary); }

/* ---- per-case detail ------------------------------------------------------------------ */
details.case { border: 1px solid var(--border); border-radius: 10px; background: var(--surface-1);
  margin-bottom: 8px; }
details.case > summary { cursor: pointer; padding: 12px 15px; display: flex; gap: 10px;
  align-items: center; flex-wrap: wrap; font-size: 14px; }
details.case > summary::-webkit-details-marker { display: none; }
details.case > summary::before { content: "\\25B8"; color: var(--text-muted); font-size: 11px; }
details.case[open] > summary::before { content: "\\25BE"; }
details.case > summary .title { font-weight: 600; }
details.case > summary .sum-rest { color: var(--text-secondary); font-size: 12.5px; }
.case-body { padding: 0 15px 15px; border-top: 1px solid var(--grid-line); }
.field { margin-top: 12px; }
.field .k { font-size: 11.5px; text-transform: uppercase; letter-spacing: .05em;
  color: var(--text-muted); margin-bottom: 2px; }
.field .v { font-size: 13.5px; color: var(--text-primary); max-width: 92ch; }
code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; }
table.arms { border-collapse: collapse; width: 100%; margin-top: 6px; font-size: 13px; }
table.arms th, table.arms td { text-align: left; padding: 6px 10px 6px 0;
  border-bottom: 1px solid var(--grid-line); vertical-align: top; }
table.arms th { font-size: 11.5px; text-transform: uppercase; letter-spacing: .05em;
  color: var(--text-muted); font-weight: 600; }
table.arms td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
blockquote.quote { margin: 6px 0 0; padding: 7px 0 7px 12px;
  border-left: 2px solid var(--axis); color: var(--text-secondary); font-size: 13px; }
blockquote.quote .src { display: block; color: var(--text-muted); font-size: 11.5px;
  margin-top: 3px; }

/* ---- table view ----------------------------------------------------------------------- */
table.data { border-collapse: collapse; width: 100%; font-size: 12.5px; min-width: 900px; }
table.data th, table.data td { padding: 5px 9px; text-align: left;
  border-bottom: 1px solid var(--grid-line); white-space: nowrap; }
table.data th { position: sticky; top: 0; background: var(--surface-1); font-size: 11.5px;
  text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); z-index: 1; }
table.data td.num { font-variant-numeric: tabular-nums; }
/* Row labels in the layer tables carry a gloss under the name — the reader should not have to
   hold "static means did it repair the defect" in their head while reading the numbers. */
table.data td .sub { display: block; color: var(--text-muted); font-size: 11.5px;
  white-space: normal; margin-top: 2px; }
.tablewrap { max-height: 520px; overflow: auto; border: 1px solid var(--border);
  border-radius: 8px; background: var(--surface-1); }

/* ---- tooltip -------------------------------------------------------------------------- */
#tip {
  position: fixed; z-index: 50; pointer-events: none; opacity: 0;
  transition: opacity .09s ease; max-width: 330px;
  background: var(--surface-1); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: 8px;
  box-shadow: 0 6px 22px rgba(0,0,0,.16); padding: 10px 12px; font-size: 12.5px;
}
#tip .t-head { font-weight: 600; margin-bottom: 4px; }
#tip .t-val { font-size: 17px; font-weight: 600; font-variant-numeric: tabular-nums; }
#tip .t-sub { color: var(--text-secondary); }
#tip .t-row { display: flex; justify-content: space-between; gap: 14px; margin-top: 2px; }
#tip .t-key { color: var(--text-muted); }
ul.plain { margin: 6px 0 0; padding-left: 18px; }
ul.plain li { margin-bottom: 5px; max-width: 90ch; }
footer.meta { margin-top: 40px; padding-top: 14px; border-top: 1px solid var(--grid-line);
  color: var(--text-muted); font-size: 12px; }
@media (max-width: 720px) {
  .bar-row { grid-template-columns: 1fr; }
  .bar-value { text-align: left; }
}
@media print { .viz-root { background: #fff; } button.theme { display: none; } }
"""

JS = """
(function () {
  var root = document.documentElement;
  var btn = document.getElementById('themeToggle');
  if (btn) {
    btn.addEventListener('click', function () {
      var now = root.getAttribute('data-theme');
      var dark = now ? now === 'dark'
                     : window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.setAttribute('data-theme', dark ? 'light' : 'dark');
      btn.textContent = dark ? 'Dark theme' : 'Light theme';
    });
  }

  // Tooltip. Labels here are data (case ids, judge text), so every insertion is textContent —
  // never innerHTML string concatenation.
  var tip = document.getElementById('tip');
  function row(key, value) {
    var line = document.createElement('div');
    line.className = 't-row';
    var k = document.createElement('span'); k.className = 't-key'; k.textContent = key;
    var v = document.createElement('span'); v.textContent = value;
    line.appendChild(k); line.appendChild(v);
    return line;
  }
  function render(data) {
    tip.textContent = '';
    var head = document.createElement('div');
    head.className = 't-head'; head.textContent = data.case;
    var sub = document.createElement('div');
    sub.className = 't-sub'; sub.textContent = data.condition;
    var val = document.createElement('div');
    val.className = 't-val'; val.textContent = data.headline;
    tip.appendChild(head); tip.appendChild(sub); tip.appendChild(val);
    (data.rows || []).forEach(function (r) { tip.appendChild(row(r[0], r[1])); });
    if (data.foot) {
      var f = document.createElement('div');
      f.className = 't-sub'; f.style.marginTop = '6px'; f.textContent = data.foot;
      tip.appendChild(f);
    }
  }
  function place(x, y) {
    var box = tip.getBoundingClientRect();
    var left = Math.min(x + 14, window.innerWidth - box.width - 8);
    var top = y + 16 + box.height > window.innerHeight ? y - box.height - 12 : y + 16;
    tip.style.left = Math.max(8, left) + 'px';
    tip.style.top = Math.max(8, top) + 'px';
  }
  function show(el, x, y) {
    var raw = el.getAttribute('data-tip');
    if (!raw) return;
    try { render(JSON.parse(raw)); } catch (err) { return; }
    tip.style.opacity = '1';
    place(x, y);
  }
  function hide() { tip.style.opacity = '0'; }

  document.querySelectorAll('[data-tip]').forEach(function (el) {
    el.addEventListener('pointermove', function (ev) { show(el, ev.clientX, ev.clientY); });
    el.addEventListener('pointerleave', hide);
    el.addEventListener('focus', function () {
      var r = el.getBoundingClientRect();
      show(el, r.left + r.width / 2, r.top + r.height / 2);
    });
    el.addEventListener('blur', hide);
  });
  window.addEventListener('scroll', hide, { passive: true });
})();
"""


# ------------------------------------------------------------------------------------------
# Sections
# ------------------------------------------------------------------------------------------


def provenance_section(
    episodes: list[dict], cases: dict[str, dict], load_notes: list[str]
) -> tuple[str, bool]:
    """Provenance and caveats, first on the page. Returns (html, judged)."""
    judged = any("endpoint" in episode for episode in episodes)
    judged_count = sum(1 for episode in episodes if "endpoint" in episode)
    models = sorted({str(episode.get("model")) for episode in episodes})
    judges = sorted(
        {
            str((episode.get("l2") or {}).get("judge_model"))
            for episode in episodes
            if episode.get("l2")
        }
        - {"None"}
    )
    versions = sorted(
        {
            str((episode.get("l2") or {}).get("prompt_version"))
            for episode in episodes
            if episode.get("l2")
        }
        - {"None"}
    )
    run_spend = sum((episode.get("cost") or {}).get("usd") or 0 for episode in episodes)
    judge_spend = sum((episode.get("l2") or {}).get("cost_usd") or 0 for episode in episodes)
    judge_spend += sum((episode.get("l3") or {}).get("cost_usd") or 0 for episode in episodes)

    case_ids = sorted({episode["case"] for episode in episodes})
    # Sign-off comes from `benchmark/cases/*/case.yaml`, which is the register the review gate
    # actually lives in. Older episode records predate the `case_review_status` field entirely,
    # and treating a missing field as "signed off" would silently retire the gate.
    unsigned = [
        case_id
        for case_id in case_ids
        if (cases.get(case_id, {}).get("review_status") or "pending") != "signed-off"
    ]
    drafts = [
        case_id
        for case_id in case_ids
        if cases.get(case_id, {}).get("draft")
        or any(episode.get("case_draft") for episode in episodes if episode["case"] == case_id)
    ]

    stats = [
        ("Episodes", f"{len(episodes)}", f"{len(case_ids)} cases"),
        ("Subject model", ", ".join(models) or "unknown", "one model only"),
        (
            "Judge",
            (", ".join(judges) if judges else "not judged"),
            (f"prompt {', '.join(versions)}" if versions else "L1 only"),
        ),
        (
            "L2 coverage",
            f"{judged_count}/{len(episodes)}",
            "partial" if 0 < judged_count < len(episodes) else ("full" if judged else "none"),
        ),
        (
            "Cases without sign-off",
            f"{len(unsigned)}/{len(case_ids)}",
            "review gate",
        ),
        (
            "Spend",
            f"${run_spend + judge_spend:.2f}",
            f"${run_spend:.2f} run · ${judge_spend:.2f} judge",
        ),
    ]
    tiles = "".join(
        f"<div><dt>{e(label)}</dt><dd>{e(value)} "
        f'<span class="unit">{e(unit)}</span></dd></div>'
        for label, value, unit in stats
    )

    caveats: list[str] = []

    def add(kind: str, tag: str, text: str) -> None:
        caveats.append(
            f'<div class="caveat c-{kind}"><span class="ic">{e(tag)}</span>'
            f"<div>{text}</div></div>"
        )

    # `publishable_evidence` is not a disclosure control, though it was once worded as one.
    # The runner computes it as `review_status == "signed-off"` (src/mock_cluster/episode.py) —
    # the same expression as `administrator_signoff`. All three fields are one fact under three
    # names: whether a sysadmin has validated the CASE DESIGN. Nothing in it knows whether the
    # captured evidence is safe to release.
    #
    # The band used to say this page was "internal" and must not "leave the project", while
    # `.github/workflows/pages.yml` published it to a public URL — so the words and the workflow
    # contradicted each other, and the words claimed knowledge the flag does not have. It now
    # states what the flag actually means. If a real release control is ever needed it should be
    # a separate field set by a separate review, not this one.
    #
    # Still surfaced rather than filtered. Dropping the episodes would leave a page that looks
    # complete and is not, which is the same class of lie in the other direction.
    withheld = sorted(
        {
            str(episode.get("substrate") or episode.get("runner") or "unknown")
            for episode in episodes
            if episode.get("publishable_evidence") is False
        }
    )
    if withheld:
        n = sum(1 for episode in episodes if episode.get("publishable_evidence") is False)
        add(
            "critical",
            "unreviewed cases — do not quote",
            f"<b>{n} episode{'s' if n != 1 else ''} on this page are marked "
            f"<code>publishable_evidence: false</code> by the runner that produced them "
            f"({', '.join(f'<code>{e(s)}</code>' for s in withheld)}).</b> "
            f"That flag is set from the case's <code>review_status</code>: no one with sysadmin "
            f"experience has confirmed the injected defect is realistic, that the rest of the "
            f"script is clean enough to attribute a failure, or that the accepted-remedy list is "
            f"complete. <b>Every number here is a pilot result and none of it is evidence yet.</b> "
            f"This page is published deliberately, caveat attached — the flag is a scientific "
            f"gate, not a release control, and says nothing about whether the capture is safe to "
            f"share.",
        )
    if unsigned:
        add(
            "critical",
            "not evidence",
            f"<b>{len(unsigned)} of {len(case_ids)} cases have no sysadmin sign-off.</b> "
            f"The review gate is a rule in this project: a case nobody with sysadmin experience "
            f"has signed off on is not evidence. Read every number on this page as a pilot. "
            f'<span class="muted">Unsigned: '
            f'{", ".join(f"<code>{e(c)}</code>" for c in unsigned)}.</span>',
        )
    if drafts:
        add(
            "serious",
            "draft case",
            f"<b>Includes draft case(s): "
            f'{", ".join(f"<code>{e(c)}</code>" for c in drafts)}.</b> '
            f"Drafts are excluded from <code>episode.py all</code> and were run deliberately. "
            f"A draft has been seen by nobody but its author.",
        )
    if not judged:
        add(
            "serious",
            "L1 only",
            "<b>These records have not been judged, so this is not the primary endpoint.</b> "
            "Nothing here distinguishes an agent that understood the problem from one that fixed "
            "it by accident; L1 is a static and call-log reading of the final script. "
            "Run <code>judge.py</code> over them before quoting anything.",
        )
    elif judged_count < len(episodes):
        add(
            "warning",
            "partial L2",
            f"<b>{judged_count} of {len(episodes)} episodes were judged</b>; the other "
            f"{len(episodes) - judged_count} are scored on L1 alone. That is deliberate when "
            f"judging only L1 passes — an L1 failure is already a failure and L2 would restate "
            f"it — but <code>fixed_by_accident</code> and forbidden regressions were only looked "
            f"for where L1 said pass.",
        )
    if judged and judges and set(judges) & set(models):
        add(
            "serious",
            "self-graded",
            "<b>The judge and the subject are the same model.</b> A model grading its own output "
            "flatters it. Re-run the judge with a different <code>--model</code> before treating "
            "any number here as external.",
        )
    seeds_per_cell = defaultdict(set)
    for episode in episodes:
        seeds_per_cell[(episode["case"], episode["condition"]["label"])].add(episode.get("seed"))
    fewest = min((len(s) for s in seeds_per_cell.values()), default=0)
    most = max((len(s) for s in seeds_per_cell.values()), default=0)
    plural = "s" if fewest != 1 else ""
    depth = f"{fewest} seed{plural}" if fewest == most else f"{fewest}–{most} seeds"
    add(
        "warning",
        "underpowered",
        f"<b>{len(case_ids)} synthetic case{'s' if len(case_ids) != 1 else ''}, "
        f"{depth} per populated cell.</b> "
        f"Detecting the effect previously observed at 80% power needs roughly 20 seeds per case "
        f"per arm. Per-cell outcomes are the result here; an aggregate at this depth is "
        f"decoration, and is placed last on this page for that reason.",
    )
    present = {episode["condition"]["label"] for episode in episodes}
    missing = [label for label in CONDITION_ORDER if label not in present]
    if missing:
        add(
            "warning",
            "incomplete",
            f"<b>{len(missing)} of the four conditions were not run in this file:</b> "
            f'{", ".join(f"{e(condition_line(m))} (<code>{e(m)}</code>)" for m in missing)}. '
            f"The 2×2 is not complete, so no statement about the interaction of the document and "
            f"the skills is available.",
        )
    for note in load_notes:
        add("warning", "partial file", f"<b>{e(note)}</b>")

    return (
        '<section id="provenance"><div class="sec-head">'
        "<h2>Provenance</h2>"
        '<p class="caveat-line">Everything below is measured from the episode records named at the '
        "foot of this page. The caveats here bind every number on it.</p></div>"
        f'<div class="prov">{tiles}</div>'
        f'<div class="caveats">{"".join(caveats)}</div></section>',
        judged,
    )


def caveat_tail(case_count: int) -> str:
    """The standing caveats, in the same sentence as any number they bind. Case count is
    counted, never spelled out from memory."""
    return (
        f"{case_count} synthetic case{'s' if case_count != 1 else ''}, one model, "
        f"no sysadmin sign-off, underpowered."
    )


def grid_section(
    grid: dict, cases: dict[str, dict], conditions: list[str], judged: bool
) -> tuple[str, dict]:
    """The core view: cases × conditions, k/n plus stability."""
    census = {"stable_zero": 0, "stable_all": 0, "flips": 0, "not_run": 0, "single_seed": 0}

    head = '<th class="rowhead">Case</th>' + "".join(
        f'<th><span class="arm-doc">{e(condition_name(label)[0])}</span>'
        f'<span class="arm-skill">{e(condition_name(label)[1])}</span>'
        f'<code class="arm-raw">{e(label)}</code></th>'
        for label in conditions
    )
    rows = []
    for case_id in sorted(grid):
        meta = cases.get(case_id, {})
        family = str(meta.get("family") or case_id[:1])
        sub = str(meta.get("family_name") or "")
        severity = str(meta.get("severity") or "")
        draft = " · draft" if meta.get("draft") else ""
        row = [
            f'<td class="rowhead">'
            f'<span class="case-id"><span class="fam-dot" style="--fam: var(--family-{e(family)})">'
            f"</span><code>{e(case_id)}</code></span>"
            f'<span class="case-sub">family {e(family)} · {e(sub)}'
            f"{e(' · ' + severity if severity else '')}{e(draft)}</span></td>"
        ]
        for label in conditions:
            group = grid[case_id].get(label, [])
            if not group:
                census["not_run"] += 1
                row.append(
                    '<td class="cell empty" tabindex="0" data-tip='
                    + json_attr(
                        {
                            "case": case_id,
                            "condition": f"{condition_line(label)}  ({label})",
                            "headline": "not run",
                            "rows": [],
                            "foot": "This cell has no episodes in the loaded file.",
                        }
                    )
                    + '><span class="kn">—</span><div class="cellchips">'
                    + chip("not run")
                    + "</div></td>"
                )
                continue

            stats = cell_stats(group)
            passed, scored = stats["passed"], stats["n_scored"]
            if scored == 1:
                census["single_seed"] += 1
            if stats["unstable"]:
                census["flips"] += 1
            elif scored and passed == scored:
                census["stable_all"] += 1
            elif scored:
                census["stable_zero"] += 1

            chips = []
            if stats["unstable"]:
                chips.append(chip("flips", "solid"))
            elif scored == 1:
                chips.append(chip("1 seed"))
            if stats["nothing_submitted"]:
                chips.append(chip(f"nothing ran ×{stats['nothing_submitted']}"))
            not_scored = stats["n_total"] - scored
            if not_scored:
                chips.append(chip(f"{not_scored} n/s"))

            mark_rows = [
                ("prevented, nothing submitted", stats["marks"].get("idle", 0)),
                ("fixed by accident", stats["marks"].get("acc", 0)),
                ("submitted nothing", stats["marks"].get("norun", 0)),
                ("needs review", stats["marks"].get("rev", 0)),
                ("ended abnormally", stats["marks"].get("part", 0)),
                ("submissions rejected", stats["rejected"]),
            ]
            tip = {
                "case": case_id,
                "condition": f"{condition_line(label)}  ({label})",
                "headline": f"{passed}/{scored} prevented",
                "rows": [
                    ["stability", "flips across seeds" if stats["unstable"] else "consistent"],
                    ["seeds", ", ".join(str(s["seed"]) for s in stats["seeds"])],
                    ["layer", "L1 + L2" if stats["judged"] == stats["n_total"] and stats["judged"]
                     else (f"L1 + L2 on {stats['judged']}/{stats['n_total']}"
                           if stats["judged"] else "L1 only")],
                ]
                + [[k, str(v)] for k, v in mark_rows if v],
                "foot": "Every seed's verdict is in the table view below.",
            }
            row.append(
                f'<td class="cell b{heat_bin(passed, scored)}" tabindex="0" '
                f"data-tip={json_attr(tip)}>"
                f'<span class="kn">{passed}/{scored}</span>'
                f"{dot_strip(stats['seeds'])}"
                + (f'<div class="cellchips">{"".join(chips)}</div>' if chips else "")
                + "</td>"
            )
        rows.append("<tr>" + "".join(row) + "</tr>")

    ramp = "".join(
        f'<i style="background: var(--heat-{index}-bg)"></i>' for index in range(len(HEAT_LIGHT))
    )
    legend = (
        '<div class="legend">'
        f'<span class="item">none prevented <span class="ramp">{ramp}</span> all prevented</span>'
        '<span class="item key-dot"><span class="dots">'
        '<span class="dot dot-on"></span></span> seed prevented</span>'
        '<span class="item key-dot"><span class="dots">'
        '<span class="dot dot-off"></span></span> seed not prevented</span>'
        '<span class="item key-dot"><span class="dots">'
        '<span class="dot dot-none"></span></span> seed not scored</span>'
        f'<span class="item">{chip("flips", "solid")} outcome changed across seeds</span>'
        "</div>"
    )

    endpoint_note = (
        "The primary endpoint — L1 and L2 agreeing."
        if judged
        else "<b>L1 only.</b> Not the primary endpoint; these cells report the static and "
        "call-log reading, which cannot see whether the agent understood anything."
    )

    section = (
        '<section id="grid"><div class="sec-head"><h2>The grid</h2>'
        f'<p class="caveat-line">Prevented episodes per cell, out of the episodes that were '
        f"scored. {endpoint_note} "
        "<b>Stability is the thing to read first:</b> a cell whose dots are mixed changed its "
        "answer between seeds, and at one seed a result and a coin flip are the same picture. "
        f"{caveat_tail(len(grid))}</p></div>"
        f"{cell_key()}{family_key(grid, cases)}"
        f'<div class="card"><div class="scroll"><table class="grid">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
        f"{legend}</div></section>"
    )
    return section, census


def cell_key() -> str:
    """How to read one cell, and nothing else.

    This was a six-term glossary defining case, prevented, instructions, skill and family as well.
    All five are the benchmark's design rather than this run's result, and the project page now
    carries them; repeating them on every report made the reader scroll past the method to reach
    the measurement.

    What stays is the part that is unreadable without it. `2/5` misleads on its own — it looks
    like a score out of five different things, and it is one thing attempted five times — and
    "prevented" has a different definition in a judged file than an unjudged one, so it cannot be
    looked up anywhere but here.
    """
    return (
        '<p class="cellkey"><b>One cell is one case in one arm.</b> '
        "<code>2/5</code> means the same script, prompt and cluster were attempted five times "
        "under five seeds and prevented twice — not two things out of five. The spread is the "
        "finding, which is why a mixed cell is flagged <b>flips</b> rather than averaged. "
        "Prevented does <b>not</b> require a submission: <code>nothing ran</code> marks those "
        "episodes, and the condition comparison carries the stricter <i>prevented + submitted</i> "
        "count beside the raw one.</p>"
    )


def family_key(grid: dict, cases: dict[str, dict]) -> str:
    """The families as a legend for the grid's colours — the letter, the name, the members.

    Derived from the loaded cases rather than written out here: the letter, its name and its
    membership all come from `case.yaml`, so a new case or a renamed family shows up without
    anyone remembering to edit this file. Colour is never the only carrier — the letter and the
    name are always printed next to the dot.

    It no longer explains what each family costs a facility. That is what the grouping means, not
    what this run found, and the project page says it once instead of every report saying it
    again.
    """
    families: dict[str, dict] = {}
    for case_id in sorted(grid):
        meta = cases.get(case_id, {})
        letter = str(meta.get("family") or case_id[:1])
        entry = families.setdefault(letter, {"name": "", "cases": []})
        entry["cases"].append(case_id)
        if meta.get("family_name"):
            entry["name"] = str(meta["family_name"])
    if not families:
        return ""
    rows = "".join(
        f'<div class="fam-row">'
        f'<span class="fam-dot" style="--fam: var(--family-{e(letter)})"></span>'
        f'<div><dt>{e(letter)} — {e(entry["name"] or "unnamed")}</dt>'
        f'<dd><span class="fam-cases">'
        f'{", ".join(f"<code>{e(c)}</code>" for c in entry["cases"])}</span></dd></div></div>'
        for letter, entry in sorted(families.items())
    )
    return f'<div class="famkey"><dl>{rows}</dl></div>'


def census_section(census: dict, judged: bool) -> str:
    """A handful of headline numbers about stability — a KPI row, not a chart."""
    items = [
        ("Cells that flip", census["flips"], "changed answer across seeds — unattributable"),
        ("Consistently 0", census["stable_zero"], "never prevented, every seed"),
        ("Consistently n", census["stable_all"], "always prevented, every seed"),
        ("Single seed", census["single_seed"], "indistinguishable from a coin flip"),
        ("Not run", census["not_run"], "cell absent from this file"),
    ]
    tiles = "".join(
        f"<div><dt>{e(label)}</dt><dd>{e(value)} "
        f'<span class="unit">{e(unit)}</span></dd></div>'
        for label, value, unit in items
    )
    return (
        '<section id="stability"><div class="sec-head"><h2>Stability census</h2>'
        '<p class="caveat-line">How much of the grid is a finding and how much is variance. '
        "A cell that flips is evidence about seed variance, not about the intervention — no "
        "per-case claim is safe for those cells in either direction.</p></div>"
        f'<div class="prov">{tiles}</div></section>'
    )


def arms_section(episodes: list[dict], conditions_all: list[str], judged: bool) -> str:
    """Prevented per condition, with submission-qualified prevention alongside it.

    Form chosen by the skill's heuristic rather than by habit: with two or more arms carrying data
    the reader's job is to compare magnitudes, which is a bar chart — horizontal, because the
    condition labels are long. With exactly one arm there is nothing to compare and a one-bar bar
    chart is a stat tile wearing a costume, so it renders as a stat tile.
    """
    per_arm = []
    for label in conditions_all:
        group = [episode for episode in episodes if episode["condition"]["label"] == label]
        scored = [episode for episode in group if endpoint_of(episode) is not None]
        caught = sum(1 for episode in scored if endpoint_of(episode))
        caught_and_submitted = sum(
            1
            for episode in scored
            if endpoint_of(episode)
            and (episode.get("evidence") or {}).get("workload_submitted")
        )
        per_arm.append(
            (label, caught, caught_and_submitted, len(scored), len(group) - len(scored))
        )

    populated = [row for row in per_arm if row[3] > 0]

    caveat = (
        f"{caveat_tail(len({episode['case'] for episode in episodes}))} This aggregate pools "
        f"cases of very different difficulty and is the least informative and most quotable thing "
        f"on the page. It is here last, and below the grid, for that reason."
    )

    if len(populated) <= 1:
        if not populated:
            body = '<p class="notrun">No arm in this file has a scored episode.</p>'
        else:
            label, caught, caught_and_submitted, scored, unscored = populated[0]
            missing = [row[0] for row in per_arm if row[3] == 0]
            body = (
                '<div class="tile">'
                f'<div class="lab">{e(condition_line(label))}</div>'
                f'<div class="val">{caught} of {scored}</div>'
                f'<div class="note">episodes prevented · {caught_and_submitted}/{scored} '
                f'prevented + submitted'
                f"{e(f' · {unscored} not scored' if unscored else '')}</div></div>"
                + (
                    '<p class="notrun" style="margin-top:12px">Not run in this file: '
                    + ", ".join(f"<code>{e(m)}</code>" for m in missing)
                    + ". With one arm there is no comparison to draw, so this is a single "
                    "figure rather than a chart.</p>"
                    if missing
                    else ""
                )
            )
        return (
            '<section id="arms"><div class="sec-head"><h2>Prevented, per condition</h2>'
            f'<p class="caveat-line">{caveat}</p></div>'
            f'<div class="card">{body}</div></section>'
        )

    rows = []
    for label, caught, caught_and_submitted, scored, unscored in per_arm:
        if scored == 0:
            rows.append(
                f'<div class="bar-row"><div class="bar-label">{e(condition_line(label))}'
                f'<span class="sub"><code>{e(label)}</code></span></div>'
                f'<div class="notrun">not run in this file</div>'
                f'<div class="bar-value muted">—</div></div>'
            )
            continue
        rate = caught / scored
        low, high = wilson(caught, scored)
        # Gridlines per row, tick labels once (in the axis row below). Repeating the labels on
        # every row put "25%" straight through the confidence rule.
        ticks = "".join(
            f'<span class="gridline" style="left: {pct}%"></span>' for pct in (0, 25, 50, 75, 100)
        )
        tip = {
            "case": label,
            "condition": f"{scored} scored episodes"
            + (f" · {unscored} not scored" if unscored else ""),
            "headline": f"{caught}/{scored} prevented ({rate * 100:.0f}%)",
            "rows": [
                ["prevented + submitted", f"{caught_and_submitted}/{scored}"],
                ["95% Wilson interval", f"{low * 100:.0f}% – {high * 100:.0f}%"],
            ],
            "foot": "Interval assumes independent episodes. They are not: the seeds within a "
                    "case share a script and a prompt, so this is wider than it looks.",
        }
        rows.append(
            f'<div class="bar-row" tabindex="0" data-tip={json_attr(tip)}>'
            f'<div class="bar-label">{e(condition_line(label))}'
            f'<span class="sub">{scored} scored'
            f"{e(f' · {unscored} not scored' if unscored else '')}"
            f" · <code>{e(label)}</code><br>{caught_and_submitted}/{scored} prevented + "
            f"submitted</span></div>"
            f'<div class="track"><span class="axisline"></span>{ticks}'
            f'<span class="fill" style="width: {rate * 100:.2f}%"></span>'
            f'<span class="ci" style="left: {low * 100:.2f}%; '
            f'width: {max(0.0, (high - low) * 100):.2f}%"></span>'
            f'<span class="ci-cap" style="left: {low * 100:.2f}%"></span>'
            f'<span class="ci-cap" style="left: {high * 100:.2f}%"></span></div>'
            f'<div class="bar-value">{caught}/{scored}</div></div>'
        )

    # The axis band is part of the chart's height, not something the container crops off.
    axis_ticks = "".join(
        f'<span class="gridline" style="left: {pct}%"></span>'
        f'<span class="gridlab{" edge-l" if pct == 0 else (" edge-r" if pct == 100 else "")}" '
        f'style="left: {pct}%">{pct}%</span>'
        for pct in (0, 25, 50, 75, 100)
    )
    rows.append(
        '<div class="bar-row axisrow"><div></div>'
        f'<div class="track axis">{axis_ticks}</div><div></div></div>'
    )

    # The document contrast, pooled — reported to show the difference is not distinguishable from
    # noise, not as a test of an effect.
    contrast = ""
    absent = [row for row in per_arm if row[0].startswith("doc-absent")]
    present = [row for row in per_arm if row[0].startswith("doc-present")]
    a_k, a_n = sum(r[1] for r in absent), sum(r[3] for r in absent)
    p_k, p_n = sum(r[1] for r in present), sum(r[3] for r in present)
    if a_n and p_n:
        p_value = fisher_two_sided(a_k, a_n - a_k, p_k, p_n - p_k)
        contrast = (
            f'<p class="small muted" style="margin-top:14px">Pooling the doc arms: '
            f"<b>{a_k}/{a_n}</b> without the document, <b>{p_k}/{p_n}</b> with it. "
            f"Fisher exact, two-sided: <b>p = {p_value:.2g}</b>. This pools nine cases of "
            f"different difficulty, so it is a between-case number; it is reported to show the "
            f"difference is not distinguishable from noise at this size, not as a test of an "
            f"effect. The intervals drawn above overlap even under the generous assumption that "
            f"episodes are independent draws, which they are not.</p>"
        )

    return (
        '<section id="arms"><div class="sec-head"><h2>Prevented, per condition</h2>'
        f'<p class="caveat-line">{caveat}</p></div>'
        f'<div class="card"><div class="bars">{"".join(rows)}</div>'
        f'<p class="small muted" style="margin-top:12px">Bar = share of scored episodes '
        f"prevented. The line under each condition reports the stricter count that also recorded "
        f"an accepted workload submission. The thin rule beneath each bar is a 95% Wilson "
        f"interval computed as if every "
        f"episode were an independent draw — they are not, since seeds are clustered within a "
        f"case, so the true interval is wider than drawn.</p>{contrast}</div></section>"
    )


def cases_section(grid: dict, cases: dict[str, dict], conditions: list[str]) -> str:
    """Per case: what the defect was, what happened in each arm, and what the judge quoted."""
    blocks = []
    for case_id in sorted(grid):
        meta = cases.get(case_id, {})
        arm_rows = []
        for label in conditions:
            group = grid[case_id].get(label, [])
            if not group:
                arm_rows.append(
                    f'<tr><td>{e(condition_line(label))}<br>'
                    f'<code class="arm-raw">{e(label)}</code></td>'
                    f'<td class="num muted">not run</td><td colspan="2"></td></tr>'
                )
                continue
            stats = cell_stats(group)
            marks = []
            for key, text in (
                ("idle", "prevented, nothing submitted"),
                ("acc", "fixed by accident"),
                ("norun", "submitted nothing"),
                ("rev", "needs review"),
                ("part", "ended abnormally"),
            ):
                count = stats["marks"].get(key, 0)
                if count:
                    marks.append(chip(f"{text} ×{count}"))
            if stats["rejected"]:
                marks.append(chip(f"submissions rejected ×{stats['rejected']}"))
            marks_cell = " ".join(marks) or '<span class="muted">—</span>'
            stability = "flips across seeds" if stats["unstable"] else "consistent"
            arm_rows.append(
                f"<tr><td>{e(condition_line(label))}<br>"
                f'<code class="arm-raw">{e(label)}</code></td>'
                f'<td class="num">{stats["passed"]}/{stats["n_scored"]}</td>'
                f"<td>{stability}</td>"
                f"<td>{marks_cell}</td></tr>"
            )

        quotes = []
        seen: set[str] = set()
        for label in conditions:
            for episode in grid[case_id].get(label, []):
                for reading in (episode.get("l2") or {}).get("readings", []):
                    quote = (reading.get("recognition_quote") or "").strip()
                    if not quote or quote in seen:
                        continue
                    seen.add(quote)
                    quotes.append(
                        f'<blockquote class="quote">{e(quote[:600])}'
                        f'<span class="src">{e(condition_line(label))} · '
                        f'seed {e(episode.get("seed"))} · '
                        f'judge verdict {e(reading.get("verdict"))} '
                        f'({e(reading.get("confidence"))} confidence)</span></blockquote>'
                    )
        quotes = quotes[:4]

        def field(key: str, value: str) -> str:
            return (
                f'<div class="field"><div class="k">{e(key)}</div>'
                f'<div class="v">{value}</div></div>'
            )

        remedies = ", ".join(
            f"<code>{e(r.get('id'))}</code>" for r in (meta.get("accepted_remedies") or [])
        )
        regressions = ", ".join(
            f"<code>{e(r.get('id'))}</code>" for r in (meta.get("forbidden_regressions") or [])
        )
        review = str(meta.get("review_status") or "unknown")
        body = (
            field("injected defect", e(str(meta.get("injected_defect") or "").strip())
                  or '<span class="muted">no case.yaml found for this id</span>')
            + (field("guardrail the agent was measured against",
                     e(str(meta.get("guardrail") or "").strip())) if meta.get("guardrail") else "")
            + (field("accepted remedies", remedies) if remedies else "")
            + (field("forbidden regressions", regressions) if regressions else "")
            + field(
                "what happened in each arm",
                '<table class="arms"><thead><tr><th>Condition</th><th>Prevented</th>'
                "<th>Stability</th><th>Marks the harness recorded</th></tr></thead>"
                f"<tbody>{''.join(arm_rows)}</tbody></table>"
                '<p class="tiny muted" style="margin-top:6px">Submission rejections are '
                "descriptive only. Being rejected is a property of the case, not of the arm, so "
                "the stratified comparison it once supported is withdrawn.</p>",
            )
            + (
                field(
                    "what the judge quoted as recognition",
                    "".join(quotes)
                    + '<p class="tiny muted" style="margin-top:6px">Verbatim from the L2 '
                    "readings, deduplicated, first four shown.</p>",
                )
                if quotes
                else ""
            )
            + (
                field("provenance of the case", e(str(meta.get("provenance") or "").strip()))
                if meta.get("provenance")
                else ""
            )
        )
        blocks.append(
            f'<details class="case"><summary>'
            f'<span class="fam-dot" style="--fam: var(--family-{family_of(meta, case_id)})">'
            f"</span>"
            f'<code class="title">{e(case_id)}</code>'
            f'<span class="sum-rest">{e(meta.get("title") or "")}</span>'
            f'<span class="sum-rest">{chip("review: " + review)}'
            f'{chip("draft") if meta.get("draft") else ""}</span>'
            f'</summary><div class="case-body">{body}</div></details>'
        )

    return (
        '<section id="cases"><div class="sec-head"><h2>Per case</h2>'
        '<p class="caveat-line">What happened in each arm and — where L2 judged — the judge\'s own '
        "words for why it thought the agent recognised the problem. Read from "
        "<code>benchmark/cases/*/case.yaml</code>, which is withheld from the agent under "
        "test.</p></div>"
        f"{''.join(blocks)}</section>"
    )


def table_section(episodes: list[dict]) -> str:
    """Every episode, one row. The accessible twin of the grid — nothing is gated on a hover."""
    rows = []
    for episode in sorted(
        episodes,
        key=lambda x: (x["case"], x["condition"]["label"], seed_key(x)),
    ):
        verdict = endpoint_of(episode)
        text = VERDICT_TEXT[verdict]
        evidence = episode.get("evidence") or {}
        rows.append(
            "<tr>"
            f"<td><code>{e(episode['case'])}</code></td>"
            f"<td><code>{e(episode['condition']['label'])}</code></td>"
            f'<td class="num">{e(episode.get("seed"))}</td>'
            f"<td>{e(text)}</td>"
            f"<td>{'L1 + L2' if 'endpoint' in episode else 'L1 only'}</td>"
            f"<td>{e((episode.get('l1') or {}).get('static', {}).get('verdict'))}</td>"
            f"<td>{e((episode.get('l1') or {}).get('call_log', {}).get('verdict'))}</td>"
            f"<td>{e((episode.get('l2') or {}).get('verdict') or '—')}</td>"
            f"<td>{e('yes' if evidence.get('workload_submitted') else 'no')}</td>"
            f'<td class="num">{e(evidence.get("submissions_rejected", "—"))}</td>'
            f"<td>{e(', '.join(cell_marks(episode)) or '—')}</td>"
            f"<td>{e(episode.get('validity'))}</td>"
            f'<td class="num">${(episode.get("cost") or {}).get("usd") or 0:.3f}</td>'
            "</tr>"
        )
    head = "".join(
        f"<th>{e(name)}</th>"
        for name in (
            "Case", "Condition", "Seed", "Endpoint", "Layers", "L1 static", "L1 call log",
            "L2 verdict", "Workload submitted", "Rejected", "Marks", "Validity", "Cost",
        )
    )
    return (
        '<section id="table"><div class="sec-head"><h2>Table view</h2>'
        '<p class="caveat-line">Every episode in the loaded files. This is the accessible twin of '
        "the grid: no value on this page is reachable only by hovering.</p></div>"
        f'<div class="tablewrap"><table class="data"><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div></section>"
    )


def layers_section(episodes: list[dict], conditions_all: list[str]) -> str:
    """Which L1 layer failed, and which detector inside it.

    The grid answers *how often* an arm prevented the misuse. It cannot answer *what went wrong*,
    and those are different questions with, in this run, different answers: an arm can repair the
    injected defect more often than the control and still finish below it, because the endpoint
    is a conjunction and the second layer fails for its own reasons.

    Kept as a table rather than a chart on purpose. The reader needs exact counts and detector
    names, and the row that matters most (one detector accounting for every failure in an arm) is
    a fact about identity, not magnitude — a bar chart would round it away. No heat colour either:
    shading failure counts would assert that more red is worse, which is the reading under dispute
    below rather than something this page should presuppose.
    """
    layers = ("static", "call_log")
    layer_name = {"static": "static", "call_log": "call log"}

    # A detector only produces a finding on the cases whose case.yaml asks for it, so its
    # denominator is not the arm size. Carrying that denominator through is the whole point of the
    # section: "8 failures" and "8 failures out of 9 episodes that could fail" are different
    # claims, and only the second one is comparable across arms.
    carried: dict[tuple[str, str], int] = defaultdict(int)
    failed: dict[tuple[str, str], int] = defaultdict(int)
    detector_layer: dict[str, str] = {}
    for episode in episodes:
        label = episode["condition"]["label"]
        for layer in layers:
            for finding in ((episode.get("l1") or {}).get(layer) or {}).get("findings") or []:
                name = finding.get("detector")
                if not name:
                    continue
                detector_layer.setdefault(name, layer)
                carried[(name, label)] += 1
                if not finding.get("passed"):
                    failed[(name, label)] += 1

    if not carried:
        return ""

    populated = [
        label
        for label in conditions_all
        if any(episode["condition"]["label"] == label for episode in episodes)
    ]

    head = "".join(f"<th>{e(condition_line(label))}</th>" for label in populated)

    layer_rows = []
    for layer in layers:
        cells = []
        for label in populated:
            group = [x for x in episodes if x["condition"]["label"] == label]
            scored = [x for x in group if ((x.get("l1") or {}).get(layer) or {}).get("verdict")]
            bad = sum(
                1 for x in scored if (x["l1"][layer] or {}).get("verdict") == "fail"
            )
            cells.append(
                f'<td class="num">{len(scored) - bad}/{len(scored)}</td>'
                if scored
                else '<td class="num muted">—</td>'
            )
        passed_label = (
            "repaired the defect" if layer == "static" else "conduct within the site's budget"
        )
        layer_rows.append(
            f'<tr><td><b>L1 {e(layer_name[layer])}</b>'
            f'<span class="sub">{e(passed_label)}</span></td>{"".join(cells)}</tr>'
        )

    detector_rows = []
    for name in sorted(detector_layer, key=lambda d: (detector_layer[d], d)):
        cells = []
        for label in populated:
            n = carried[(name, label)]
            k = failed[(name, label)]
            cells.append(
                f'<td class="num">{k}/{n}</td>' if n else '<td class="num muted">—</td>'
            )
        detector_rows.append(
            f"<tr><td><code>{e(name)}</code>"
            f'<span class="sub">L1 {e(layer_name[detector_layer[name]])}</span></td>'
            f'{"".join(cells)}</tr>'
        )

    # State the concentration if there is one, computed rather than asserted: an arm whose call-log
    # failures all come from a single detector is a finding about that detector, and the sentence
    # should not survive into a run where it stops being true.
    notes = []
    for label in populated:
        call_detectors = [d for d in detector_layer if detector_layer[d] == "call_log"]
        totals = {d: failed[(d, label)] for d in call_detectors}
        total = sum(totals.values())
        hot = [d for d, k in totals.items() if k]
        if total and len(hot) == 1:
            name = hot[0]
            notes.append(
                f"<li><b>{e(condition_line(label))}</b>: all {total} call-log failures are "
                f"<code>{e(name)}</code>, out of {carried[(name, label)]} episodes whose case "
                f"carries that detector.</li>"
            )

    concentration = (
        f'<ul class="plain" style="margin-top:14px">{"".join(notes)}</ul>' if notes else ""
    )

    return (
        '<section id="layers"><div class="sec-head"><h2>Which layer failed</h2>'
        '<p class="caveat-line">The endpoint is a conjunction, so a cell can miss two ways: the '
        "defect was not repaired (<i>static</i>), or it was and the agent misbehaved on the way "
        "(<i>call log</i>). Passes out of the episodes each layer scored.</p></div>"
        f'<div class="tablewrap"><table class="data"><thead><tr><th>Layer</th>{head}</tr></thead>'
        f'<tbody>{"".join(layer_rows)}</tbody></table></div>'
        '<div class="sec-head" style="margin-top:22px"><h3>Which detector fired</h3>'
        '<p class="caveat-line">Failures out of the episodes whose case carries that detector — '
        "not out of the arm. A detector defined on three of nine cases has a denominator of nine, "
        "not twenty-seven, and comparing its raw count against another detector's is a category "
        "error.</p></div>"
        f'<div class="tablewrap"><table class="data"><thead><tr><th>Detector</th>{head}</tr>'
        f'</thead><tbody>{"".join(detector_rows)}</tbody></table></div>'
        f"{concentration}"
        '<p class="small muted" style="margin-top:14px">A single detector carrying every failure '
        "in an arm is not by itself evidence that the arm behaved badly, nor that the detector is "
        "miscalibrated. It localises the disagreement to one threshold, which is the point at "
        "which a sysadmin has to say which reading is right — see the review gate above.</p>"
        "</section>"
    )


def substrate_limit(episodes: list[dict]) -> str:
    """Explain whether consequence was inferred by stubs or executed by a scheduler."""
    substrates = sorted(
        {str(episode.get("substrate") or "echo-stub") for episode in episodes}
    )
    if substrates == ["echo-stub"]:
        return (
            "<li><b>Nothing executed.</b> No node was allocated and no file written. Slurm is an "
            "echo stub; family B is scored from the text of the script, and every L3 figure is a "
            "projection.</li>"
        )
    if "echo-stub" in substrates:
        names = ", ".join(f"<code>{e(name)}</code>" for name in substrates)
        return (
            f"<li><b>Mixed substrates: {names}.</b> Consequence is executed under the scheduler "
            "substrate and inferred from script text under <code>echo-stub</code>. These are not "
            "the same measurement and must not be pooled into one rate.</li>"
        )

    submitted = sum(
        bool((episode.get("evidence") or {}).get("workload_submitted"))
        for episode in episodes
    )
    accounting = sum(
        len((episode.get("evidence") or {}).get("accounting") or [])
        for episode in episodes
    )
    names = ", ".join(f"<code>{e(name)}</code>" for name in substrates)
    return (
        f"<li><b>Executed substrate: {names}.</b> {submitted}/{len(episodes)} episodes recorded "
        f"an accepted workload submission and the records contain {accounting} scheduler "
        "accounting entries. Consequence is observed on the laptop mock cluster rather than "
        "inferred from an echo stub; this still does not reproduce production scale, queueing, "
        "or filesystem load.</li>"
    )


def limits_section(episodes: list[dict]) -> str:
    return (
        '<section id="limits"><div class="sec-head"><h2>What this does not measure</h2></div>'
        '<div class="card"><ul class="plain">'
        "<li><b>Repair, not restraint.</b> The agent is handed a bad script and asked to run it. "
        "It is never asked to write one, so nothing here shows whether it would have made the "
        "same mistake itself. That is the difference between <i>the skill teaches an agent to "
        "spot misuse</i> and <i>the skill prevents misuse</i>, and only the first is measured."
        "</li>"
        f"{substrate_limit(episodes)}"
        "<li><b>The richest arm can look good by refusing to do the work.</b> An episode that "
        "prevents the defect and submits nothing is counted as prevented by the endpoint, and it "
        "is not the same result as one that repaired the script and ran it. Those episodes are "
        "flagged in the grid (<i>nothing ran</i>) and listed per case. The condition comparison "
        "reports <i>prevented + submitted</i> alongside the raw prevented count.</li>"
        "<li><b>No case has sysadmin sign-off.</b> Until it does, this is a pilot measuring "
        "itself.</li>"
        "</ul></div></section>"
    )


def json_attr(payload: dict) -> str:
    return '"' + html.escape(json.dumps(payload, ensure_ascii=False), quote=True) + '"'


# ------------------------------------------------------------------------------------------
# Page
# ------------------------------------------------------------------------------------------


def build_page(
    episodes: list[dict], title: str, sources: list[str], load_notes: list[str]
) -> str:
    cases = load_cases()

    grid: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for episode in episodes:
        grid[episode["case"]][episode["condition"]["label"]].append(episode)

    present = {episode["condition"]["label"] for episode in episodes}
    # Every one of the four conditions is shown in the grid, even when it was not run: the hole in
    # the matrix is a fact about the run, and hiding the column would hide it.
    conditions = list(CONDITION_ORDER) + sorted(present - set(CONDITION_ORDER))

    provenance, judged = provenance_section(episodes, cases, load_notes)
    grid_html, census = grid_section(grid, cases, conditions, judged)

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    source_list = ", ".join(f"<code>{e(name)}</code>" for name in sources)

    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{e(title)}</title>"
        f"<style>{build_css()}</style></head>"
        '<body><div class="viz-root"><div class="wrap">'
        '<div class="topbar"><div>'
        f"<h1>{e(title)}</h1>"
        '<p class="lede">One run of the misuse-repair benchmark: each case hands the agent a job '
        "script with one known defect injected and asks it to run the work. "
        "<b>Read the provenance first — the caveats there bind every number on this page.</b> "
        '<a class="method" href="./index.html">The question, the cases, the conditions and the '
        "judging &rarr;</a></p>"
        "</div>"
        '<button class="theme" id="themeToggle" type="button">Theme</button></div>'
        f"{provenance}"
        f"{grid_html}"
        f"{census_section(census, judged)}"
        f"{cases_section(grid, cases, conditions)}"
        f"{layers_section(episodes, conditions)}"
        f"{arms_section(episodes, conditions, judged)}"
        f"{table_section(episodes)}"
        f"{limits_section(episodes)}"
        f'<footer class="meta">Generated {e(generated)} by '
        f"<code>hpcbench.harness.report_html</code> from {source_list}. "
        f"Counts are computed with the same functions as <code>report.py</code> "
        f"(<code>endpoint_of</code>, <code>cell_marks</code>), so the two cannot disagree. "
        f"Self-contained: no network request is made by this page.</footer>"
        f'</div></div><div id="tip" role="status" aria-live="polite"></div>'
        f"<script>{JS}</script></body></html>\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("episodes", nargs="+", help="episodes*.jsonl, judged or not")
    parser.add_argument("--out", required=True, help="path of the HTML file to write")
    parser.add_argument("--title", default="Misuse-repair benchmark — results")
    arguments = parser.parse_args()

    episodes, notes = load(arguments.episodes)
    if not episodes:
        raise SystemExit("no episodes matched")

    sources = []
    for pattern in arguments.episodes:
        sources.extend(Path(path).name for path in sorted(glob.glob(pattern)))
    sources = sources or [Path(p).name for p in arguments.episodes]

    output = Path(arguments.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_page(episodes, arguments.title, sources, notes))
    print(f"{output} — {len(episodes)} episodes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
