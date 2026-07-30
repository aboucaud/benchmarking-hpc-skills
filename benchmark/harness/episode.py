#!/usr/bin/env python3
"""Run one episode: materialize a condition, let an agent act, collect the evidence, score L1.

    # inspect a condition without running an agent
    uv run --with pyyaml benchmark/harness/episode.py C3-wrong-partition --runner noop --keep

    # the full 2x2 for one case, with scripted conduct
    uv run --with pyyaml benchmark/harness/episode.py C3-wrong-partition --matrix --seeds 3

An episode is a case, a condition, and a seed. The condition is the 2x2 the benchmark turns on:

    doc     ∈ {absent, present}    is the center's INSTRUCTIONS.md in the sandbox
    skills  ∈ {none, good}         are the HPC skills under test installed

Nothing here reaches a cluster. The sandbox's PATH puts the echo stubs first, and the case
scripts are never executed by anything but the agent's own choices.

## What the agent may see

Only `job.sh`, `prompt.md` and the contents of `assets/`. Not `case.yaml`, not `reference.sh`, not
`rubric.md` — an agent that can read the rubric is measuring nothing, and this is the one property
of the harness that cannot be recovered after the fact, so it is asserted at materialization time
rather than trusted.

## What gets scored, and on which script

**Every script the agent executed, and every script it submitted** — not whatever happens to be
named `job.sh`. Both halves of that rule were learned from getting it wrong; see `scoring_targets`.

## Calibration

Two runs bound the measurement, and both are checked in `test_harness.py`:

    --runner scripted-asis        do nothing, run the script as handed over  → 0/9 prevented
    --runner scripted-reference   apply the case's reference remedy          → 9/9 prevented

A detector set that cannot produce both numbers is not measuring the defect. `scripted-reference`
uses withheld ground truth, so it is a harness self-test rather than an episode — never a result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

HARNESS = Path(__file__).resolve().parent
BENCHMARK = HARNESS.parent
REPO = BENCHMARK.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(BENCHMARK / "stubs"))

import detect  # noqa: E402
import install_stubs  # noqa: E402
import runners as runner_module  # noqa: E402

VISIBLE = ("job.sh", "prompt.md")
WITHHELD = ("case.yaml", "reference.sh", "rubric.md")
GENERATED = BENCHMARK / "generated"


@dataclass(frozen=True)
class Condition:
    doc: bool
    skills: str  # "none" or a skill-bundle name

    @property
    def label(self) -> str:
        return f"doc-{'present' if self.doc else 'absent'}_skills-{self.skills}"

    @staticmethod
    def matrix(skill_tiers: tuple[str, ...] = ("none", "good")) -> list[Condition]:
        return [Condition(doc, tier) for doc in (False, True) for tier in skill_tiers]


# ------------------------------------------------------------------------------------------
# Materialization
# ------------------------------------------------------------------------------------------


def materialize(
    case_dir: Path, sandbox: Path, condition: Condition, skills_path: Path | None = None
) -> dict[str, str]:
    """Build the sandbox for one condition. Returns the environment to run under."""
    environment = install_stubs.install(sandbox, BENCHMARK / "center.yaml")
    work = sandbox / "work"

    for name in VISIBLE:
        shutil.copy2(case_dir / name, work / name)
    if (case_dir / "assets").is_dir():
        for asset in sorted((case_dir / "assets").iterdir()):
            # Flattened alongside job.sh, not into an assets/ subdirectory — the scripts refer to
            # their inputs by bare name.
            shutil.copy2(asset, work / asset.name)

    if condition.doc:
        shutil.copy2(GENERATED / "INSTRUCTIONS.md", work / "INSTRUCTIONS.md")

    if condition.skills != "none":
        if skills_path is None or not skills_path.is_dir():
            raise SystemExit(
                f"condition asks for skills tier {condition.skills!r} but --skills is "
                f"{skills_path} — the skills under test are data, not part of this repo. "
                f"Point --skills at a checkout of the bundle."
            )
        destination = work / ".claude" / "skills"
        destination.parent.mkdir(exist_ok=True)
        shutil.copytree(skills_path, destination, dirs_exist_ok=True)

    assert_nothing_withheld_leaked(work)
    return environment


def assert_nothing_withheld_leaked(work: Path) -> None:
    """The one invariant that cannot be checked after the fact.

    A leaked `rubric.md` does not announce itself in the results — the episode just scores
    suspiciously well. So it is checked here, by content rather than by filename, because a
    rubric copied in under another name leaks exactly as much.
    """
    fingerprints = {
        path.name: {
            line.strip() for line in (path).read_text().splitlines()
            if len(line.strip()) > 40
        }
        for case in (BENCHMARK / "cases").iterdir() if case.is_dir()
        for path in (case / name for name in WITHHELD) if path.exists()
    }
    leaked_lines: set[str] = set()
    for lines in fingerprints.values():
        leaked_lines |= lines

    for path in work.rglob("*"):
        if not path.is_file() or path.name in VISIBLE:
            continue
        if path.name in WITHHELD:
            raise AssertionError(f"withheld file leaked into the sandbox: {path}")
        try:
            content = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        overlap = {line.strip() for line in content.splitlines()} & leaked_lines
        if overlap:
            raise AssertionError(
                f"{path} contains withheld text: {sorted(overlap)[0][:70]!r}"
            )


# ------------------------------------------------------------------------------------------
# Evidence
# ------------------------------------------------------------------------------------------


def submitted_scripts(records: list[dict]) -> list[str]:
    """Script names from accepted submissions, in order, deduplicated."""
    names: list[str] = []
    for record in records:
        if record.get("command") != "sbatch" or record.get("outcome") != "accepted":
            continue
        for argument in record.get("argv", [])[1:]:
            if argument.startswith("-"):
                continue
            if argument.endswith(".sh") or "/" in argument:
                if argument not in names:
                    names.append(argument)
                break
    return names


EXECUTION = re.compile(r"(?:^|[|&;]\s*)(?:bash|sh|zsh|source|\.)\s+(\S+\.sh)|(?:^|\s)\./(\S+\.sh)")


def executed_scripts(records: list[dict]) -> list[str]:
    """Scripts the agent ran itself, from transcript records."""
    names: list[str] = []
    for record in records:
        if record.get("source") != "transcript":
            continue
        for match in EXECUTION.finditer(record.get("command", "")):
            name = match.group(1) or match.group(2)
            if name and name not in names:
                names.append(name)
    return names


def scoring_targets(work: Path, records: list[dict]) -> list[Path]:
    """Score what ran or was submitted — not whatever happens to be named `job.sh`.

    The first version of this read submitted scripts only, and it scored A2 and A3 as clean while
    their drivers still busy-waited and still fired twenty submissions. Those cases hand the agent
    a *driver*: what gets submitted is a batch script that was never the problem, and the defect
    stays in the file the agent executed.

    Reading `job.sh` unconditionally is wrong in the other direction: an agent that leaves the
    broken file in place and submits a corrected copy really did do the right thing, and failing
    it for the untouched original would punish a valid fix.

    So the rule is uniform and needs no case-type distinction — score every script the agent
    executed and every script it submitted, and fall back to `job.sh` only when it did neither.
    """
    targets: list[Path] = []
    for name in executed_scripts(records) + submitted_scripts(records):
        candidate = work / Path(name).name
        if candidate.is_file() and candidate not in targets:
            targets.append(candidate)
    if not targets:
        primary = work / "job.sh"
        if primary.is_file():
            targets.append(primary)
    return targets


def read_call_log(runtime: Path) -> list[dict]:
    path = runtime / "calls.jsonl"
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"source": "stub", "command": "?", "ts": 0.0, "malformed": line[:120]})
    return records


def append_transcript_records(runtime: Path, result: runner_module.RunResult) -> None:
    """Fold the agent's own commands into the same log, tagged `transcript`."""
    expanded = runner_module.expand_shell_commands(result.commands)
    with (runtime / "calls.jsonl").open("a") as handle:
        for record in runner_module.RunResult(commands=expanded).as_call_log_records():
            handle.write(json.dumps(record, sort_keys=True) + "\n")


