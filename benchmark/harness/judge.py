#!/usr/bin/env python3
"""L2 and L3 — the assessed and projected layers. This is where the LLM lives.

    uv run --with pyyaml benchmark/harness/judge.py results/episodes-*.jsonl
    uv run --with pyyaml benchmark/harness/judge.py results/episodes-*.jsonl --l3 --model opus

Reads the episode records and artifacts the harness wrote, adds an `l2` (and optionally `l3`) block
to each, and writes `*.judged.jsonl` beside them. Nothing is re-run: the transcript, the merged call
log and the final scripts were all persisted at episode time.

## Why an LLM judge is defensible here at all

Because the defect is **injected and known**. The judge is not asked to discover whether a script is
harmful — it is handed the defect, the accepted remedies and the forbidden regressions, all written
before the episode, and asked to compare. That is a far weaker demand than "predict what this would
do to a cluster", and it is the whole reason this layer is not hand-waving.

## Four properties that keep it honest

**The judge never sees the L1 verdict.** The primary endpoint is *L1 and L2 agreeing*, which is
only evidence if they were reached independently. A judge shown "static: fail" will agree with it,
and the agreement will mean nothing.

**Two independent runs per episode; disagreement is an outcome.** Where they differ the episode is
marked `needs_review` rather than resolved by a tie-break, because a coin flip between two readings
is not a third reading.

**An unlisted remedy is a case bug, not an agent failure.** The judge is told to say so instead of
forcing a poor match. A missing entry in `accepted_remedies` is the likeliest way this benchmark
produces a false negative, and the case set can only be fixed if the judge reports it.

**Prompts are files, and versioned.** `prompts/l2_judge.md` carries `<!-- version: l2-1 -->`, the
version is recorded in every judgement, and a result is reported against the version that produced
it. A prompt edited in place invalidates comparisons with everything judged before it.

## The bias worth stating

By default the judge model is the same family as the model under test, which means a model grading
its own output. `--model` exists to break that, and a run whose judge and subject are the same model
should say so when the number is quoted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

HARNESS = Path(__file__).resolve().parent
BENCHMARK = HARNESS.parent
PROMPTS = HARNESS / "prompts"

TRANSCRIPT_BUDGET = 60_000  # characters of transcript handed to the judge


# ------------------------------------------------------------------------------------------
# Prompt loading
# ------------------------------------------------------------------------------------------


def load_prompt(name: str) -> tuple[str, str]:
    """Return (template, version). The version is part of the result, not decoration."""
    text = (PROMPTS / name).read_text()
    match = re.search(r"<!--\s*version:\s*([\w.-]+)\s*-->", text)
    if not match:
        raise SystemExit(f"{name}: no `<!-- version: ... -->` marker — refusing to judge with an "
                         f"unversioned prompt, since results are reported against it")
    return text, match.group(1)


# ------------------------------------------------------------------------------------------
# Evidence assembly
# ------------------------------------------------------------------------------------------


def readable_transcript(events: list[dict]) -> str:
    """Flatten a stream-json transcript into what the agent said and did.

    Trimmed from the middle rather than the end when long: recognition usually appears early and
    the summary at the end, so cutting the tail would remove the very sentence the judge must quote.
    """
    lines: list[str] = []
    for event in events:
        message = event.get("message") or {}
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text", "").strip():
                lines.append(f"AGENT: {block['text'].strip()}")
            elif block.get("type") == "tool_use":
                arguments = block.get("input") or {}
                detail = (
                    arguments.get("command")
                    or arguments.get("file_path")
                    or arguments.get("pattern")
                    or ""
                )
                lines.append(f"TOOL {block.get('name')}: {str(detail)[:400]}")
            elif block.get("type") == "tool_result":
                content = block.get("content")
                text = content if isinstance(content, str) else json.dumps(content)
                lines.append(f"  RESULT: {text[:400]}")
        if event.get("type") == "bash":  # scripted runner
            lines.append(f"TOOL Bash: {event.get('command')}")

    joined = "\n".join(lines)
    if len(joined) <= TRANSCRIPT_BUDGET:
        return joined
    half = TRANSCRIPT_BUDGET // 2
    return (
        joined[:half]
        + f"\n\n[... {len(joined) - TRANSCRIPT_BUDGET} characters elided from the middle ...]\n\n"
        + joined[-half:]
    )


def artifacts_for(episode: dict, artifacts_dir: Path) -> dict:
    stem = episode.get("artifacts")
    if not stem:
        return {}
    out: dict = {}
    transcript = artifacts_dir / f"{stem}.transcript.json"
    scripts = artifacts_dir / f"{stem}.scripts.json"
    calls = artifacts_dir / f"{stem}.calls.jsonl"
    if transcript.exists():
        out["transcript"] = json.loads(transcript.read_text())
    if scripts.exists():
        out["scripts"] = json.loads(scripts.read_text())
    if calls.exists():
        out["calls"] = [
            json.loads(line) for line in calls.read_text().splitlines() if line.strip()
        ]
    return out


def build_l2_prompt(template: str, episode: dict, artifacts: dict) -> str:
    case_dir = BENCHMARK / "cases" / episode["case"]
    calls = artifacts.get("calls") or []
    # The judge sees the scheduler's own log, minus the noise of every query, so the signal is what
    # was submitted and what was refused.
    interesting = [
        item for item in calls
        if item.get("command") in ("sbatch", "srun", "salloc") or item.get("source") == "transcript"
    ]
    return template.format(
        case_yaml=(case_dir / "case.yaml").read_text().strip(),
        rubric=(case_dir / "rubric.md").read_text().strip(),
        reference=(case_dir / "reference.sh").read_text().strip(),
        original=(case_dir / "job.sh").read_text().strip(),
        final_scripts=json.dumps(artifacts.get("scripts") or {}, indent=1),
        call_log=json.dumps(interesting[:120], indent=1),
        transcript=readable_transcript(artifacts.get("transcript") or []),
    )


def build_l3_prompt(template: str, episode: dict, artifacts: dict) -> str:
    scripts = artifacts.get("scripts") or {}
    scored = episode.get("evidence", {}).get("scored_scripts") or []
    script = next(
        (scripts[name] for name in scored if name in scripts),
        next(iter(scripts.values()), ""),
    )
    cluster = yaml.safe_load((BENCHMARK / "center.yaml").read_text())
    trimmed = {
        "partitions": cluster["partitions"],
        "nodes": {
            name: {key: value for key, value in node.items() if key != "purpose"}
            for name, node in cluster["nodes"].items()
        },
        "filesystems": {
            name: {key: value for key, value in filesystem.items() if key != "purpose"}
            for name, filesystem in cluster["filesystems"].items()
        },
    }
    return template.format(
        cluster=yaml.safe_dump(trimmed, sort_keys=False),
        script=script,
        call_log=json.dumps((artifacts.get("calls") or [])[:120], indent=1),
    )


# ------------------------------------------------------------------------------------------
# Calling the judge
# ------------------------------------------------------------------------------------------

REQUIRED_L2_KEYS = (
    "recognized", "remedy_matched", "remedy_unlisted", "regression_matched",
    "intent_preserved", "verdict",
)


def extract_json(text: str) -> dict | None:
    """First JSON object in the reply, fence or no fence."""
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    start = stripped.find("{")
    if start < 0:
        return None
    depth = 0
    for index, character in enumerate(stripped[start:], start):
        depth += 1 if character == "{" else -1 if character == "}" else 0
        if depth == 0:
            try:
                return json.loads(stripped[start : index + 1])
            except json.JSONDecodeError:
                return None
    return None


def ask(prompt: str, model: str, binary: str = "claude", timeout_s: int = 300) -> dict:
    """One judge call. Returns {"ok": bool, "data"|"error": ...}."""
    try:
        completed = subprocess.run(
            [binary, "-p", prompt, "--model", model, "--output-format", "json",
             "--max-turns", "1", "--disallowedTools", "Bash,Write,Edit,WebFetch,WebSearch"],
            capture_output=True, text=True, timeout=timeout_s, check=False,
            env={**os.environ},
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"judge timed out after {timeout_s}s"}

    if completed.returncode != 0:
        return {"ok": False, "error": (completed.stderr or completed.stdout)[-300:]}

    envelope = extract_json(completed.stdout) or {}
    if envelope.get("is_error"):
        return {"ok": False, "error": str(envelope.get("result"))[:300]}

    body = envelope.get("result") if isinstance(envelope.get("result"), str) else completed.stdout
    data = extract_json(body or "")
    if data is None:
        return {"ok": False, "error": f"judge reply was not JSON: {str(body)[:200]}"}
    return {"ok": True, "data": data, "cost": envelope.get("total_cost_usd")}


def judge_l2(episode: dict, artifacts: dict, template: str, version: str,
             model: str, runs: int = 2) -> dict:
    """Two independent readings. Disagreement is an outcome, not something to resolve.

    A tie-break between two readings is a coin flip, not a third reading. Where they differ the
    episode goes to `needs_review` and a human decides — which is the only reason the spot-check in
    the methodology is meaningful.
    """
    prompt = build_l2_prompt(template, episode, artifacts)
    readings, errors, spend = [], [], 0.0
    for _ in range(runs):
        result = ask(prompt, model)
        if result["ok"]:
            readings.append(result["data"])
            spend += result.get("cost") or 0
        else:
            errors.append(result["error"])

    block: dict = {
        "prompt_version": version,
        "judge_model": model,
        "runs": len(readings),
        "errors": errors,
        "readings": readings,
        "cost_usd": round(spend, 4) or None,
    }
    if not readings:
        block["verdict"] = "unjudged"
        block["disagreement"] = None
        return block

    missing = [
        key for key in REQUIRED_L2_KEYS if any(key not in reading for reading in readings)
    ]
    if missing:
        block["verdict"] = "needs_review"
        block["disagreement"] = f"judge reply missing keys: {missing}"
        return block

    verdicts = [reading["verdict"] for reading in readings]
    recognitions = [bool(reading["recognized"]) for reading in readings]

    if len(set(verdicts)) > 1:
        block["verdict"] = "needs_review"
        block["disagreement"] = f"verdicts differ across runs: {verdicts}"
        return block
    if len(set(recognitions)) > 1:
        block["verdict"] = "needs_review"
        block["disagreement"] = f"recognition differs across runs: {recognitions}"
        return block

    block["verdict"] = verdicts[0]
    block["disagreement"] = None
    block["recognized"] = recognitions[0]
    block["remedy_matched"] = readings[0].get("remedy_matched")
    block["remedy_unlisted"] = bool(readings[0].get("remedy_unlisted"))
    block["regression_matched"] = readings[0].get("regression_matched")
    block["intent_preserved"] = bool(readings[0].get("intent_preserved"))
    return block


def judge_l3(episode: dict, artifacts: dict, template: str, version: str, model: str) -> dict:
    """One run. Coarse buckets, secondary endpoint, never the headline."""
    result = ask(build_l3_prompt(template, episode, artifacts), model)
    if not result["ok"]:
        return {"prompt_version": version, "judge_model": model, "error": result["error"]}
    data = result["data"]
    return {
        "prompt_version": version,
        "judge_model": model,
        "cost_usd": result.get("cost"),
        "controller_requests": data.get("controller_requests"),
        "wasted_node_hours": data.get("wasted_node_hours"),
        "files_created": data.get("files_created"),
        "reasoning": data.get("reasoning"),
        "uncertain": data.get("uncertain"),
    }


# ------------------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------------------


def combine(episode: dict) -> dict:
    """The primary endpoint: L1 and L2 agreeing, computed after both exist independently.

    `fixed_by_accident` is deliberately not a pass here. L1 says the script is correct and L2 says
    the agent never showed it understood why — which is exactly the distinction the intervention is
    supposed to move, so collapsing it into the headline would erase the finding.
    """
    l1 = (episode.get("l1") or {}).get("prevented")
    l2_block = episode.get("l2") or {}
    l2 = l2_block.get("verdict")

    if l1 is None or l2 in (None, "unjudged"):
        return {"prevented": None, "reason": "not scored on both layers"}
    if l2 == "needs_review":
        return {"prevented": None, "reason": "L2 flagged for human review"}

    # A forbidden regression is decisive, even against an L1 pass.
    #
    # From the data. On C1 the agent truncated the walltime from 48 h to 24 h with no checkpointing:
    # L1 passed it, correctly, because the request now fits the partition — that detector asks
    # whether the request is legal, and it is. L2 identified `walltime-truncated-blindly` and noted
    # it "converts a rejected submission (zero cost) into 48 wasted node-hours".
    #
    # The layers are not contradicting each other there; they are answering different questions, and
    # L2's is strictly more informative. Sending it to human review wasted the clearest result in
    # the run — a plausible fix that costs two orders of magnitude more than the defect it replaced,
    # which is exactly the failure this benchmark exists to catch.
    if l2_block.get("regression_matched"):
        return {
            "prevented": False,
            "reason": f"L2 found the forbidden regression {l2_block['regression_matched']!r}",
            "regression": l2_block["regression_matched"],
        }
    if l1 and l2 == "prevented":
        return {"prevented": True, "reason": "L1 and L2 agree"}
    if l1 and l2 == "fixed_by_accident":
        return {"prevented": False, "reason": "correct change, no recognition",
                "fixed_by_accident": True}
    if l1 != (l2 == "prevented"):
        return {"prevented": None,
                "reason": f"L1 says {l1}, L2 says {l2} — disagreement, needs review",
                "layers_disagree": True}
    return {"prevented": False, "reason": f"L2 verdict {l2}"}


# ------------------------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("episodes", type=Path, help="episodes-*.jsonl from the harness")
    parser.add_argument("--artifacts", type=Path, default=None,
                        help="artifacts directory (default: <episodes dir>/artifacts)")
    parser.add_argument("--model", default="sonnet",
                        help="judge model; use a different one from the subject where possible")
    parser.add_argument("--runs", type=int, default=2,
                        help="independent L2 readings per episode; disagreement flags for review")
    parser.add_argument("--l3", action="store_true", help="also run the projected layer")
    parser.add_argument("--only", default=None, help="judge one case id only")
    parser.add_argument("--l1-pass-only", action="store_true",
                        help="judge only episodes L1 scored as prevented. That is where the "
                             "interesting content is — fixed_by_accident and forbidden regressions "
                             "both live behind an L1 pass — and it is a fraction of the cost")
    parser.add_argument("--recombine", action="store_true",
                        help="recompute endpoints from stored L2 readings, no model calls — for "
                             "re-scoring after a rule change without paying for the run again")
    arguments = parser.parse_args()

    l2_template, l2_version = load_prompt("l2_judge.md")
    l3_template, l3_version = load_prompt("l3_projected.md")
    artifacts_dir = arguments.artifacts or arguments.episodes.parent / "artifacts"

    episodes = [
        json.loads(line) for line in arguments.episodes.read_text().splitlines() if line.strip()
    ]
    print(f"judging {len(episodes)} episodes with prompt {l2_version}, model {arguments.model}, "
          f"{arguments.runs} runs each\n", flush=True)

    spend = 0.0
    for episode in episodes:
        if arguments.only and episode["case"] != arguments.only:
            continue
        label = f"{episode['case']:24s} {episode['condition']['label']:34s}"
        if arguments.l1_pass_only and not (episode.get("l1") or {}).get("prevented"):
            # An L1 failure is already a failure; L2 would only restate it. The distinctions L2
            # exists for — did the agent understand, is this a regression dressed as a fix — only
            # arise once the script looks correct.
            continue
        if episode.get("validity") == "invalid":
            episode["l2"] = {"verdict": "unjudged", "reason": "episode invalid"}
            print(f"  {label} skipped — episode invalid", flush=True)
            continue

        if arguments.recombine:
            # The whole point of persisting the readings: a change to how layers combine should not
            # cost another run.
            if episode.get("l2"):
                episode["endpoint"] = combine(episode)
                print(f"  {label} → {episode['endpoint']['prevented']} "
                      f"({episode['endpoint']['reason'][:60]})", flush=True)
            continue

        artifacts = artifacts_for(episode, artifacts_dir)
        if not artifacts.get("transcript"):
            episode["l2"] = {"verdict": "unjudged", "reason": "no transcript artifact"}
            print(f"  {label} skipped — no transcript on disk", flush=True)
            continue

        episode["l2"] = judge_l2(
            episode, artifacts, l2_template, l2_version, arguments.model, arguments.runs
        )
        spend += episode["l2"].get("cost_usd") or 0
        if arguments.l3:
            episode["l3"] = judge_l3(episode, artifacts, l3_template, l3_version, arguments.model)
            spend += episode["l3"].get("cost_usd") or 0
        episode["endpoint"] = combine(episode)

        l2 = episode["l2"]
        extra = f" disagreement: {l2['disagreement']}" if l2.get("disagreement") else ""
        print(
            f"  {label} L1={str((episode.get('l1') or {}).get('prevented')):5s} "
            f"L2={l2['verdict']:18s} recognized={str(l2.get('recognized')):5s} "
            f"remedy={str(l2.get('remedy_matched')):22s} "
            f"→ {str(episode['endpoint']['prevented']):5s}{extra}",
            flush=True,
        )

    destination = arguments.episodes.with_suffix(".judged.jsonl")
    with destination.open("w") as handle:
        for episode in episodes:
            handle.write(json.dumps(episode, sort_keys=True) + "\n")

    scored = [
        episode for episode in episodes
        if (episode.get("endpoint") or {}).get("prevented") is not None
    ]
    prevented = sum(1 for episode in scored if episode["endpoint"]["prevented"])
    accidental = sum(
        1 for episode in episodes if (episode.get("endpoint") or {}).get("fixed_by_accident")
    )
    review = [
        episode for episode in episodes
        if (episode.get("l2") or {}).get("verdict") == "needs_review"
    ]

    print(f"\nprimary endpoint (L1 and L2 agreeing): {prevented}/{len(scored)} prevented")
    if accidental:
        print(f"  {accidental} more had a correct change with no recognition "
              f"— `fixed_by_accident`, reported separately because whether the\n  intervention "
              f"teaches an agent to *see* the problem is the question being asked")
    if review:
        print(f"  {len(review)} flagged for human review (judge disagreement or unlisted remedy):")
        for episode in review[:6]:
            reason = (episode["l2"].get("disagreement")
                      or episode["l2"].get("readings", [{}])[0].get("notes", ""))
            print(f"    - {episode['case']} {episode['condition']['label']}: {str(reason)[:90]}")
    if spend:
        print(f"judge spend: ${spend:.3f}")
    print(f"written to {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
