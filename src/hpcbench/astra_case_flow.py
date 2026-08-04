"""One "what happened" page per case, generated from the case spec and the episode records.

    uv run --with pyyaml src/hpcbench/astra_case_flow.py results/episodes-*.judged.jsonl

Writes `benchmark/pages/cases/<case>.md` — GENERATED pages, not hand-edited — each carrying:

  - the injected defect, quoted from `case.yaml`;
  - a mermaid flow of what actually happened, with counts taken from the records;
  - the declared ASTRA audit figure for the case;
  - the detector and judge detail behind those counts.

Every number on these pages is counted here, from the records, and nothing is summarised by
a model. That is the point: the audit view is only worth having if a reader can trust that
what it says about a case is what the records say. Prose that *interprets* a case lives in
the hand-written pages instead, and links here.

Two counting rules, both chosen because the obvious alternative would flatter the result:

**Detector counts are per episode, not per finding.** A detector can emit several findings
in one episode — `launches_in_loop` fires once per loop it finds — and counting findings
would report more failures than there were episodes.

**"Submitted nothing" excludes the episodes the harness already credits.** It mirrors
`report.py`'s own `norun` rule, including its exemption for `prevented_without_running`, so
the page and the report cannot disagree about which episodes did no work.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hpcbench.astra_figures import output_id  # noqa: E402
from hpcbench.harness.report import endpoint_of, is_scoreable  # noqa: E402
from hpcbench.paths import BENCHMARK, CASES  # noqa: E402

PAGES = BENCHMARK / "pages" / "cases"

ARMS = [
    ("absent", "none", "no doc, no skills"),
    ("absent", "good", "no doc, skills"),
    ("present", "none", "doc, no skills"),
    ("present", "good", "doc, skills"),
]


def mermaid_escape(text: str) -> str:
    """Mermaid labels are quoted, so quotes and newlines have to go."""
    return " ".join(str(text).replace('"', "'").split())


def first_sentence(text: str, limit: int = 150) -> str:
    flat = " ".join(str(text).split())
    cut = flat.split(". ")[0].rstrip(".")
    return (cut[: limit - 1] + "…") if len(cut) > limit else cut


def detector_failures(episodes: list[dict], source: str) -> Counter:
    """Which detectors failed, counted once per episode each."""
    counts: Counter = Counter()
    for record in episodes:
        block = (record.get("l1") or {}).get(source) or {}
        failed = {f["detector"] for f in block.get("findings", []) if not f.get("passed")}
        counts.update(failed)
    return counts


def submitted_nothing(record: dict) -> bool:
    """`report.py`'s own rule, including the exemption, so the two cannot disagree."""
    return (
        is_scoreable(record)
        and bool(record.get("evidence"))
        and not record["evidence"].get("workload_submitted")
        and not (record.get("l1") or {}).get("prevented_without_running")
    )


