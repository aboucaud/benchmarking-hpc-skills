#!/usr/bin/env python3
"""Turn judged episodes into a report a reader can argue with.

    uv run --with pyyaml benchmark/harness/report.py results/episodes-*.judged.jsonl
    uv run --with pyyaml benchmark/harness/report.py results/*.judged.jsonl > report.md

**Per case, not just a rate.** The methodology is explicit about this: at nine cases and three seeds
the interesting content is *which* cases an intervention catches, not a percentage with a confidence
interval it cannot support. A single number here would be the least informative thing the data can
produce, and the most quotable — so this prints the grid first and the aggregate last.

Four things are always shown, because each of them can turn a good-looking number into nothing:

  - **excluded episodes**, with reasons. A rate whose denominator quietly shrank is not a rate.
  - **`fixed_by_accident`**, separately. A correct change with no sign the agent understood why is
    not evidence that anything was taught.
  - **`prevented_without_running`**, separately. Averting the defect by doing no work is not a fix.
  - **the pushback split**. The only cases caught without the document in the first live run were
    the two whose submission the scheduler rejected outright, so a doc-versus-no-doc number that
    ignores that stratum is measuring Slurm as much as the agent.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

CONDITION_ORDER = (
    "doc-absent_skills-none", "doc-absent_skills-good",
    "doc-present_skills-none", "doc-present_skills-good",
)

SYMBOLS = {
    True: "PASS",
    False: "fail",
    None: " -- ",
}


def load(patterns: list[str]) -> list[dict]:
    episodes: list[dict] = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            for line in Path(path).read_text().splitlines():
                if line.strip():
                    episodes.append(json.loads(line))
    return episodes


def endpoint_of(episode: dict) -> bool | None:
    """The primary endpoint if judged, else the L1-only reading, labelled as such by the caller."""
    if "endpoint" in episode:
        return episode["endpoint"].get("prevented")
    return (episode.get("l1") or {}).get("prevented")


def summarize_cell(group: list[dict]) -> str:
    """One cell, however many seeds it holds.

    With several seeds the useful thing is `k/n` plus whether the cell was stable, not a comma-run
    of verdicts. At one seed per cell an outcome and a coin flip look identical, which is the whole
    reason for running more than one.
    """
    if not group:
        return " -- "
    if len(group) == 1:
        return cell(group[0])

    scored = [episode for episode in group if endpoint_of(episode) is not None]
    passed = sum(1 for episode in scored if endpoint_of(episode))
    text = f"{passed}/{len(scored)}" if scored else "0/0"
    if len(scored) < len(group):
        text += f" ({len(group) - len(scored)} n/s)"
    if scored and passed not in (0, len(scored)):
        text += " UNSTABLE"
    # Counted, not merely present. A bare `[idle]` on a 5/5 cell does not say whether one seed or
    # all five submitted nothing, and reading it as "all of them" is a mistake I made on this very
    # report — B3 showed `[idle]` at 5/5 and three of the ten passes had actually submitted work.
    tally: dict[str, int] = {}
    for episode in group:
        for mark in cell_marks(episode):
            tally[mark] = tally.get(mark, 0) + 1
    detail = ",".join(
        f"{mark}x{count}" if count > 1 else mark for mark, count in sorted(tally.items())
    )
    return text + (f" [{detail}]" if detail else "")


def cell_marks(episode: dict) -> list[str]:
    marks = []
    if (episode.get("endpoint") or {}).get("fixed_by_accident"):
        marks.append("acc")
    if (episode.get("l1") or {}).get("prevented_without_running"):
        marks.append("idle")
    elif (
        episode.get("validity") != "invalid"
        and episode.get("evidence")
        and not episode["evidence"].get("workload_submitted")
    ):
        marks.append("norun")
    if episode.get("validity") == "partial":
        marks.append("part")
    if (episode.get("l2") or {}).get("verdict") == "needs_review":
        marks.append("rev")
    return marks


def cell(episode: dict) -> str:
    value = endpoint_of(episode)
    text = SYMBOLS[value] if value in SYMBOLS else str(value)
    marks = cell_marks(episode)
    return text + (f"({','.join(marks)})" if marks else "")


def report(episodes: list[dict]) -> str:
    lines: list[str] = []
    judged = any("endpoint" in episode for episode in episodes)
    models = sorted({str(episode.get("model")) for episode in episodes})
    judges = sorted({
        str((episode.get("l2") or {}).get("judge_model"))
        for episode in episodes if episode.get("l2")
    } - {"None"})
    versions = sorted({
        str((episode.get("l2") or {}).get("prompt_version"))
        for episode in episodes if episode.get("l2")
    } - {"None"})

    lines.append("# Misuse-repair benchmark — results")
    lines.append("")
    lines.append(
        f"{len(episodes)} episode{'s' if len(episodes) != 1 else ''} · "
        f"subject model {', '.join(models)}"
        + (f" · judge {', '.join(judges)} (prompt {', '.join(versions)})" if judges else "")
    )
    lines.append("")

    # The review gate, restated wherever a result is read rather than only where it was run.
    unsigned = {
        episode["case"] for episode in episodes
        if episode.get("case_review_status") not in (None, "signed-off")
    }
    drafts = {episode["case"] for episode in episodes if episode.get("case_draft")}
    if unsigned:
        lines.append(
            f"> **{len(unsigned)} of {len({e['case'] for e in episodes})} cases have no sysadmin "
            f"sign-off.** The review gate is a rule in this project: a case nobody with sysadmin "
            f"experience has signed off on is not evidence. Read this as a pilot."
        )
        lines.append("")
    if drafts:
        lines.append(
            f"> **Includes draft case(s): {', '.join(sorted(drafts))}.** Drafts are excluded from "
            f"`episode.py all` and were run deliberately. A draft has been seen by nobody but its "
            f"author."
        )
        lines.append("")
    if judged and judges and set(judges) & set(models):
        lines.append(
            "> **The judge and the subject are the same model.** A model grading its own output "
            "flatters it. Re-run the judge with a different `--model` before treating any number "
            "here as external."
        )
        lines.append("")
    if not judged:
        lines.append(
            "> **L1 only — not the primary endpoint.** These records have not been judged, so "
            "nothing here distinguishes an agent that understood the problem from one that fixed "
            "it by accident. Run `judge.py` over them."
        )
        lines.append("")
    else:
        # Partial judging has to announce itself. With `--l1-pass-only` the L1 failures carry no L2
        # block at all and fall back to their L1 verdict, which is the right scoring — but a report
        # that stayed silent would imply the judge had looked at everything.
        unjudged = [episode for episode in episodes if "endpoint" not in episode]
        if unjudged:
            lines.append(
                f"> **Partial L2 coverage.** {len(episodes) - len(unjudged)} of {len(episodes)} "
                f"episodes were judged; the other {len(unjudged)} are scored on L1 alone. That is "
                f"deliberate when judging only L1 passes — an L1 failure is already a failure and "
                f"L2 would restate it — but it means `fixed_by_accident` and forbidden regressions "
                f"were only looked for where L1 said pass."
            )
            lines.append("")

    # ---- the grid -------------------------------------------------------------------------
    grid: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for episode in episodes:
        grid[episode["case"]][episode["condition"]["label"]].append(episode)
    conditions = [
        label for label in CONDITION_ORDER
        if any(label in per_case for per_case in grid.values())
    ]

    header = f"| {'Case':24s} | " + " | ".join(f"{label:26s}" for label in conditions) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(conditions) + 1))
    for case in sorted(grid):
        marker = " (draft)" if case in drafts else ""
        cells = []
        for label in conditions:
            cells.append(summarize_cell(grid[case].get(label, [])))
        label_text = f"`{case}`{marker}"
        lines.append(f"| {label_text:30s} | " + " | ".join(f"{text:26s}" for text in cells) + " |")
    lines.append("")
    lines.append(
        "`acc` = correct change, no recognition · `idle` = prevented but nothing submitted · "
        "`norun` = nothing submitted · `part` = run ended abnormally · `rev` = needs human review"
    )
    lines.append("")

    # ---- instability ----------------------------------------------------------------------
    unstable = []
    for case in sorted(grid):
        for label in conditions:
            group = grid[case].get(label, [])
            scored = [episode for episode in group if endpoint_of(episode) is not None]
            if len(scored) > 1:
                passed = sum(1 for episode in scored if endpoint_of(episode))
                if passed not in (0, len(scored)):
                    unstable.append((case, label, passed, len(scored)))
    if unstable:
        lines.append(f"## Unstable across seeds: {len(unstable)} cell(s)")
        lines.append("")
        lines.append(
            "Same case, same condition, different outcome. At one seed per cell these are "
            "indistinguishable from findings, which is why a single-seed grid should not be read "
            "as one: a cell that flips is evidence about variance, not about the intervention."
        )
        lines.append("")
        for case, label, passed, total in unstable:
            lines.append(f"- `{case}` {label} — {passed}/{total}")
        lines.append("")

    # ---- what was excluded ----------------------------------------------------------------
    excluded = [episode for episode in episodes if episode.get("validity") == "invalid"]
    if excluded:
        lines.append(f"## Excluded: {len(excluded)} of {len(episodes)}")
        lines.append("")
        lines.append("A rate whose denominator quietly shrank is not a rate.")
        lines.append("")
        for episode in excluded:
            lines.append(
                f"- `{episode['case']}` {episode['condition']['label']} — "
                f"{episode.get('invalid_reason', '')[:110]}"
            )
        lines.append("")

    # ---- outcomes that are not passes -----------------------------------------------------
    accidental = [
        episode for episode in episodes
        if (episode.get("endpoint") or {}).get("fixed_by_accident")
    ]
    idle = [
        episode for episode in episodes
        if (episode.get("l1") or {}).get("prevented_without_running")
    ]
    review = [
        episode for episode in episodes
        if (episode.get("l2") or {}).get("verdict") == "needs_review"
        or (episode.get("endpoint") or {}).get("layers_disagree")
    ]

    if accidental:
        lines.append(f"## Fixed by accident: {len(accidental)}")
        lines.append("")
        lines.append(
            "Correct change, no sign the agent understood why. Reported apart from the headline "
            "because whether an intervention teaches an agent to *see* the problem is the question "
            "being asked."
        )
        lines.append("")
        for episode in accidental:
            lines.append(f"- `{episode['case']}` {episode['condition']['label']}")
        lines.append("")

    norun = [
        episode for episode in episodes
        if episode.get("validity") != "invalid" and episode.get("evidence")
        and not episode["evidence"].get("workload_submitted")
        and not (episode.get("l1") or {}).get("prevented_without_running")
    ]
    if norun:
        lines.append(f"## Submitted nothing: {len(norun)}")
        lines.append("")
        lines.append(
            "Flagged whatever the verdict, because an episode where the workload never ran can "
            "look like good conduct. A skills-arm run of A2 scored `call_log=pass` in both doc "
            "conditions — apparently the skill preventing a poll storm. It was the agent spending "
            "its whole budget trying to configure a CLI for a host that does not exist and never "
            "reaching the scheduler at all. Zero controller calls reads identically to restraint."
        )
        lines.append("")
        for episode in norun:
            lines.append(f"- `{episode['case']}` {episode['condition']['label']}")
        lines.append("")

    if idle:
        lines.append(f"## Prevented without running anything: {len(idle)}")
        lines.append("")
        lines.append(
            "The defect was averted and the work was not done. An agent that reliably lands here "
            "has learned to refuse, not to fix."
        )
        lines.append("")
        for episode in idle:
            lines.append(f"- `{episode['case']}` {episode['condition']['label']}")
        lines.append("")

    if review:
        lines.append(f"## Needs human review: {len(review)}")
        lines.append("")
        for episode in review:
            reason = (
                (episode.get("l2") or {}).get("disagreement")
                or (episode.get("endpoint") or {}).get("reason")
                or ""
            )
            lines.append(
                f"- `{episode['case']}` {episode['condition']['label']} — {str(reason)[:110]}"
            )
        lines.append("")

    # ---- stratification -------------------------------------------------------------------
    lines.append("## Was the agent pushed back on?")
    lines.append("")
    lines.append(
        "In the first live run the only cases caught without the document were the two whose "
        "submission the scheduler rejected outright. A doc-versus-no-doc number that ignores this "
        "split is measuring Slurm as much as the agent."
    )
    lines.append("")
    lines.append("| Stratum | Prevented |")
    lines.append("|---|---|")
    for label, predicate in (
        ("scheduler rejected something", lambda e: e["evidence"]["submissions_rejected"] > 0),
        ("no pushback", lambda e: e["evidence"]["submissions_rejected"] == 0),
    ):
        group = [
            episode for episode in episodes
            if episode.get("validity") != "invalid"
            and episode.get("evidence")
            and predicate(episode)
        ]
        scored = [episode for episode in group if endpoint_of(episode) is not None]
        caught = sum(1 for episode in scored if endpoint_of(episode))
        lines.append(f"| {label} | {caught}/{len(scored)} |")
    lines.append("")

    # ---- per-arm aggregate, last --------------------------------------------------------
    lines.append("## Aggregate, per arm")
    lines.append("")
    for label in conditions:
        group = [episode for episode in episodes if episode["condition"]["label"] == label]
        scored = [episode for episode in group if endpoint_of(episode) is not None]
        caught = sum(1 for episode in scored if endpoint_of(episode))
        excluded_here = len(group) - len(scored)
        note = f" ({excluded_here} not scored)" if excluded_here else ""
        lines.append(f"- **{label}**: {caught}/{len(scored)} prevented{note}")
    lines.append("")

    spend = sum((episode.get("cost") or {}).get("usd") or 0 for episode in episodes)
    judge_spend = sum((episode.get("l2") or {}).get("cost_usd") or 0 for episode in episodes)
    judge_spend += sum((episode.get("l3") or {}).get("cost_usd") or 0 for episode in episodes)
    if spend or judge_spend:
        lines.append(
            f"Spend: ${spend:.2f} running, ${judge_spend:.2f} judging, "
            f"${spend + judge_spend:.2f} total."
        )
        lines.append("")

    lines.append("## What this does not measure")
    lines.append("")
    lines.append(
        "- **Repair, not restraint.** The agent is handed a bad script. It is never asked to write "
        "one, so nothing here shows whether it would have made the same mistake itself."
    )
    lines.append(
        "- **Nothing executed.** No node was allocated and no file written; family B is scored "
        "from the text of the script, and every L3 figure is a projection."
    )
    lines.append(
        "- **One seed per cell** unless stated. Per-case outcomes above are the result; an "
        "aggregate at this sample size is decoration."
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("episodes", nargs="+", help="episodes*.jsonl, judged or not")
    arguments = parser.parse_args()

    episodes = load(arguments.episodes)
    if not episodes:
        raise SystemExit("no episodes matched")
    print(report(episodes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
