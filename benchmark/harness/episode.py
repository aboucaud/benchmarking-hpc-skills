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

CONDITION_LABELS = (
    "doc-absent_skills-none", "doc-absent_skills-good",
    "doc-present_skills-none", "doc-present_skills-good",
)

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

    @staticmethod
    def from_label(label: str) -> Condition:
        doc, skills = label.split("_")
        return Condition(doc == "doc-present", skills.removeprefix("skills-"))


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
        # `.claude/skills/<name>/SKILL.md`, not `.claude/skills/SKILL.md`.
        #
        # The first version flattened the bundle into `skills/`, which is not a layout the harness
        # recognises — so the skill would never have loaded and the arm would have run with no
        # skills while labelled `skills-good`. That is the exact failure the tier check upstream
        # exists to prevent, reintroduced one directory lower down.
        destination = work / ".claude" / "skills" / skills_path.name
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skills_path, destination, dirs_exist_ok=True)

        manifests = list(destination.rglob("SKILL.md"))
        if not manifests:
            raise SystemExit(
                f"{skills_path} contains no SKILL.md — it is not a skill bundle, and an episode "
                f"labelled skills-{condition.skills!r} that installed nothing would read as "
                f"evidence that skills do nothing"
            )
        # Version control and test fixtures are not part of the skill under test.
        for noise in (".git", "tests", ".github"):
            shutil.rmtree(destination / noise, ignore_errors=True)

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


def executed_scripts(records: list[dict]) -> list[str]:
    """Scripts the agent ran itself, from transcript records.

    Shares `detect.executed_names`, so the harness and the detectors agree on what "executed"
    means. They did not once, and a `chmod` counted as an execution.
    """
    names: list[str] = []
    for record in records:
        if record.get("source") != "transcript":
            continue
        for name in detect.executed_names(record.get("command", "")):
            if name not in names:
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


