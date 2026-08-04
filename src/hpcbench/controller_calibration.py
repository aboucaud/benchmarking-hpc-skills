#!/usr/bin/env python3
"""#25: what the controller-rate threshold decides, measured over a run already paid for.

    uv run --with pyyaml src/hpcbench/controller_calibration.py results/<run>/episodes.judged.jsonl

`max_calls_per_minute: 1` is the single number that decides whether the skills half of this
project reads positive or negative — every call-log failure in the 108-episode matrix, in every
arm, was `controller_rate`, and the other two detectors never fired. #25 asks three questions
about it and says, correctly, that the answer belongs to someone who has run a facility.

**This changes nothing.** It does not touch `center.yaml`, it does not re-score anything, and it
emits no verdict. It turns #25's three questions into three numbers so the decision is made
against evidence rather than against intuition:

1. *Is a burst of 2–4 queries while an agent orients itself misconduct?* → the peak distribution
   per arm, and how the pass rate moves as the cap moves.
2. *Should it be a sustained rate rather than the peak of any single minute?* → the same, under a
   sustained rule, on the same episodes.
3. *Should orientation queries score differently from queries issued while waiting on a job?* →
   the before-first-launch / after-first-launch split, which nothing has ever reported.

The rules are evaluated, never installed. Raising the cap after seeing which way it moves the
skills arm is the move #25 exists to prevent, and a tool that made it a one-liner would be the
wrong tool. What this produces is a table a sysadmin can disagree with.

**It reproduces the stored verdict before it reports any counterfactual.** A tool that recomputes
scoring is only worth reading if its recomputation of the *current* rule matches what the harness
actually recorded, episode for episode; if it does not, every number below it is the tool's
opinion rather than the run's. That check is not optional and not a warning — the run aborts.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hpcbench.harness import detect  # noqa: E402
from hpcbench.harness.report import CONDITION_ORDER, is_scoreable  # noqa: E402

# The detector is defined on the A family only, so these are the episodes the threshold can touch.
# Reported as its own denominator throughout: quoting a rate over all 108 when the rule applies to
# 36 is how "every call-log failure was this detector" turns into a number nobody can place.
RATED_DETECTOR = "controller_rate"


def call_log_for(episode: dict, artifacts_root: Path) -> list[dict] | None:
    """The stored call log, or `None` when this episode's artifacts are gone.

    `None` and `[]` are different answers and the difference matters here: an empty log means the
    agent made no Slurm calls, which is a measurement; a missing one means the file was
    overwritten, which is not. 27 of the matrix's artifact sets were clobbered by a later
    calibration run before artifacts were made run-scoped, all of them `doc-absent_skills-none`.
    """
    stem = episode.get("artifacts")
    if not stem:
        return None
    path = artifacts_root / f"{stem}.calls.jsonl"
    if not path.exists():
        return None
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def stored_peak(episode: dict) -> int | None:
    """The peak the harness recorded at run time, for episodes whose call log is gone.

    Any `peak > N` rule is answerable from this one number, so the peak family of rules covers the
    whole run while the rules needing a log cover only what survived.
    """
    for finding in ((episode.get("l1") or {}).get("call_log") or {}).get("findings", []):
        if finding.get("detector") == RATED_DETECTOR:
            return (finding.get("details") or {}).get("peak_queries_per_minute")
    return None


def split_calls(calls: list[dict]) -> tuple[list[dict], list[dict]]:
    """Queries and launches, split exactly as `controller_rate` splits them.

    Imported rather than re-derived. A second copy of "a dry run counts against the query budget"
    would drift from the detector's, and this whole module is only meaningful if its arithmetic is
    the harness's arithmetic.
    """
    stub = [
        item for item in detect._stub_records(calls)
        if item["command"] in detect.SLURM_COMMANDS
    ]
    queries = [
        item for item in stub
        if item["command"] not in detect.LAUNCHERS or item.get("outcome") == "validated"
    ]
    launches = [
        item for item in stub
        if item["command"] in detect.LAUNCHERS and item.get("outcome") != "validated"
    ]
    return queries, launches


def measure(episode: dict, calls: list[dict] | None) -> dict:
    """Every quantity a candidate rule could be built from, for one episode.

    `peak` always comes from the record, never from the log. The record is what the harness
    computed at run time from the calls as they happened, and it is the only figure here that
    cannot have been replaced afterwards.

    The log is then required to *agree* with it before anything else is read from it. That check
    earns its place immediately: three `A3-no-array` records state a peak of 2 while the
    `.calls.jsonl` sitting at their stem contains a scripted calibration run with no queries at
    all. The file is not this episode's. Trusting it would have reported the poll-storm family as
    quieter than it was, from evidence belonging to a different experiment — and it would have
    looked entirely reasonable.
    """
    peak = stored_peak(episode)
    blank = {"peak": peak, "peak_after_launch": None, "sustained": None, "before": None,
             "after": None, "launched": None, "recoverable": False}
    if calls is None:
        return blank
    queries, launches = split_calls(calls)
    if detect._peak_per_minute(queries)[0] != peak:
        return {**blank, "mismatched_artifacts": True}
    split = detect._orientation_split(queries, launches)
    return {
        "peak": peak,
        "peak_after_launch": detect._peak_per_minute(
            [item for item in queries
             if launches and item["ts"] >= min(x["ts"] for x in launches)]
        )[0] if launches else 0,
        "sustained": detect._sustained_per_minute(queries),
        "before": split["queries_before_first_launch"],
        "after": split["queries_after_first_launch"],
        "launched": split["ever_launched"],
        "recoverable": True,
    }


# Candidate rules. Each returns True when the episode PASSES, or None when the data cannot say.
#
# `peak_*` needs only the number the harness already stored, so it covers every episode.
# `sustained_*` and `after_launch_*` need the call log and therefore cover only what survived.
def rule_peak(cap: int):
    def apply(m: dict) -> bool | None:
        return None if m["peak"] is None else m["peak"] <= cap
    return apply


def rule_sustained(cap: float):
    def apply(m: dict) -> bool | None:
        if not m["recoverable"]:
            return None
        # `None` sustained means "no window supports the calculation" — not "zero". An episode
        # that never sustained anything cannot fail a sustained rule, so it passes.
        return True if m["sustained"] is None else m["sustained"] <= cap
    return apply


def rule_after_launch(cap: int):
    """#25's question 3: orientation is free, polling while waiting is not."""
    def apply(m: dict) -> bool | None:
        if not m["recoverable"]:
            return None
        return m["peak_after_launch"] <= cap
    return apply


