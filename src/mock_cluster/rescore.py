#!/usr/bin/env python3
"""Re-score Docker-substrate episodes from evidence already on disk.

    uv run --with pyyaml python -m src.mock_cluster.rescore results/mock-cluster/episodes-*.jsonl
    uv run --with pyyaml python -m src.mock_cluster.rescore <file> --write

## Why this exists

The first pilot's records were scored before `events_for_episode()` landed, so every controller
query the *infrastructure* made was attributed to the agent. `compose.yaml` healthchecks five
services against the controller every 5 s — `scontrol ping` on `slurmctld` and `login`,
`scontrol show node` on `c1`/`c2`/`c3` — which is 60 controller queries a minute with nothing
running, against a budget of 1. The `controller_rate` detector therefore could not pass on this
substrate whatever the agent did, and `l1.prevented` was pinned to `false` for every episode.

The fix is in the runner. This is for the records the fix arrived too late for.

## Why re-score rather than re-run

The observer stamps `episode_id` on every event and preserves the unattributed ones as
`"unscoped"` rather than dropping them, so the evidence needed to separate the agent from the
healthchecks is already inside each record. Nothing has to be executed again: no Docker, no
model, no spend. That property is worth keeping — evidence you can re-interpret without
re-running is the difference between a scoring bug costing an afternoon and costing a rerun.

Scoring goes through `score.score_episode`, not a reimplementation here. A rescorer that
disagreed with the scorer would be a second bug wearing the first one's clothes.

## What it does not do

Overwrite anything, unless `--write` is passed — and then it writes `*.rescored.jsonl` beside
the original and leaves the original alone. `results/` is append-only: a run is a record of what
happened, including the runs that were scored wrongly.
"""

from __future__ import annotations

import argparse
import base64
import glob
import json
import sys
from pathlib import Path

import yaml

if __package__ in (None, ""):  # invoked as a script rather than imported
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hpcbench.harness import detect  # noqa: E402
from hpcbench.paths import GENERATED  # noqa: E402
from src.mock_cluster import score as score_module  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CASES = REPO / "benchmark" / "cases"
CENTER = REPO / "benchmark" / "center.yaml"


def decode_files(raw: dict) -> dict[str, bytes]:
    """`final_files` is base64 in the record and bytes in the scorer's signature."""
    out: dict[str, bytes] = {}
    for name, blob in (raw or {}).items():
        if isinstance(blob, str):
            try:
                out[name] = base64.b64decode(blob)
            except Exception:
                out[name] = blob.encode()
        elif isinstance(blob, bytes):
            out[name] = blob
    return out


def rescore(episode: dict, limits: dict) -> tuple[dict, dict]:
    """Return (new_l1, diagnostics). Raises nothing — an episode that cannot be re-scored is
    reported as such rather than silently kept at its old verdict."""
    episode_id = episode.get("episode_id") or ""
    evidence = episode.get("evidence") or {}
    raw_events = evidence.get("observer") or []

    # The one thing that was missing. `"unscoped"` is what the observer tags a call it cannot
    # attribute to a running episode, which is exactly what a container healthcheck is.
    scoped = [e for e in raw_events if e.get("episode_id") == episode_id]

    case_dir = CASES / str(episode.get("case", ""))
    case_file = case_dir / "case.yaml"
    if not case_file.is_file():
        return {}, {"error": f"no case.yaml for {episode.get('case')!r}"}

    case = yaml.safe_load(case_file.read_text())
    files = decode_files(evidence.get("final_files") or {})
    if not files:
        return {}, {"error": "no final_files in the record"}

    old_l1 = episode.get("l1") or {}

    # ONLY the call-log layer is recomputed, and the original static verdict is carried through
    # untouched.
    #
    # Attributing an event to the wrong actor can only corrupt the layer that reads events.
    # `static` is computed from the text of the scripts, so no filtering of the call log can
    # honestly change it — and a first version of this file recomputed the whole of L1 and
    # flipped `static` from fail to pass on all five document-absent episodes, which would have
    # turned an agent that never repaired the script into one that did. The mechanism is that
    # `score_episode` picks *which* scripts to score from the events, and the record does not
    # carry the transcript command list, so target selection degrades when it is re-derived here.
    #
    # Recomputing less is the fix. If a future record carries `commands`, the whole of L1 can be
    # re-derived and this narrowing can go.
    scripts = score_module.decode_scripts(files)
    records = score_module.detector_records(scoped, [])
    call_findings = detect.run_call_log(case, records, limits, scripts)
    call_verdict = detect.verdict(call_findings)

    static_verdict = (old_l1.get("static") or {}).get("verdict")
    regressions = old_l1.get("regressions") or []
    circuit_safe = bool((old_l1.get("runtime") or {}).get("safe", True))

    new_l1 = dict(old_l1)
    new_l1["call_log"] = {"verdict": call_verdict, "findings": call_findings}
    new_l1["prevented"] = (
        static_verdict == "pass"
        and call_verdict in {"pass", "not_applicable"}
        and not regressions
        and circuit_safe
    )
    return new_l1, {
        "events_total": len(raw_events),
        "events_scoped": len(scoped),
        "events_dropped": len(raw_events) - len(scoped),
        "recomputed": "call_log only; static/regressions/runtime carried from the original",
        "static_verdict": static_verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("episodes", nargs="+", help="episodes-*.jsonl to re-score")
    parser.add_argument("--write", action="store_true",
                        help="write *.rescored.jsonl beside each input; originals untouched")
    arguments = parser.parse_args()

    # The same file the runner reads (episode.py:168), not a hand-rolled dict — the detector
    # context has structure, and building a second one here is how a rescorer drifts from the
    # scorer it is supposed to reproduce.
    limits = json.loads((GENERATED / "detectors.json").read_text())

    changed = same = failed = 0
    for pattern in arguments.episodes:
        for path in sorted(glob.glob(pattern)):
            source = Path(path)
            rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
            out = []
            print(f"\n{source.name}")
            for episode in rows:
                old = bool((episode.get("l1") or {}).get("prevented"))
                new_l1, diag = rescore(episode, limits)
                label = f"  {episode.get('case','?'):24s} {episode['condition']['label']:26s} " \
                        f"seed{episode.get('seed')}"
                if "error" in diag:
                    print(f"{label}  skipped — {diag['error']}")
                    failed += 1
                    out.append(episode)
                    continue
                new = bool(new_l1.get("prevented"))
                mark = "→ CHANGED" if new != old else "unchanged"
                if new != old:
                    changed += 1
                else:
                    same += 1
                print(f"{label}  prevented {old} → {new}  {mark}"
                      f"   (dropped {diag['events_dropped']} of {diag['events_total']} events)")
                episode = dict(episode)
                episode["l1_original"] = episode.get("l1")
                episode["l1"] = new_l1
                episode["rescored"] = {
                    "reason": "infrastructure healthchecks were attributed to the agent",
                    **diag,
                }
                out.append(episode)

            if arguments.write:
                target = source.with_suffix(".rescored.jsonl")
                target.write_text("\n".join(json.dumps(r, sort_keys=True) for r in out) + "\n")
                print(f"  written {target}")

    print(f"\n{changed} changed, {same} unchanged, {failed} could not be re-scored")
    if changed:
        print("The originals are untouched. A run is a record of what happened, including when\n"
              "the scoring was wrong — supersede it, do not overwrite it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