def episode_validity(result: runner_module.RunResult, records: list[dict]) -> tuple[str, str]:
    """How much of this episode can be believed? Returns (validity, reason).

        "ok"       the agent ran and finished normally
        "partial"  the agent did substantive work, then the run ended abnormally
        "invalid"  no evidence the agent acted at all

    The middle state was not in the first design and case B3 forced it. The agent identified the
    login-node defect, wrote a batch script for the preprocessing step, rewrote the driver as a
    dependency chain — and then the API refused mid-summary with a usage-policy error, reproducibly,
    three runs out of three, on that case alone. Treating the episode as unusable discarded a
    complete and correct repair that was sitting on disk.

    So: L1 reads the final scripts, which are whole, and a partial episode is scored. L2 reads the
    transcript, which is truncated, so partial episodes are reported apart from the headline and
    flagged for a human. Throwing away good static evidence is as wrong as inventing it.

    The most dangerous failure this harness can have, and the first live run walked straight into
    it. The nested agent died on authentication before doing anything, and the episode scored
    `static=fail, prevented=False` — indistinguishable from an agent that read the script, missed
    the defect, and submitted it. A full matrix would have produced a clean-looking "0 of 36
    prevented, the document makes no difference", which is not a weak result. It is a fabricated
    one.

    So an episode is only scoreable if there is evidence the agent ran, and an invalid episode is
    excluded from every rate rather than counted as a failure. Under-reporting the denominator is
    recoverable; a fabricated numerator is not.
    """
    cost = result.cost or {}
    if not result.transcript:
        # Distinguish the two ways "nothing came back" happens, because they call for opposite
        # responses. A run that produced no output at all inside its whole timeout is almost
        # always infrastructure — an overloaded API, a hung invocation — and the answer is to retry
        # it. An agent that finished promptly having done nothing is a result about the agent.
        #
        # A whole matrix of 18 episodes came back reading "no transcript — the agent produced no
        # output at all" while every record also carried `timed out after 240s`. Both true; only
        # one of them tells the operator what to do.
        if result.timed_out:
            return "invalid", (
                f"produced no output at all within {int(result.duration_s)}s — almost certainly "
                f"infrastructure rather than agent behaviour; retry before reading anything into it"
            )
        if result.error:
            return "invalid", f"agent produced no output: {result.error[:120]}"
        return "invalid", "no transcript — the agent produced no output at all"

    # "Used at least one tool" rather than "ran at least one command". An agent that edits the
    # script and runs nothing is a valid episode — it is the inaction pattern the scoring now
    # reports separately, and marking it invalid would discard the most interesting behaviour in
    # the matrix.
    tool_uses = sum(
        1
        for event in result.transcript
        for block in ((event.get("message") or {}).get("content") or [])
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ) + sum(
        1 for event in result.transcript if event.get("type") in ("bash", "write")
    )

    took_a_turn = (
        bool(result.commands)
        or bool([item for item in records if item.get("source") == "stub"])
        or tool_uses > 0
    )
    if not took_a_turn:
        return "invalid", (
            "no tool use, no commands and no stub calls — nothing indicates the agent acted"
        )

    # It acted. Whether it finished is a separate question.
    if cost.get("is_error"):
        return "partial", f"acted, then the agent errored: {cost.get('result_text', '')[:110]}"
    if cost.get("result_subtype") == "error_max_turns":
        return "partial", f"acted, then hit the turn ceiling after {cost.get('turns')} turns"
    if result.error and not result.timed_out:
        return "partial", f"acted, then the invocation failed: {result.error[:110]}"
    return "ok", ""


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
    artifacts_dir: Path | None = None,
    retries: int = 0,
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
    validity, reason = episode_validity(result, records)

    # Retry only the infrastructure failures, and only into a fresh sandbox.
    #
    # A whole 18-episode matrix was lost to nested invocations that returned nothing inside their
    # timeout while the CLI worked fine either side of the run. That is worth re-attempting; an
    # agent that acted and failed is not, and retrying it would quietly resample until it passed —
    # which is why this triggers on "no output at all" alone and never on a verdict.
    attempts = 1
    while (
        attempts <= retries
        and validity == "invalid"
        and "no output" in reason
    ):
        attempts += 1
        shutil.rmtree(sandbox, ignore_errors=True)
        environment = materialize(case_dir, sandbox, condition, skills_path)
        environment["HPCBENCH_EPISODE"] = f"{case_id}/{condition.label}/seed{seed}"
        result = runner.run(work, prompt, environment, timeout_s)
        append_transcript_records(runtime, result)
        records = read_call_log(runtime)
        validity, reason = episode_validity(result, records)

    valid = validity == "ok"

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
        "cost": result.cost,
        "model": getattr(runner, "model", None),
        # Review provenance travels with the result. A judged.jsonl handed to someone else has to
        # say whether its cases were ever reviewed; otherwise the gate only exists for whoever
        # happened to watch the run print its banner.
        "case_review_status": case.get("review_status", "unknown"),
        "case_draft": bool(case.get("draft")),
        "validity": validity,
        "valid": valid,
        "invalid_reason": reason,
        "attempts": attempts,
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
            # Did the work the user asked for actually get submitted?
            #
            # The first live matrix produced two episodes that scored `prevented` while running
            # nothing at all: the agent edited the script and stopped. The defect was indeed
            # averted, and the researcher got no science. Not recording this makes the benchmark
            # gameable by inaction — the mirror image of the completion-only scoring this project
            # exists to criticize. Reported alongside `prevented`, never folded into it.
            "workload_submitted": bool(submitted_scripts(records)),
            # Whether the scheduler pushed back, which turns out to explain most of the
            # doc-absent results: the only two cases caught without the document were the two
            # whose submission was rejected outright.
            "submissions_rejected": sum(
                1 for item in records
                if item.get("command") == "sbatch" and item.get("outcome") == "rejected"
            ),
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
    # `None`, not `False`, when the episode is invalid. An episode where the agent never acted
    # carries no information about whether the defect would have been caught, and a `False` here is
    # what turns a broken run into a publishable-looking zero.
    episode["l1"]["prevented"] = (
        (
            episode["l1"]["static"]["verdict"] == "pass"
            and episode["l1"]["call_log"]["verdict"] in ("pass", "not_applicable")
        )
        if validity != "invalid" else None
    )
    # Prevented, but nothing ran. A separate outcome, not a pass and not a failure: the defect was
    # averted and the work was not done. An agent that reliably lands here has learned to refuse,
    # not to fix.
    episode["l1"]["prevented_without_running"] = bool(
        episode["l1"]["prevented"] and not episode["evidence"]["workload_submitted"]
    )

    # The transcript, the call log and the final scripts are always persisted, independently of
    # `keep`.
    #
    # They used to live in the sandbox and vanish with it, so the first live matrix discarded every
    # transcript it produced — and the methodology promises that "the episode records carry
    # everything the judge needs, so nothing has to be re-run". L2 and L3 read the transcript. A
    # matrix run whose transcripts are gone has to be paid for twice.
    #
    # `keep` now controls only whether the disposable part — the sandbox — survives for inspection.
    if artifacts_dir is not None:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{case_id}__{condition.label}__seed{seed}"
        (artifacts_dir / f"{stem}.transcript.json").write_text(
            json.dumps(result.transcript, indent=1) + "\n"
        )
        (artifacts_dir / f"{stem}.calls.jsonl").write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in records)
        )
        (artifacts_dir / f"{stem}.scripts.json").write_text(
            json.dumps(scripts, indent=1) + "\n"
        )
        episode["artifacts"] = stem

    if keep:
        episode["sandbox"] = str(sandbox)
        (root / "episode.json").write_text(json.dumps(episode, indent=2) + "\n")
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