def build_page(case_id: str, spec: dict, episodes: list[dict]) -> str:
    defect = first_sentence(spec.get("injected_defect", ""), 190)
    total = len(episodes)

    edited = sum(1 for r in episodes if (r.get("evidence") or {}).get("job_sh_modified"))
    submitted = sum(1 for r in episodes if (r.get("evidence") or {}).get("workload_submitted"))
    nothing = sum(1 for r in episodes if submitted_nothing(r))
    rejected = sum(1 for r in episodes if (r.get("evidence") or {}).get("submissions_rejected"))

    static_fail = detector_failures(episodes, "static")
    call_fail = detector_failures(episodes, "call_log")

    judged = [r for r in episodes if r.get("l2", {}).get("verdict")]
    verdicts = Counter(r["l2"]["verdict"] for r in judged)
    remedies = Counter(r["l2"]["remedy_matched"] for r in judged if r["l2"].get("remedy_matched"))
    regressions = Counter(
        r["l2"]["regression_matched"] for r in judged if r["l2"].get("regression_matched")
    )

    with_reading_remedy = [
        r for r in judged
        if any("remedy_matched" in reading for reading in r["l2"].get("readings", []))
    ]
    remedy_differ = sum(
        1 for r in with_reading_remedy
        if len({reading.get("remedy_matched") for reading in r["l2"]["readings"]
                if "remedy_matched" in reading}) > 1
    )
    remedy_agree = len(with_reading_remedy) - remedy_differ
    disagreements = sum(1 for r in judged if r["l2"].get("disagreement"))

    endpoints = [endpoint_of(r) for r in episodes]
    scored = [e for e in endpoints if e is not None]
    prevented = sum(1 for e in scored if e)

    def detector_line(counts: Counter, label: str) -> str:  # noqa: D401
        if not counts:
            return f"{label}: nothing failed"
        return f"{label}: " + ", ".join(f"{d} failed {n}x" for d, n in counts.most_common())

    static_line = mermaid_escape(detector_line(static_fail, "detectors"))
    call_line = mermaid_escape(detector_line(call_fail, "detectors"))

    lines = [
        "---",
        f'title: "{case_id} — what happened"',
        "---",
        "",
        "<!-- GENERATED by src/hpcbench/astra_case_flow.py from benchmark/cases/"
        f"{case_id}/case.yaml and the judged episode records. Do not hand-edit. -->",
        "",
        f"**{spec.get('family_name', 'family ' + str(spec.get('family', '')))}.** "
        f"{spec.get('title', '')}",
        "",
        f"> **The injected defect.** {defect}.",
        "",
        f"Across **{total} episodes** — four arms at three seeds — this is what the records say "
        "happened. Every count below is taken from those records.",
        "",
        "```{mermaid}",
        "flowchart TB",
        f'  HANDED["job.sh carrying one injected defect<br/>{mermaid_escape(defect)[:110]}"]',
        f'  CONDUCT["{total} episodes<br/>4 arms x 3 seeds"]',
        f'  EDITED["edited the script<br/>{edited} of {total}"]',
        f'  SUBMITTED["submitted work<br/>{submitted} of {total}"]',
        f'  NOTHING["submitted nothing<br/>{nothing} of {total}"]',
        f'  REJECTED["scheduler rejected a submission<br/>{rejected} of {total}"]',
        f'  STATIC["L1 static - the script left behind<br/>{static_line}"]',
        f'  CALLLOG["L1 call log - what the agent did<br/>{call_line}"]',
        f'  JUDGE["L2 judge - {len(judged)} of {total} judged<br/>'
        + mermaid_escape(", ".join(f"{v} {n}x" for v, n in verdicts.most_common()) or "none")
        + '"]',
        f'  ENDPOINT["Endpoint<br/>{prevented} of {len(scored)} scored episodes prevented"]',
        "  HANDED --> CONDUCT",
        "  CONDUCT --> EDITED",
        "  CONDUCT --> SUBMITTED",
        "  CONDUCT --> NOTHING",
        "  SUBMITTED --> REJECTED",
        "  EDITED --> STATIC",
        "  SUBMITTED --> CALLLOG",
        "  NOTHING --> CALLLOG",
        "  STATIC --> JUDGE",
        "  CALLLOG --> JUDGE",
        "  JUDGE --> ENDPOINT",
        "```",
        "",
        "## Outcome by arm",
        "",
        ":::{astra} reporting.outputs." + output_id(case_id),
        ":::",
        "",
        "| Arm | prevented | submitted nothing | rejected | seeds agreed |",
        "|---|---|---|---|---|",
    ]

    for doc, skills, label in ARMS:
        arm = [
            r for r in episodes
            if ("present" if r["condition"]["doc"] else "absent") == doc
            and r["condition"]["skills"] == skills
        ]
        if not arm:
            lines.append(f"| {label} | not run | — | — | — |")
            continue
        arm_endpoints = [e for e in (endpoint_of(r) for r in arm) if e is not None]
        arm_prevented = sum(1 for e in arm_endpoints if e)
        agreed = "no" if 0 < arm_prevented < len(arm_endpoints) else "yes"
        lines.append(
            f"| {label} | {arm_prevented}/{len(arm_endpoints)} "
            f"| {sum(1 for r in arm if submitted_nothing(r))} "
            f"| {sum(1 for r in arm if (r.get('evidence') or {}).get('submissions_rejected'))} "
            f"| {agreed} |"
        )

    lines += ["", "## What the judge matched", ""]
    if not judged:
        lines.append(
            "No episode reached the judge. Under `--l1-pass-only` an L1 failure is not judged, "
            "because it is already a failure — so this case failed the factual layer everywhere."
        )
    else:
        if remedies:
            lines.append("**Accepted remedies matched:** "
                         + ", ".join(f"`{r}` ({n}x)" for r, n in remedies.most_common()) + ".")
            lines.append("")
            # Computed, never assumed. An earlier run showed remedy labels moving between
            # readings while verdicts held, and stating that as a standing caveat put a claim
            # on the page that these records contradict — the readings here agree on the label
            # and it is the *verdict* that occasionally splits. Whichever is true of a run is
            # a property of that run, so it is counted rather than recited.
            lines.append(
                f"Both judge readings agreed on the remedy label in "
                f"{remedy_agree} of {len(with_reading_remedy)} judged episodes that carry one"
                + (f", and differed in {remedy_differ}." if remedy_differ else ".")
            )
        if disagreements:
            lines.append("")
            lines.append(
                f"**{disagreements} of {len(judged)} judged episodes had the two readings "
                "disagree** and went to `needs_review` rather than a tie-break. A coin flip "
                "between two readings is not a third reading."
            )
        if regressions:
            lines.append("")
            lines.append("**Forbidden regressions matched:** "
                         + ", ".join(f"`{r}` ({n}x)" for r, n in regressions.most_common())
                         + ". A matched regression is decisive against an L1 pass.")

    # "Submitted nothing" is only the inaction pattern when the defect was actually averted.
    # An agent that neither edited the script nor submitted it left the defect in place and
    # simply failed; calling that "neither a pass nor a failure" contradicts the same page's
    # own endpoint count.
    norun_records = [r for r in episodes if submitted_nothing(r)]
    norun_prevented = sum(1 for r in norun_records if endpoint_of(r))
    norun_failed = len(norun_records) - norun_prevented
    if not norun_records:
        norun_sentence = f"- **0 of {total}** submitted nothing: every episode ran something."
    else:
        parts = [f"- **{len(norun_records)} of {total}** submitted nothing."]
        if norun_prevented:
            parts.append(
                f"{norun_prevented} of those still scored as preventing the defect — the defect "
                "was averted and no science happened, which is neither a pass nor a failure."
            )
        if norun_failed:
            parts.append(
                f"{norun_failed} left the defect in place and scored as a failure: not editing "
                "the script and not submitting it averts nothing."
            )
        norun_sentence = " ".join(parts)

    lines += [
        "",
        "## Reading this case honestly",
        "",
        f"- **{rejected} of {total}** episodes had a submission rejected by the scheduler. Where "
        "the scheduler pushes back, the agent can learn from the rejection rather than from the "
        "intervention under test.",
        norun_sentence,
        "- Cases carry `review_status: "
        f"{spec.get('review_status', 'unknown')}`. A case nobody with sysadmin experience has "
        "signed off on is not evidence.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episodes", type=Path)
    args = parser.parse_args()

    records = [json.loads(line) for line in args.episodes.read_text().splitlines() if line.strip()]
    by_case: dict[str, list[dict]] = {}
    for record in records:
        by_case.setdefault(record["case"], []).append(record)

    PAGES.mkdir(parents=True, exist_ok=True)
    written = []
    for case_id, episodes in sorted(by_case.items()):
        spec_path = CASES / case_id / "case.yaml"
        if not spec_path.exists():
            print(f"  skip {case_id}: no case.yaml", file=sys.stderr)
            continue
        spec = yaml.safe_load(spec_path.read_text())
        # MyST derives a route from the FILE STEM and flattens directories, so a
        # generated `A3-no-array.md` collides with the hand-written `a3-no-array.md`
        # and silently becomes `/a3-no-array-1`. The prefix keeps routes distinct
        # and, more importantly, stable: which page won the bare slug depended on
        # build order.
        (PAGES / f"case-{case_id}.md").write_text(build_page(case_id, spec, episodes))
        written.append(case_id)
        print(f"  pages/cases/case-{case_id}.md")

    print(f"{len(written)} case pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