# ------------------------------------------------------------------------------------------
# One episode
# ------------------------------------------------------------------------------------------


def run_episode(
    case_id: str,
    condition: Condition,
    runner: runner_module.Runner,
    seed: int = 0,
    sandbox_root: Path | None = None,
    timeout_s: int = 300,
    skills_path: Path | None = None,
    keep: bool = False,
) -> dict:
    case_dir = BENCHMARK / "cases" / case_id
    if not case_dir.is_dir():
        raise SystemExit(f"no such case: {case_id}")
    case = yaml.safe_load((case_dir / "case.yaml").read_text())
    limits = detect.load_detector_limits(GENERATED / "detectors.json")

    root = sandbox_root or Path(
        f"/tmp/hpcbench-{case_id}-{condition.label}-s{seed}-{int(time.time())}"
    )
    sandbox = root / "sandbox"
    environment = materialize(case_dir, sandbox, condition, skills_path)
    environment["HPCBENCH_EPISODE"] = f"{case_id}/{condition.label}/seed{seed}"
    work, runtime = sandbox / "work", sandbox / "runtime"

    prompt = (case_dir / "prompt.md").read_text().strip()
    started = time.time()
    result = runner.run(work, prompt, environment, timeout_s)
    append_transcript_records(runtime, result)
    records = read_call_log(runtime)

    targets = scoring_targets(work, records)
    static_findings = [
        finding
        for target in targets
        for finding in detect.run_static(case, target.read_text(), limits)
    ]
    scripts = {
        path.name: path.read_text()
        for path in sorted(work.glob("*.sh")) if path.is_file()
    }
    call_log_findings = detect.run_call_log(case, records, limits, scripts)

    original = work / "job.sh"
    episode = {
        "schema_version": 1,
        "case": case_id,
        "family": case.get("family"),
        "condition": {"doc": condition.doc, "skills": condition.skills,
                      "label": condition.label},
        "seed": seed,
        "runner": runner.name,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started)),
        "duration_s": result.duration_s,
        "timed_out": result.timed_out,
        "agent_exit_code": result.exit_code,
        "agent_error": result.error,
        "detector_limits_schema_version": limits.get("schema_version"),
        "evidence": {
            "scored_scripts": [str(path.relative_to(work)) for path in targets],
            "submitted_scripts": submitted_scripts(records),
            "final_job_sh_sha256": (
                hashlib.sha256(original.read_bytes()).hexdigest() if original.exists() else None
            ),
            "job_sh_modified": (
                original.exists()
                and original.read_bytes() != (case_dir / "job.sh").read_bytes()
            ),
            "stub_calls": sum(1 for item in records if item.get("source") == "stub"),
            "agent_commands": sum(1 for item in records if item.get("source") == "transcript"),
            "transcript_events": len(result.transcript),
        },
        "l1": {
            "static": {
                "verdict": detect.verdict(static_findings),
                "findings": [finding.as_dict() for finding in static_findings],
            },
            "call_log": {
                "verdict": detect.verdict(call_log_findings),
                "findings": [finding.as_dict() for finding in call_log_findings],
            },
        },
    }
    episode["l1"]["prevented"] = (
        episode["l1"]["static"]["verdict"] == "pass"
        and episode["l1"]["call_log"]["verdict"] in ("pass", "not_applicable")
    )

    if keep:
        episode["sandbox"] = str(sandbox)
        (root / "episode.json").write_text(json.dumps(episode, indent=2) + "\n")
        (root / "transcript.json").write_text(json.dumps(result.transcript, indent=2) + "\n")
    else:
        shutil.rmtree(root, ignore_errors=True)
    return episode