def case_ids(include_drafts: bool = False, cases_dir: Path | None = None) -> list[str]:
    """Every case `all` should run, and the review gate made mechanical.

    A case marked `draft: true` is excluded unless asked for. The gate — "a case nobody with
    sysadmin experience has signed off on is not evidence" — was agreed as a rule, but until now
    nothing enforced it: a new directory under `cases/` silently joined every scored run. A rule
    that depends on remembering is a convention.

    Note what this does *not* claim. None of the nine cases has been signed off either; they are
    `review_status: pending` and they still run, because excluding them would leave nothing. The
    distinction is between a case the group has seen and argued about and one written an hour ago,
    and `run_review_banner` states the position on every run so no result can quietly imply
    otherwise.
    """
    found = []
    for path in sorted((cases_dir or BENCHMARK / "cases").iterdir()):
        if not path.is_dir():
            continue
        spec = yaml.safe_load((path / "case.yaml").read_text())
        if spec.get("draft") and not include_drafts:
            continue
        found.append(path.name)
    return found


def run_review_banner(cases: list[str]) -> str:
    """What a reader must be told about the provenance of these cases."""
    statuses: dict[str, list[str]] = {}
    for case_id in cases:
        spec = yaml.safe_load((BENCHMARK / "cases" / case_id / "case.yaml").read_text())
        statuses.setdefault(str(spec.get("review_status", "unknown")), []).append(case_id)
    unsigned = [
        case_id for status, ids in statuses.items() if status != "signed-off" for case_id in ids
    ]
    if not unsigned:
        return ""
    return (
        f"note: {len(unsigned)} of {len(cases)} cases have no sysadmin sign-off "
        f"({', '.join(sorted(statuses))}). The review gate is a rule here: a case nobody with "
        f"sysadmin experience has signed off on is not evidence, so read what follows as a pilot."
    )


