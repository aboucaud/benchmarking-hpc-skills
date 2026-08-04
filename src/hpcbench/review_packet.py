#!/usr/bin/env python3
"""#10: everything a sysadmin needs to sign off a case, in one page per case.

    uv run --with pyyaml src/hpcbench/review_packet.py
    uv run --with pyyaml src/hpcbench/review_packet.py --run results/<run>/episodes.judged.jsonl

**0 of 9 cases are signed off**, and until that changes nothing this project has produced is
evidence. The gate is not the obstacle — the obstacle is that reviewing a case currently means
opening six files across two directories, three of which are withheld from agents and none of
which say what the case did when it ran.

So this assembles the packet: the injected defect, the script as the agent receives it, the
remedies that would be accepted and the regressions that would not, the provenance, and — when
given a run — what actually happened, per arm. Then the three questions from #10, and the exact
edit that answers them.

Two things it deliberately will not do:

- **It does not sign anything off.** `review_status` stays `pending` in every case here. The
  gate exists precisely because "someone who has run a facility said this is realistic" is a
  claim no tool and no agent can make on that person's behalf, and a generator that filled in
  `reviewed_by` would be the most direct possible way to defeat it.
- **It does not argue for a verdict.** The observed outcomes are included because #10 names them
  as the thing review should look at — A1, B1 and C2 caught 0/10, which is either a real blind
  spot worth reporting or a sign the case is unrealistic, and those readings call for opposite
  responses. Which one it is, is the reviewer's call; the packet gives them the number and stops.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hpcbench.harness.report import CONDITION_ORDER, endpoint_of, is_scoreable  # noqa: E402
from hpcbench.paths import BENCHMARK  # noqa: E402

QUESTIONS = (
    ("defect_realistic",
     "Would a researcher plausibly submit this, or is it a strawman only a benchmark would "
     "write?"),
    ("rest_of_script_clean",
     "Each case injects exactly one defect. Is anything else — account, partition, walltime, "
     "resources — also wrong? A second defect makes a failure unattributable."),
    ("remedies_complete",
     "Is an obvious fix missing from `accepted_remedies`? This is the likeliest route to a false "
     "negative: marking an agent wrong for choosing a different valid repair."),
)


def outcomes_for(case_id: str, records: list[dict]) -> list[str]:
    """What this case did when it ran, per arm. Empty when no run was supplied."""
    episodes = [r for r in records if r.get("case") == case_id]
    if not episodes:
        return []
    lines = ["| Arm | prevented | note |", "|---|---|---|"]
    by_arm: dict[str, list[dict]] = defaultdict(list)
    for episode in episodes:
        by_arm[episode["condition"]["label"]].append(episode)
    for label in CONDITION_ORDER:
        arm = by_arm.get(label) or []
        if not arm:
            continue
        scored = [e for e in arm if is_scoreable(e) and endpoint_of(e) is not None]
        passed = sum(1 for e in scored if endpoint_of(e))
        # `rejected` is carried because it is the stratifier that decides whether the rate says
        # anything about the agent: the cases caught without the document in the first live run
        # were the ones Slurm refused outright.
        rejected = sum(1 for e in arm if (e.get("evidence") or {}).get("submissions_rejected"))
        note = f"{rejected} had a submission rejected" if rejected else ""
        lines.append(f"| {label} | {passed}/{len(scored)} | {note} |")
    return lines


def case_digest(case_dir: Path) -> str:
    """A hash of everything this packet quotes, so a stale packet cannot pass as current.

    These are committed, because #10's obstacle is that reviewing a case means opening six files
    and a sysadmin should be able to click one — and a committed generated file drifts from its
    source the moment anyone edits a case. Same shape as the intervention stamp: the artefact says
    what it was made from, and a test compares that against the tree.
    """
    accumulator = hashlib.sha256()
    for path in sorted(
        [case_dir / "case.yaml", case_dir / "job.sh", case_dir / "prompt.md"]
        + sorted((case_dir / "assets").iterdir() if (case_dir / "assets").is_dir() else [])
    ):
        if path.is_file():
            accumulator.update(path.name.encode())
            accumulator.update(path.read_bytes())
    return accumulator.hexdigest()[:16]


def packet(case_dir: Path, records: list[dict]) -> str:
    spec = yaml.safe_load((case_dir / "case.yaml").read_text())
    name = case_dir.name
    out = [
        f"# {name} — review packet",
        "",
        f"**{spec.get('title', '')}**",
        "",
        f"Family {spec.get('family')} ({spec.get('family_name')}) · severity "
        f"{spec.get('severity')} · **review_status: {spec.get('review_status')}**",
        "",
        f"<!-- generated by src/hpcbench/review_packet.py from case {case_digest(case_dir)} -->",
        f"_Generated. Regenerate with `uv run --with pyyaml src/hpcbench/review_packet.py`; "
        f"`tests/test_review_gate.py` fails if this is stale against `case.yaml`_ "
        f"(`case {case_digest(case_dir)}`)",
        "",
        "## Where the pattern came from",
        "",
        str(spec.get("provenance", "")).strip() or "_none declared_",
        "",
        "## The guardrail it is written against",
        "",
        str(spec.get("guardrail", "")).strip() or "_none declared_",
        "",
        "## The injected defect",
        "",
        "```yaml",
        yaml.safe_dump(spec.get("injected_defect"), sort_keys=False).strip(),
        "```",
        "",
        "## What the agent is handed",
        "",
    ]
    # Exactly the visible set, so a reviewer reads what an agent reads and not what the harness
    # keeps back. A packet that quietly included `reference.sh` would be reviewing a different
    # object from the one under test.
    for visible in ("prompt.md", "job.sh"):
        if (case_dir / visible).exists():
            out += [f"### `{visible}`", "", "```",
                    (case_dir / visible).read_text().rstrip(), "```", ""]
    assets = case_dir / "assets"
    if assets.is_dir():
        for asset in sorted(p for p in assets.iterdir() if p.is_file()):
            out += [f"### `assets/{asset.name}`", "", "```",
                    asset.read_text().rstrip()[:4000], "```", ""]

    out += ["## What counts as a repair", "",
            "**Accepted remedies** — any one of these passes:", ""]
    for remedy in spec.get("accepted_remedies") or []:
        out.append(f"- `{remedy.get('id')}` — {str(remedy.get('description', '')).strip()}")
    out += ["", "**Forbidden regressions** — these fail even if the defect is gone:", ""]
    for regression in spec.get("forbidden_regressions") or []:
        out.append(f"- `{regression.get('id')}` — {str(regression.get('description', '')).strip()}")

    observed = outcomes_for(name, records)
    if observed:
        out += ["", "## What happened when it ran", "", *observed, "",
                "_Included because #10 names these as what review should look at. A case nothing "
                "catches is either a real blind spot worth reporting or a case that is not "
                "realistic — and those call for opposite responses._"]

    out += [
        "",
        "## The three questions",
        "",
    ]
    for key, question in QUESTIONS:
        out += [f"**`{key}`** — {question}", "", "> ", ""]
    out += [
        "## To sign off",
        "",
        f"In `benchmark/cases/{name}/case.yaml`:",
        "",
        "```yaml",
        "review_status: signed-off",
        "reviewed_by: <name or GitHub handle>",
        "reviewed_on: <YYYY-MM-DD>",
        "reviewed_questions:",
        *[f"  {key}: <yes | no | what you would change>" for key, _ in QUESTIONS],
        "```",
        "",
        "`validate_cases.py` rejects a sign-off missing any of these. An unattributed sign-off is "
        "not a sign-off — this gate decides whether any result here is evidence, so the claim has "
        "to carry a name.",
        "",
        "Answering *no* to any question is a useful review outcome, not a failure: leave "
        "`review_status: pending`, open an issue, and say what you would change.",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, default=None,
                        help="an episodes*.jsonl; adds what each case did when it ran")
    # Outside `benchmark/cases/`, which is not a style preference: `validate_cases.py` treats
    # every directory in there as a case and demanded a `job.sh` from the packet folder. A
    # reviewing artefact that breaks the gate it serves is not much of a packet.
    parser.add_argument("--out", type=Path, default=BENCHMARK.parent / "docs" / "case-review",
                        help="directory to write one packet per case into")
    parser.add_argument("--case", default=None, help="just this one")
    arguments = parser.parse_args()

    records = []
    if arguments.run:
        records = [
            json.loads(line)
            for line in arguments.run.read_text().splitlines() if line.strip()
        ]

    cases = sorted(
        path for path in (BENCHMARK / "cases").iterdir()
        if (path / "case.yaml").exists() and (not arguments.case or path.name == arguments.case)
    )
    if not cases:
        print("no cases matched", file=sys.stderr)
        return 1

    arguments.out.mkdir(parents=True, exist_ok=True)
    index = [
        "# Case review — #10",
        "",
        "A case is not evidence until someone with sysadmin experience has read it. One page per "
        "case below, each carrying the provenance, the injected defect, the script exactly as the "
        "agent receives it, the accepted remedies, and what the case did when it ran.",
        "",
        "**Generated** by `src/hpcbench/review_packet.py`. Each page stamps the digest of the "
        "files it quotes and `tests/test_review_gate.py` fails if one goes stale.",
        "",
        "| Case | Family | Status | Packet |",
        "|---|---|---|---|",
    ]
    pending = []
    for case_dir in cases:
        destination = arguments.out / f"{case_dir.name}.md"
        destination.write_text(packet(case_dir, records))
        spec = yaml.safe_load((case_dir / "case.yaml").read_text())
        status = spec.get("review_status")
        if status != "signed-off":
            pending.append(case_dir.name)
        reviewer = f" ({spec['reviewed_by']})" if spec.get("reviewed_by") else ""
        draft = " · draft" if spec.get("draft") else ""
        index.append(
            f"| `{case_dir.name}` | {spec.get('family')} | **{status}**{reviewer}{draft} | "
            f"[packet]({case_dir.name}.md) |"
        )
        print(f"  {destination.relative_to(BENCHMARK.parent)}")

    index += [
        "",
        f"**{len(pending)} of {len(cases)} unreviewed.** Until that reaches zero, every result "
        f"this project produces is a pilot and its own report says so.",
        "",
    ]
    if not arguments.case:
        # Only when the whole set was regenerated. An index built from one case would list one.
        (arguments.out / "README.md").write_text("\n".join(index))

    print(f"\n{len(pending)} of {len(cases)} cases are unreviewed"
          + (f": {', '.join(pending)}" if pending else ""))
    if not records:
        print("Pass --run to include what each case did when it ran; #10 names those numbers as "
              "the thing review should start from.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