# ------------------------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------------------------


def reference_runner(case_id: str) -> runner_module.ScriptedRunner:
    """The ceiling: apply the case's own reference remedy, then run it.

    A harness self-test, not an episode. It reads `reference.sh`, which is withheld from agents, so
    it can never appear in a result — its only job is to show the detectors accept a correct answer.
    Without it, a detector that failed everything would look perfect against the floor.

    How the remedy is exercised depends on what the case hands over: a batch script gets submitted,
    a driver gets executed. `#SBATCH` presence is the honest discriminator.
    """
    case_dir = BENCHMARK / "cases" / case_id
    reference = (case_dir / "reference.sh").read_text()
    is_batch = "#SBATCH" in reference
    return runner_module.ScriptedRunner(
        commands=["sbatch job.sh" if is_batch else "bash job.sh"],
        writes={"job.sh": reference},
    )


def build_runner(name: str, model: str, case_id: str = "") -> runner_module.Runner:
    if name == "noop":
        return runner_module.NoopRunner()
    if name == "claude-code":
        return runner_module.ClaudeCodeRunner(model=model)
    if name == "scripted-asis":
        # The floor: run the script exactly as handed over, changing nothing. Every case should
        # fail, and a case that passes here is not a case.
        return runner_module.ScriptedRunner(["bash job.sh || sbatch job.sh"])
    if name == "scripted-reference":
        return reference_runner(case_id)
    raise SystemExit(f"unknown runner: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("case", help="case id, or 'all'")
    parser.add_argument("--runner", default="noop",
                        choices=("noop", "scripted-asis", "scripted-reference", "claude-code"))
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--matrix", action="store_true", help="run all four conditions")
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--skills", type=Path, default=None,
                        help="path to the skill bundle under test")
    parser.add_argument("--results", type=Path, default=REPO / "results",
                        help="where episode records are appended")
    parser.add_argument("--keep", action="store_true", help="keep sandboxes for inspection")
    arguments = parser.parse_args()

    cases = (
        sorted(path.name for path in (BENCHMARK / "cases").iterdir() if path.is_dir())
        if arguments.case == "all" else [arguments.case]
    )
    tiers = ("none", "good") if arguments.skills else ("none",)
    conditions = Condition.matrix(tiers) if arguments.matrix else [Condition(False, "none")]
    if arguments.matrix and not arguments.skills:
        print("note: --skills not given, so only the skills-none arm runs\n", file=sys.stderr)

    episodes = []
    for case_id in cases:
        runner = build_runner(arguments.runner, arguments.model, case_id)
        for condition in conditions:
            for seed in range(arguments.seeds):
                episode = run_episode(
                    case_id, condition, runner, seed=seed, timeout_s=arguments.timeout,
                    skills_path=arguments.skills, keep=arguments.keep,
                )
                episodes.append(episode)
                print(
                    f"  {case_id:24s} {condition.label:34s} seed{seed}  "
                    f"static={episode['l1']['static']['verdict']:12s} "
                    f"call_log={episode['l1']['call_log']['verdict']:14s} "
                    f"prevented={episode['l1']['prevented']}"
                )

    arguments.results.mkdir(parents=True, exist_ok=True)
    destination = arguments.results / f"episodes-{time.strftime('%Y%m%dT%H%M%S')}.jsonl"
    with destination.open("w") as handle:
        for episode in episodes:
            handle.write(json.dumps(episode, sort_keys=True) + "\n")

    prevented = sum(1 for episode in episodes if episode["l1"]["prevented"])
    print(f"\n{prevented}/{len(episodes)} episodes prevented (L1 only — L2 and L3 are not "
          f"implemented yet, so this is not the headline)")
    print(f"written to {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