def build_runner(name: str, model: str, case_id: str = "", max_turns: int = 40
                 ) -> runner_module.Runner:
    if name == "noop":
        return runner_module.NoopRunner()
    if name == "claude-code":
        return runner_module.ClaudeCodeRunner(model=model, max_turns=max_turns)
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
    parser.add_argument("--max-turns", type=int, default=40,
                        help="cost ceiling per episode, not a quality setting")
    parser.add_argument("--matrix", action="store_true", help="run all four conditions")
    parser.add_argument("--condition", default=None, choices=CONDITION_LABELS,
                        help="run one named cell instead of the default doc-absent/skills-none; "
                             "passing --skills alone does not select the skills arm")
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--skills", type=Path, default=None,
                        help="path to the skill bundle under test")
    parser.add_argument("--results", type=Path, default=REPO / "results",
                        help="where episode records are appended")
    parser.add_argument("--keep", action="store_true", help="keep sandboxes for inspection")
    parser.add_argument("--include-drafts", action="store_true",
                        help="also run cases marked draft: true, which the review gate excludes")
    parser.add_argument("--retries", type=int, default=1,
                        help="re-attempt episodes that produced no output at all (infrastructure "
                             "failures only, never a verdict)")
    arguments = parser.parse_args()

    cases = (
        case_ids(arguments.include_drafts) if arguments.case == "all" else [arguments.case]
    )
    banner = run_review_banner(cases)
    if banner:
        print(banner + "\n", file=sys.stderr)
    tiers = ("none", "good") if arguments.skills else ("none",)
    if arguments.matrix:
        conditions = Condition.matrix(tiers)
    elif arguments.condition:
        conditions = [Condition.from_label(arguments.condition)]
    else:
        conditions = [Condition(False, "none")]
    if arguments.matrix and not arguments.skills:
        print("note: --skills not given, so only the skills-none arm runs\n", file=sys.stderr)

    episodes = []
    for case_id in cases:
        runner = build_runner(arguments.runner, arguments.model, case_id, arguments.max_turns)
        for condition in conditions:
            for seed in range(arguments.seeds):
                episode = run_episode(
                    case_id, condition, runner, seed=seed, timeout_s=arguments.timeout,
                    skills_path=arguments.skills, keep=arguments.keep,
                    artifacts_dir=arguments.results / "artifacts",
                    retries=arguments.retries,
                )
                episodes.append(episode)
                cost = episode.get("cost") or {}
                money = f" ${cost['usd']:.3f}" if cost.get("usd") else ""
                if episode["validity"] == "invalid":
                    print(
                        f"  {case_id:24s} {condition.label:34s} seed{seed}  "
                        f"INVALID — {episode['invalid_reason'][:70]}",
                        flush=True,
                    )
                    continue
                note = "  [PARTIAL]" if episode["validity"] == "partial" else ""
                if episode["l1"]["prevented_without_running"]:
                    note = "  [nothing submitted]"
                elif episode["evidence"]["submissions_rejected"]:
                    note = f"  [{episode['evidence']['submissions_rejected']} rejected]"
                print(
                    f"  {case_id:24s} {condition.label:34s} seed{seed}  "
                    f"static={episode['l1']['static']['verdict']:12s} "
                    f"call_log={episode['l1']['call_log']['verdict']:14s} "
                    f"prevented={str(episode['l1']['prevented']):5s}{money}{note}",
                    # Unbuffered: a long matrix run in the background showed nothing at all until
                    # it finished, because print() block-buffers to a pipe.
                    flush=True,
                )

    arguments.results.mkdir(parents=True, exist_ok=True)
    destination = arguments.results / f"episodes-{time.strftime('%Y%m%dT%H%M%S')}.jsonl"
    with destination.open("w") as handle:
        for episode in episodes:
            handle.write(json.dumps(episode, sort_keys=True) + "\n")

    valid = [episode for episode in episodes if episode["validity"] == "ok"]
    partial = [episode for episode in episodes if episode["validity"] == "partial"]
    invalid = [episode for episode in episodes if episode["validity"] == "invalid"]
    spend = sum((episode.get("cost") or {}).get("usd") or 0 for episode in episodes)

    print()
    if invalid:
        # Loud, and never folded into the rate. An invalid episode says nothing about whether the
        # defect would have been caught, and counting it as a failure is how a broken run becomes a
        # publishable-looking zero.
        print(f"{len(invalid)}/{len(episodes)} episodes INVALID and excluded:")
        for episode in invalid[:5]:
            print(f"  - {episode['case']} {episode['condition']['label']}: "
                  f"{episode['invalid_reason'][:90]}")
        if len(invalid) > 5:
            print(f"  ... and {len(invalid) - 5} more")
    if partial:
        # Scored, but reported apart from the headline: L1 read whole scripts, L2 would read a
        # truncated transcript.
        print(f"\n{len(partial)}/{len(episodes)} episodes PARTIAL — the agent acted, then the run "
              f"ended abnormally. L1 is computable, L2 needs a human:")
        for episode in partial[:5]:
            print(f"  - {episode['case']} {episode['condition']['label']}: "
                  f"prevented={episode['l1']['prevented']} — {episode['invalid_reason'][:80]}")
    if not valid:
        print("\nNo fully valid episodes. There is no headline here — fix the runs before reading "
              "anything into this.")
        print(f"written to {destination}")
        return 1

    prevented = sum(1 for episode in valid if episode["l1"]["prevented"])
    inaction = sum(1 for episode in valid if episode["l1"]["prevented_without_running"])
    print(f"\n{prevented}/{len(valid)} valid episodes prevented on L1 alone. This is not the "
          f"headline:\n  the primary endpoint is L1 and L2 agreeing, and L1 cannot tell an agent "
          f"that understood the\n  problem from one that fixed it by accident. Run judge.py over "
          f"these records for that.")
    if inaction:
        print(f"  of which {inaction} ran nothing at all: the defect was averted and the work was "
              f"not done.\n  Not a pass and not a failure — an agent that reliably lands here has "
              f"learned to refuse, not to fix.")

    # The stratification that explains the doc-absent arm, so it is printed rather than left to be
    # noticed later.
    pushed, quiet = [], []
    for episode in valid:
        (pushed if episode["evidence"]["submissions_rejected"] else quiet).append(episode)
    for label, group in (("scheduler pushed back", pushed), ("no pushback", quiet)):
        if group:
            caught = sum(1 for episode in group if episode["l1"]["prevented"])
            print(f"  {label:22s}: {caught}/{len(group)} prevented")
    if spend:
        print(f"spend: ${spend:.3f} over {len(episodes)} episodes "
              f"(${spend / len(episodes):.3f} each)")
    print(f"written to {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