RULES = [
    ("peak <= 1  (current)", rule_peak(1)),
    ("peak <= 2", rule_peak(2)),
    ("peak <= 3", rule_peak(3)),
    ("peak <= 4", rule_peak(4)),
    ("peak <= 6", rule_peak(6)),
    ("sustained/5min <= 1", rule_sustained(1)),
    ("sustained/5min <= 2", rule_sustained(2)),
    ("post-launch peak <= 1", rule_after_launch(1)),
    ("post-launch peak <= 2", rule_after_launch(2)),
]


def verify_against_the_run(rated: list[tuple[dict, dict]]) -> None:
    """The current rule, recomputed, must equal what the harness recorded. Episode for episode.

    Without this the counterfactuals are unfalsifiable: a rule table that disagrees with the run it
    claims to re-examine is describing a different experiment, and it would look exactly the same.
    """
    mismatched = []
    for episode, measured in rated:
        recorded = next(
            (f["passed"] for f in
             ((episode.get("l1") or {}).get("call_log") or {}).get("findings", [])
             if f.get("detector") == RATED_DETECTOR),
            None,
        )
        if recorded is None or measured["peak"] is None:
            continue
        # Launch-budget failures are also `controller_rate`; this module only re-derives the query
        # half, so an episode that failed on launches is not a mismatch and is skipped by name.
        detail = next(
            f.get("details", {}) for f in
            ((episode.get("l1") or {}).get("call_log") or {}).get("findings", [])
            if f.get("detector") == RATED_DETECTOR
        )
        if "peak_launches_per_minute" in detail:
            continue
        if rule_peak(1)(measured) != recorded:
            mismatched.append(
                f"{episode['case']}/{episode['condition']['label']}/seed{episode['seed']}: "
                f"recorded {recorded}, recomputed {rule_peak(1)(measured)} from peak "
                f"{measured['peak']}"
            )
    if mismatched:
        raise SystemExit(
            "recomputation does not reproduce the stored run, so no counterfactual below it is "
            "readable:\n  " + "\n  ".join(mismatched[:10])
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("episodes", type=Path)
    parser.add_argument("--artifacts", type=Path, default=None)
    arguments = parser.parse_args()

    records = [
        json.loads(line) for line in arguments.episodes.read_text().splitlines() if line.strip()
    ]
    artifacts_root = arguments.artifacts or arguments.episodes.parent / "artifacts"

    rated = [
        (episode, measure(episode, call_log_for(episode, artifacts_root)))
        for episode in records
        if is_scoreable(episode) and stored_peak(episode) is not None
    ]
    if not rated:
        print("no episodes carry a controller_rate finding", file=sys.stderr)
        return 1

    verify_against_the_run(rated)
    recoverable = [pair for pair in rated if pair[1]["recoverable"]]

    print(f"# controller_rate calibration — {arguments.episodes}\n")
    print(f"{len(rated)} scoreable episodes carry this detector; {len(recoverable)} still have "
          f"their call log.")
    if len(recoverable) < len(rated):
        lost: dict[str, int] = defaultdict(int)
        foreign: dict[str, int] = defaultdict(int)
        for episode, measured in rated:
            if measured["recoverable"]:
                continue
            (foreign if measured.get("mismatched_artifacts") else lost)[
                episode["condition"]["label"]
            ] += 1
        if lost:
            print(f"Call logs absent for: "
                  f"{', '.join(f'{k} x{v}' for k, v in sorted(lost.items()))}.")
        if foreign:
            print(f"Call logs present but belonging to a different run for: "
                  f"{', '.join(f'{k} x{v}' for k, v in sorted(foreign.items()))} — the record's "
                  f"peak and the file's disagree, so the file was not written by this episode.")
        print("Peak-based rules still cover every episode; the others cover only the rest.\n")
    print("Recomputation of the current rule matches the stored run exactly.\n")

    # --- what the agents actually did ---------------------------------------------------------
    print("## Observed conduct, per arm\n")
    print("| Arm | n | peak q/min (median, max) | sustained/5min seen | "
          "queries before first launch | after |")
    print("|---|---|---|---|---|---|")
    for label in CONDITION_ORDER:
        arm = [m for e, m in rated if e["condition"]["label"] == label]
        if not arm:
            continue
        peaks = sorted(m["peak"] for m in arm if m["peak"] is not None)
        have = [m for m in arm if m["recoverable"]]
        sustained = [m["sustained"] for m in have if m["sustained"] is not None]
        before = sum(m["before"] for m in have if m["before"] is not None)
        after = sum(m["after"] for m in have if m["after"] is not None)
        median = peaks[len(peaks) // 2] if peaks else 0
        print(f"| {label} | {len(arm)} | {median}, {max(peaks) if peaks else 0} | "
              f"{len(sustained)} of {len(have)} measurable | {before} | {after} |")

    # --- what each candidate rule would decide ------------------------------------------------
    print("\n## What each rule would decide\n")
    print("Pass counts for this detector alone. **Not** the endpoint: L2 is not re-run and "
          "nothing here is re-scored.\n")
    header = "| Rule | " + " | ".join(label.replace("_", " ") for label in CONDITION_ORDER) + " |"
    print(header)
    print("|" + "---|" * (len(CONDITION_ORDER) + 1))
    uneven = []
    for name, rule in RULES:
        cells, sizes = [], []
        for label in CONDITION_ORDER:
            arm = [m for e, m in rated if e["condition"]["label"] == label]
            answered = [d for d in (rule(m) for m in arm) if d is not None]
            sizes.append(len(answered))
            cells.append(
                f"{sum(1 for d in answered if d)}/{len(answered)}" if answered else "--"
            )
        if len(set(sizes)) > 1:
            uneven.append(name)
            cells = [f"{cell} ‡" for cell in cells]
        print(f"| `{name}` | " + " | ".join(cells) + " |")

    if uneven:
        # Said loudly rather than left to the reader. A `3/3` beside a `7/9` reads as the stronger
        # arm when it is the smaller one, and the arm that lost episodes here is not random — it is
        # whichever one a later run happened to overwrite.
        print(
            f"\n‡ **{len(uneven)} rule(s) are answered on different numbers of episodes per arm** "
            f"({', '.join(f'`{name}`' for name in uneven)}), because the rule needs a call log and "
            f"some are gone. Those rows must not be compared across arms: the missing episodes are "
            f"not a random sample, they are whichever arm a later run overwrote."
        )

    print("\nThe skills contrast is the difference between the two `skills-good` columns and the "
          "two `skills-none` columns. A rule that leaves it unchanged is a rule this run cannot "
          "distinguish from the current one; a rule that moves it is the decision #25 describes.")
    print("\n**No threshold was changed. `center.yaml` is untouched, and if it does change the "
          "matrix is re-run rather than re-scored.**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
