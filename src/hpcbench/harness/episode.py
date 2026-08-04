#!/usr/bin/env python3
"""Run one episode: materialize a condition, let an agent act, collect the evidence, score L1.

    # inspect a condition without running an agent
    uv run --with pyyaml src/hpcbench/harness/episode.py C3-wrong-partition --runner noop --keep

    # the full 2x2 for one case, with scripted conduct
    uv run --with pyyaml src/hpcbench/harness/episode.py C3-wrong-partition --matrix --seeds 3

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
import secrets
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

if __package__ in (None, ""):  # invoked as a script rather than imported
    # ...and the target is `src/`, not the repo root. The repo root holds no `hpcbench`,
    # so getting this index wrong makes the next line raise — invisibly, because `uv run`
    # leaves an editable install whose .pth already puts `src` on the path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hpcbench.harness import (
    detect,  # noqa: E402
    report,  # noqa: E402
)
from hpcbench.harness import runners as runner_module  # noqa: E402
from hpcbench.paths import BENCHMARK, GENERATED, REPO  # noqa: E402
from hpcbench.stubs import install_stubs  # noqa: E402

HARNESS = Path(__file__).resolve().parent

CONDITION_LABELS = (
    "doc-absent_skills-none", "doc-absent_skills-good",
    "doc-present_skills-none", "doc-present_skills-good",
)

VISIBLE = ("job.sh", "prompt.md")
WITHHELD = ("case.yaml", "reference.sh", "rubric.md")

# Every copy of the intervention that exists anywhere on this machine, not just the one this
# arm would have installed.
#
# A doc-absent episode that widened its search to the host found three: two concurrent sandboxes
# and the repo's own hand-maintained copy. Fingerprinting only `generated/INSTRUCTIONS.md` would
# miss an agent that read `agents/INSTRUCTIONS.md` instead — which is the copy the Docker
# substrate serves, so it is a real document and not a stray file. See #29 for why there are two.
DOCUMENTS = (GENERATED / "INSTRUCTIONS.md", REPO / "agents" / "INSTRUCTIONS.md")

# Long enough that no agent writes one by coincidence.
#
# The withheld-content check uses 40, which is right for it: a leaked rubric line is being copied
# verbatim into a file. This check reads a *transcript*, where the agent's own prose is in scope
# and a 40-character sentence about walltime limits is something a competent agent might simply
# say. At 60 there is no overlap between the two documents, the skill bundle, and every case's
# visible files — measured, not assumed, and asserted in tests/test_containment.py so it stays
# true as those files change.
CONTAMINATION_MIN_LINE = 60

# Skills are delivered as plain markdown in the working directory, not installed into any
# agent's own skill mechanism.
#
# They used to go to `.claude/skills/<name>/SKILL.md`, which is a Claude Code autoload
# convention. Three things are wrong with that. It measures one harness: Codex — which the
# Docker/Slurm substrate uses — never reads that path, so the skills arm would silently be
# skills-none there while still being labelled skills-good. It is not deployable: a centre can
# publish files, it cannot install into every user's agent configuration. And it makes the two
# interventions structurally different, when the thing under test is their *content* — the
# document describes the cluster, the skill describes procedure, and both are markdown a centre
# hosts.
SKILLS_DIR = "skills"

# Appended verbatim to every episode's prompt, in all four cells. See materialize().
SITE_GUIDANCE_POINTER = (
    "\n\nBefore you start: this site may publish guidance for the cluster you are on — "
    "conventions, limits, and how it expects jobs to be run. If it does, it is in this "
    "directory (`INSTRUCTIONS.md`) or under `skills/`. Check, and use whatever you find. "
    "There may be nothing there.\n"
)


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
        destination = work / SKILLS_DIR / skills_path.name
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

    # The pointer goes in EVERY arm, including the ones with nothing to find.
    #
    # Delivering the skill as a file rather than as an autoloaded skill changes what the
    # condition means: an autoloaded skill is always in context, a file is read only if the agent
    # looks. Without a constant pointer the skills-good arm would be measuring "did it think to
    # look in this directory", which varies by model and by run, rather than "did the skill's
    # content help" — and the skills-none arm would not even face the question.
    #
    # So availability is held constant and only content varies. In three of the four cells the
    # agent looks and finds nothing, which is exactly what an agent on a centre that publishes
    # nothing would find.
    prompt_path = work / "prompt.md"
    prompt_path.write_text(prompt_path.read_text().rstrip() + SITE_GUIDANCE_POINTER)

    assert_nothing_withheld_leaked(work)
    assert_arm_was_built(work, condition)
    return environment


def assert_arm_was_built(work: Path, condition: Condition) -> None:
    """The sandbox matches the label on it. Checked here because it is exactly checkable here.

    The post-hoc `arm_contamination` check catches an episode that reached the *other* arm's
    content. This catches the opposite and much quieter failure: an arm that was never built.
    A `doc-present` episode whose document silently failed to copy runs as a control while being
    counted as an intervention, which does not weaken the result — it moves episodes across the
    comparison, and the direction it moves them is toward "the document does nothing".

    Nothing downstream can recover this. Once the run is over, a doc-present episode with no
    document and a doc-present episode whose agent never opened the document produce the same
    transcript.
    """
    document = work / "INSTRUCTIONS.md"
    if condition.doc and not document.exists():
        raise AssertionError(
            f"condition is doc-present but no INSTRUCTIONS.md reached {work} — this episode "
            f"would run as a control and be counted as an intervention"
        )
    if not condition.doc and document.exists():
        raise AssertionError(
            f"condition is doc-absent but {document} exists — the control arm carries the "
            f"intervention"
        )

    manifests = list((work / SKILLS_DIR).rglob("SKILL.md")) if (work / SKILLS_DIR).is_dir() else []
    if condition.skills != "none" and not manifests:
        raise AssertionError(
            f"condition is skills-{condition.skills} but no SKILL.md is under {work / SKILLS_DIR}"
        )
    if condition.skills == "none" and manifests:
        raise AssertionError(
            f"condition is skills-none but {manifests[0]} exists — the control arm carries the "
            f"intervention"
        )


def _digest(paths: list[Path], root: Path) -> str | None:
    """One hash over a set of files, keyed by path relative to `root`. `None` if there are none.

    Path-keyed rather than content-only, so moving a file changes the digest: where a skill puts
    its content is part of what an agent was given.
    """
    if not paths:
        return None
    accumulator = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item.relative_to(root))):
        accumulator.update(str(path.relative_to(root)).encode())
        accumulator.update(b"\0")
        accumulator.update(hashlib.sha256(path.read_bytes()).hexdigest().encode())
        accumulator.update(b"\n")
    return accumulator.hexdigest()


def intervention_digest(work: Path, condition: Condition) -> dict:
    """What the agent was actually given, hashed before the agent can change any of it.

    `assert_arm_was_built` answers "did the intervention arrive" as a boolean. This answers
    "which intervention", which is the question a results file could not answer at all: records
    stamp `schema_version` and the code revision, and nothing about the experimental material.
    That is how the matrix came to be run against a 200-line skill while `main` carried the
    191-line version (#34) with every record looking identical, and how two substrates ran two
    different `INSTRUCTIONS.md` for the whole pilot (#29).

    Called after `materialize` and before the runner, deliberately. Hashing afterwards would
    record whatever the agent edited, and an agent that rewrites `INSTRUCTIONS.md` is exactly the
    episode where knowing what it started from matters.

    `case_files` covers `job.sh`, `prompt.md` and the assets as materialized — including the
    appended site-guidance pointer. It is here because the fixtures are experimental material
    too: the commit that removed "the defect is the partition, not the request" from a file the
    agent reads changed what C3 measures, and without this stamp no record would say which side
    of that change it is on.
    """
    def under(directory: Path) -> list[Path]:
        if not directory.is_dir():
            return []
        return [path for path in directory.rglob("*") if path.is_file()]

    document = work / "INSTRUCTIONS.md"
    skills_root = work / SKILLS_DIR
    case_files = [
        path for path in work.iterdir()
        if path.is_file() and path.name != "INSTRUCTIONS.md"
    ]
    return {
        "document_sha256": (
            hashlib.sha256(document.read_bytes()).hexdigest() if document.exists() else None
        ),
        "skills_sha256": _digest(under(skills_root), skills_root),
        # Readable beside the hash on purpose: a digest tells you two runs differed, not how.
        "skills_manifests": sorted(
            str(path.relative_to(skills_root))
            for path in skills_root.rglob("SKILL.md")
        ) if skills_root.is_dir() else [],
        "case_files_sha256": _digest(case_files, work),
    }


def distinctive_lines(paths, minimum: int = CONTAMINATION_MIN_LINE) -> set[str]:
    """Long stripped lines from `paths`, as a set. Missing and unreadable files contribute none."""
    found: set[str] = set()
    for path in paths:
        try:
            text = Path(path).read_text()
        except (UnicodeDecodeError, OSError):
            continue
        found |= {line.strip() for line in text.splitlines() if len(line.strip()) >= minimum}
    return found


def transcript_text(result: runner_module.RunResult) -> str:
    """Every string anywhere in the transcript, including tool results.

    Deliberately not `environment_failure`'s blob, which collects assistant `text` blocks only.
    That is right for reading what the agent *said*; it is wrong here, because the way an episode
    reaches the other arm's content is `cat` — and the file's contents come back inside a
    `tool_result`, which that blob never looks at. A containment check that cannot see tool output
    is a containment check that passes.
    """
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, str):
            found.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    walk(result.transcript or [])
    walk(result.error or "")
    return "\n".join(found)


def arm_contamination(
    text: str, condition: Condition, skills_path: Path | None = None
) -> str:
    """Did this episode read content belonging to an arm it is not in? Returns a reason, or "".

    36 of 108 episodes in the full matrix answered "there is no document here" by searching the
    host, and between them turned up `INSTRUCTIONS.md` in two concurrent sandboxes and in the
    repo itself. None of them opened one — verified across all 108 — so the matrix stands. It
    stands by luck: an agent that ran `find` and then `cat` on the first hit would have moved
    itself into the opposite arm, and every rate would have absorbed it silently.

    What this can and cannot see is worth being exact about, because a containment check that is
    trusted for more than it does is worse than none:

    - It catches **verbatim** content — the agent read the file and the bytes came back. That is
      the failure mode that actually occurred, and the only one with a crisp signature.
    - It does not catch **paraphrase**. An agent that reads the document and restates it in its
      own words is contaminated and will pass this check. Nothing short of a judge sees that, and
      a judge asked to decide it would be guessing.
    - It does not fire on **paths**. `find` printing `/tmp/.../INSTRUCTIONS.md` is the search, not
      the read, and the search alone leaves the arm intact. Only body lines are fingerprinted.

    The fingerprint is subtracted, not merely collected: anything the episode is entitled to see
    in its own arm is removed first. There is currently no overlap at all between the documents,
    the skill and the cases, so the subtraction removes nothing — it is there so that the day
    someone quotes the guardrail table into the skill, this check reports contamination in the
    episodes that have it rather than in every episode at once.
    """
    document_lines = distinctive_lines(DOCUMENTS)
    skill_sources = [path for path in (skills_path,) if path]
    skill_lines = distinctive_lines(
        path for source in [*skill_sources, REPO / SKILLS_DIR / "candidates"]
        for path in Path(source).rglob("*.md")
    )

    entitled: set[str] = set()
    if condition.doc:
        entitled |= document_lines
    if condition.skills != "none":
        entitled |= skill_lines
    # The case's own files are visible in every arm.
    for case in (BENCHMARK / "cases").iterdir():
        if not case.is_dir():
            continue
        entitled |= distinctive_lines(case / name for name in VISIBLE)
        if (case / "assets").is_dir():
            entitled |= distinctive_lines(
                asset for asset in (case / "assets").iterdir() if asset.is_file()
            )

    seen = {line.strip() for line in text.splitlines()}
    for label, fingerprint, expected in (
        ("INSTRUCTIONS.md", document_lines, condition.doc),
        ("the skill under test", skill_lines, condition.skills != "none"),
    ):
        if expected:
            continue
        found = sorted(seen & (fingerprint - entitled))
        if found:
            return (
                f"condition is {condition.label} but the transcript contains verbatim text from "
                f"{label}: {found[0][:90]!r}"
            )
    return ""


# Commands whose whole purpose is to look somewhere, so a path argument to one is a search.
# `find` is the one that actually fired; the rest are the same move by another route.
SEARCH_COMMANDS = ("find", "locate", "mdfind", "fd", "rg", "grep", "ls", "cat", "head", "tail")


def in_fiction_roots(limits: dict) -> tuple[str, ...]:
    """The cluster's own filesystem roots, from the file the detectors already score against.

    `/scratch/$USER` is not an escape. It is where the centre's document says job output belongs,
    and an agent that goes there is following the intervention — on the echo-stub substrate it
    finds nothing, because nothing executes. Counting it as an escape would put the doc-present
    arm at the top of the containment table for obeying the document, which is the opposite of
    what the number is for.

    Taken from `detectors.json` rather than listed here: `center.yaml` is the only descriptor of
    this cluster, and a second hand-maintained copy of its mount points is exactly the drift
    `render.py` exists to prevent.
    """
    filesystem = limits.get("filesystem") or {}
    paths = [
        *(filesystem.get("bulk_output_paths") or []),
        *(filesystem.get("forbidden_bulk_output_paths") or []),
    ]
    # First segment only: `/scratch/$USER` and a bare `ls /scratch` are the same fiction.
    return tuple(sorted({f"/{path.strip('/').split('/')[0]}" for path in paths if path}))


def sandbox_escape(text: str, root: Path, in_fiction: tuple[str, ...] = ()) -> list[str]:
    """Commands in the transcript that reach outside this episode's own sandbox.

    Reported, never scored. `arm_contamination` answers "did this episode read the other arm's
    content", which is the question that decides whether a rate is valid, and it deliberately
    ignores paths: `find` printing a path is the search, not the read, and the search alone
    leaves the arm intact. That is the right call for validity and it leaves the harness unable
    to say a search happened at all.

    So this is the other half, and it is a *count* rather than a verdict. In the 108-episode
    matrix 36 episodes searched the host filesystem and between them turned up `INSTRUCTIONS.md`
    in two concurrent sandboxes and in the repo itself; none opened one. Nothing in the harness
    recorded that — it is known because a judge mentioned it in free-text notes, which is not a
    measurement and does not survive a change of judge.

    An episode that searches outside its sandbox is not invalid. It is an episode whose
    containment held for a reason nobody chose, and a run where that number moves is a run where
    the next `cat` lands.
    """
    # Both spellings of this episode's own root. macOS resolves `/tmp` to `/private/tmp`, so the
    # agent's own absolute paths come back under a prefix the harness never wrote down — and a
    # check that misses that reports every episode as having escaped from itself.
    text_root = str(root)
    mine = tuple({text_root, text_root.replace("/private/tmp/", "/tmp/", 1),
                  text_root.replace("/tmp/", "/private/tmp/", 1)})

    escapes: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        head = stripped.split(" ", 1)[0].rsplit("/", 1)[-1]
        if head not in SEARCH_COMMANDS:
            continue
        # Absolute paths only. A relative argument cannot leave the sandbox without `..`, and
        # `find .` is the correct, contained way to answer "is there a document here".
        for argument in stripped.split():
            if not argument.startswith("/") or argument.startswith(mine):
                continue
            if in_fiction and argument.startswith(in_fiction):
                continue
            escapes.append(stripped[:200])
            break
    return sorted(set(escapes))


def assert_nothing_withheld_leaked(work: Path) -> None:
    """The one invariant that cannot be checked after the fact.

    A leaked `rubric.md` does not announce itself in the results — the episode just scores
    suspiciously well. So it is checked here, by content rather than by filename, because a
    rubric copied in under another name leaks exactly as much.
    """
    # Fingerprint every case's withheld lines, then subtract everything legitimately visible.
    # Two reasons this has to span all cases and both sides:
    #   - keying by filename (as this once did) collapses to a single case, since every case has a
    #     rubric.md / case.yaml / reference.sh; which one survived depended on directory iteration
    #     order, so the guard silently covered only one of nine (green on macOS, red on ext4).
    #   - a withheld reference.sh shares boilerplate with the visible job.sh and assets it fixes
    #     (#SBATCH headers, module loads, output paths). Those lines are not secret, so they are
    #     subtracted — otherwise a legitimate asset like B3's train.sh trips the check.
    def long_lines(path: Path) -> set[str]:
        try:
            return {
                line.strip() for line in path.read_text().splitlines()
                if len(line.strip()) > 40
            }
        except (UnicodeDecodeError, OSError):
            return set()

    withheld_lines: set[str] = set()
    visible_lines: set[str] = set()
    for case in (BENCHMARK / "cases").iterdir():
        if not case.is_dir():
            continue
        for name in WITHHELD:
            withheld_lines |= long_lines(case / name)
        for name in VISIBLE:
            visible_lines |= long_lines(case / name)
        if (case / "assets").is_dir():
            for asset in (case / "assets").iterdir():
                if asset.is_file():
                    visible_lines |= long_lines(asset)
    # The document is legitimately in the sandbox in the doc-present arm.
    visible_lines |= long_lines(GENERATED / "INSTRUCTIONS.md")
    leaked_lines = withheld_lines - visible_lines

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


# Failures that belong to the harness's environment rather than to the agent under test.
#
# The distinction matters more here than the wording suggests. Every one of these strings means
# "the episode never happened"; none of them means "the agent behaved badly". Reporting them
# through the same channel as agent conduct is how a dead credential becomes a research finding.
ENVIRONMENT_FAILURES = (
    ("OAuth access token has been revoked", "authentication"),
    ("authentication_failed", "authentication"),
    ("Invalid API key", "authentication"),
    ("Please run /login", "authentication"),
    ("Credit balance is too low", "billing"),
    ("rate_limit_error", "rate limit"),
    ("overloaded_error", "API capacity"),
)


# How many environment failures in a row before a run gives up.
#
# Not one: a single overloaded-API episode is worth riding out, and `--retries` already re-attempts
# those. Not never: the 90-episode matrix that motivated this ran for four hours and produced a
# complete-looking results file in which no episode had happened. Three consecutive failures,
# across different cases and conditions, is not weather.
#
# The counter resets on any episode that runs, so a merely flaky run continues.
ABORT_AFTER = 3


def environment_failure(result: runner_module.RunResult) -> tuple[str, str]:
    """Name an environment failure in the runner's own output. Returns (kind, evidence).

    A whole 90-episode matrix once came back reading `INVALID — no tool use, no commands and no
    stub calls — nothing indicates the agent acted`. True, and useless: every record also carried
    `API Error: 401 ... OAuth access token has been revoked`, which says exactly what went wrong
    and exactly who has to fix it. The harness had the diagnosis in hand and reported the symptom.

    Worth being precise about why this is not a cosmetic complaint. "The agent did nothing" is a
    claim about the agent — it is the same sentence the harness prints for a model that read the
    script and declined to act, which is a real and interesting behaviour. Printing it for a
    revoked token puts a statement about the operator's credentials into the column reserved for
    statements about model conduct.
    """
    texts: list[str] = []
    for event in result.transcript or []:
        if event.get("error"):
            texts.append(str(event["error"]))
        for block in ((event.get("message") or {}).get("content") or []):
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(str(block.get("text") or ""))
        if event.get("type") == "result":
            texts.append(str(event.get("result") or ""))
    if result.error:
        texts.append(result.error)
    blob = "\n".join(texts)
    for needle, kind in ENVIRONMENT_FAILURES:
        if needle in blob:
            line = next(
                (part for part in blob.splitlines() if needle in part), needle
            )
            return kind, line.strip()[:160]
    return "", ""


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

    # Ahead of the no-output branch, because that branch's wording ("no output") is what `--retries`
    # keys on, and re-attempting a revoked token just spends the timeout again. Retry is for
    # failures that might not recur; a dead credential recurs by definition.
    kind, evidence = environment_failure(result)
    if kind and not result.commands:
        return "invalid", (
            f"{kind} failed before the agent acted — this is the harness's environment, not the "
            f"agent's conduct: {evidence}"
        )

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
    episode_token: str | None = None,
) -> dict:
    case_dir = BENCHMARK / "cases" / case_id
    if not case_dir.is_dir():
        raise SystemExit(f"no such case: {case_id}")
    case = yaml.safe_load((case_dir / "case.yaml").read_text())
    limits = detect.load_detector_limits(GENERATED / "detectors.json")

    # An opaque token, not `{case}-{label}-s{seed}`, and this is not cosmetic.
    #
    # The sandbox directory name is the agent's working directory, and the old one read
    # `/tmp/hpcbench-C3-wrong-partition-doc-present_skills-none-s0-…`. Two things were in it that
    # nothing else in the episode is allowed to say: the case id, which names the defect
    # (`wrong-partition`, `over-request`, `poll-storm`), and the arm label, which says an
    # experiment is running and which cell this is. Measured across the surviving transcripts of
    # the 108-episode matrix: that path appears in the model's own tool calls in **81 of 81**,
    # because the runner puts the cwd in context and the agent then uses absolute paths. PR #44
    # spent a whole pass removing exactly this content from the fixture docstrings while it sat
    # in every episode's cwd.
    #
    # `HPCBENCH_EPISODE` carried the same string and reaches two further places the agent can
    # read: its own environment, and `runtime/calls.jsonl`, which its own `sbatch` writes. Neither
    # fired in those 81 — no agent ran `env` and none opened the call log — but 72 of them had
    # `/runtime` in the transcript, so it held for the same reason #36 held: luck.
    #
    # The token is the only name the episode can see. The mapping back to (case, condition, seed)
    # lives in the record, which the agent never reads.
    token = episode_token or secrets.token_hex(8)
    root = sandbox_root or Path(f"/tmp/hpcbench-{token}")
    sandbox = root / "sandbox"
    environment = materialize(case_dir, sandbox, condition, skills_path)
    environment["HPCBENCH_EPISODE"] = token
    work, runtime = sandbox / "work", sandbox / "runtime"
    intervention = intervention_digest(work, condition)

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
        environment["HPCBENCH_EPISODE"] = token
        # Re-taken rather than carried over: the retry rebuilt the sandbox, and a stamp that
        # described the discarded attempt would be a provenance record of the wrong episode.
        intervention = intervention_digest(work, condition)
        result = runner.run(work, prompt, environment, timeout_s)
        append_transcript_records(runtime, result)
        records = read_call_log(runtime)
        validity, reason = episode_validity(result, records)

    # After the retries, and only over an episode that acted.
    #
    # Ordered below `invalid` on purpose: an episode with no evidence the agent did anything has
    # no conduct to contaminate, and relabelling it would lose the diagnosis that says the token
    # was dead. Above `partial`, because a truncated episode in the wrong arm is still in the
    # wrong arm — `partial` says how much of the record survived, `contaminated` says the record
    # is about the wrong comparison, and only one of those can be repaired by reading the scripts.
    contamination = ""
    escapes: list[str] = []
    if validity != "invalid":
        transcript = transcript_text(result)
        contamination = arm_contamination(transcript, condition, skills_path)
        if contamination:
            validity, reason = "contaminated", contamination
        # Counted, not scored, and deliberately after the verdict above so it cannot change one.
        # An episode that searched outside its sandbox and read nothing is a valid episode; it is
        # also the one that was a `cat` away from being invalid, and that has to be a number.
        escapes = sandbox_escape(transcript, root, in_fiction_roots(limits))

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
        # The label says which cell. This says which *version* of that cell — see
        # `intervention_digest`. Two records with the same label and different digests were not
        # run against the same experiment, and nothing else in the record would show it.
        "intervention": intervention,
        # The only name the episode itself could see. Kept here so a sandbox, a call log or a
        # stray path in a transcript can still be traced back to the cell that produced it —
        # the mapping moved out of the agent's reach, it did not stop existing.
        "episode_token": token,
        # Containment as a measurement rather than an anecdote. `validity` says whether the arm
        # held; this says how close it came. Empty is the answer we want and is still recorded,
        # because "no episode searched out" is only a finding if the field exists when it is true.
        "sandbox_escape": escapes,
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
        # Recorded whether or not it fired, so a results file says which of "no contamination" and
        # "no check" it means. A field that only appears when something went wrong cannot
        # distinguish a clean run from a run made before the check existed.
        "arm_contamination": contamination or None,
        # Empty unless the runner itself failed. Read by the run loop to decide whether continuing
        # can produce anything, and by anyone auditing a results file after the fact — an operator
        # handed 90 records has to be able to tell "the model never caught this" from "the token
        # was dead", and `validity: invalid` alone does not carry that.
        "environment_failure": environment_failure(result)[0],
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
    # `None`, not `False`, when the episode cannot be scored. An episode where the agent never
    # acted carries no information about whether the defect would have been caught, and a `False`
    # here is what turns a broken run into a publishable-looking zero. A contaminated episode is
    # excluded the same way and for a sharper reason: it has a real outcome, but the outcome
    # belongs to neither arm, so counting it as a pass or a failure corrupts the comparison rather
    # than merely diluting it.
    episode["l1"]["prevented"] = (
        (
            episode["l1"]["static"]["verdict"] == "pass"
            and episode["l1"]["call_log"]["verdict"] in ("pass", "not_applicable")
        )
        if validity not in report.UNSCOREABLE else None
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
        # Never overwrite. The stem has no run id in it, so two runs into the same `--results`
        # collide cell for cell — and that is not hypothetical: a later `scripted-asis`
        # calibration overwrote 27 of the 108-episode matrix's transcripts, every one of them
        # from `doc-absent_skills-none`, which is the arm #36 is about. The records still point
        # at those stems; what is behind them is a different run. `results/` is append-only by
        # convention and nothing enforced it.
        #
        # Suffixed rather than refused, because this runs after the episode has been paid for and
        # aborting here would discard the thing it is trying to protect. The CLI gives each run
        # its own directory, so in normal use this never fires; when it does, the token says which
        # episode the extra copy belongs to and the record carries the same token.
        stem = f"{case_id}__{condition.label}__seed{seed}"
        if (artifacts_dir / f"{stem}.transcript.json").exists():
            stem = f"{stem}__{token}"
        (artifacts_dir / f"{stem}.transcript.json").write_text(
            json.dumps(result.transcript, indent=1) + "\n"
        )
        (artifacts_dir / f"{stem}.calls.jsonl").write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in records)
        )
        (artifacts_dir / f"{stem}.scripts.json").write_text(
            json.dumps(scripts, indent=1) + "\n"
        )
        # Relative to the artifacts root, not bare, so a record still resolves once the run has
        # its own subdirectory. `judge.artifacts_for` joins this with `/`, so an old record's
        # bare stem and a new record's `<run>/<stem>` both resolve with no change there.
        episode["artifacts"] = str(
            (artifacts_dir / stem).relative_to(artifacts_dir.parent)
            if artifacts_dir.parent.name == "artifacts" else stem
        )

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
    # Three, not one, and not the five the pilot used. A single seed cannot tell a result from a
    # coin flip, so one was never a defensible default for a real run.
    #
    # The choice of three over five is a deliberate trade, and it costs something. `docs/
    # first-run-results.md` finding 6 records that at *five* seeds four of nine cases still
    # flipped, and that ~20 per cell is what 80% power would need — so three makes per-cell
    # stability worse, not better, and more cells will be marked unstable. What it buys is the
    # complete 2×2: at 9 cases × 4 conditions, three seeds is 108 episodes where five is 180, and
    # the pilot could only afford two of the four arms. The project's thesis is about the
    # interaction of the document and the skills, and no number of seeds in half the matrix says
    # anything about an interaction. Breadth first, depth second.
    #
    # This is a default, not a claim that three is enough. Raise it for any run whose purpose is
    # to settle a per-cell question rather than to populate the grid.
    parser.add_argument("--seeds", type=int, default=3,
                        help="repeats per (case, condition); the same task, a different sample")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--skills", type=Path, default=None,
                        help="path to the skill bundle under test")
    parser.add_argument("--results", type=Path, default=REPO / "results",
                        help="where episode records are appended")
    parser.add_argument("--keep", action="store_true", help="keep sandboxes for inspection")
    parser.add_argument("--include-drafts", action="store_true",
                        help="also run cases marked draft: true, which the review gate excludes")
    parser.add_argument("--skip-live-preflight", action="store_true",
                        help="skip the one live call that checks a nested session can "
                             "authenticate (the free static check still runs)")
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

    # Refuse to start a run that cannot authenticate, rather than discovering it once per episode.
    #
    # The abort-after-three guard already caps the damage, but three episodes is still three
    # timeouts and a results file, and the message arrives per-episode as though it were about the
    # agent. This is the same fact stated once, before anything is spent, in the operator's terms.
    if arguments.runner == "claude-code":
        probe_runner = build_runner(arguments.runner, arguments.model, "", arguments.max_turns)
        ok, why = runner_module.ClaudeCodeRunner.credentials_reachable()
        if not ok:
            raise SystemExit(f"preflight: {why}")
        print(f"preflight: {why}", file=sys.stderr)
        if not arguments.skip_live_preflight:
            ok, why = probe_runner.preflight(arguments.results / "preflight")
            if not ok:
                raise SystemExit(
                    f"preflight: {why}\n"
                    f"  Nothing has been spent on episodes. Fix the environment and re-run, or "
                    f"pass --skip-live-preflight to run anyway."
                )
            print(f"preflight: {why}\n", file=sys.stderr)

    consecutive_environment_failures = 0
    aborted = ""

    # Open the results file BEFORE the first episode and append as we go.
    #
    # It used to be written once, after the loop. A run stopped at any point — Ctrl-C, a laptop
    # sleeping, a decision to change course four hours in — therefore produced no records at all,
    # having spent the money. That happened: fifteen episodes and the API charges for them, kept
    # only as raw transcripts nobody had scored.
    #
    # An overnight run is exactly the case where this matters, because nobody is watching it, and
    # the failure mode is silent: the file simply never appears.
    arguments.results.mkdir(parents=True, exist_ok=True)
    run_stamp = time.strftime("%Y%m%dT%H%M%S")
    destination = arguments.results / f"episodes-{run_stamp}.jsonl"
    results_handle = destination.open("w")
    # Per run, not shared. The results file has always been stamped; the artifacts beside it were
    # not, so every run after the first overwrote its predecessor's transcripts cell by cell.
    artifacts = arguments.results / "artifacts" / run_stamp

    episodes = []
    for case_id in cases:
        if aborted:
            break
        runner = build_runner(arguments.runner, arguments.model, case_id, arguments.max_turns)
        for condition in conditions:
            if aborted:
                break
            for seed in range(arguments.seeds):
                episode = run_episode(
                    case_id, condition, runner, seed=seed, timeout_s=arguments.timeout,
                    skills_path=arguments.skills, keep=arguments.keep,
                    artifacts_dir=artifacts,
                    retries=arguments.retries,
                )
                episodes.append(episode)
                # Flushed per episode, not buffered. A record that exists only in this process's
                # memory is a record that does not survive whatever stops the process.
                results_handle.write(json.dumps(episode, sort_keys=True) + "\n")
                results_handle.flush()
                cost = episode.get("cost") or {}
                money = f" ${cost['usd']:.3f}" if cost.get("usd") else ""
                if episode.get("environment_failure"):
                    consecutive_environment_failures += 1
                else:
                    consecutive_environment_failures = 0
                if episode["validity"] == "invalid":
                    print(
                        f"  {case_id:24s} {condition.label:34s} seed{seed}  "
                        f"INVALID — {episode['invalid_reason'][:90]}",
                        flush=True,
                    )
                    if consecutive_environment_failures >= ABORT_AFTER:
                        aborted = episode["environment_failure"]
                        break
                    continue
                if episode["validity"] == "contaminated":
                    # Loud, and while the run is still going. Contamination is a property of the
                    # setup rather than of one agent, so the second occurrence is nearly certain
                    # once there is a first — an operator who sees this at episode 3 can stop and
                    # fix it instead of paying for the other 105.
                    print(
                        f"  {case_id:24s} {condition.label:34s} seed{seed}  "
                        f"CONTAMINATED — {episode['arm_contamination'][:90]}",
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

    results_handle.close()

    valid = [episode for episode in episodes if episode["validity"] == "ok"]
    partial = [episode for episode in episodes if episode["validity"] == "partial"]
    invalid = [episode for episode in episodes if episode["validity"] == "invalid"]
    contaminated = [
        episode for episode in episodes if episode["validity"] == "contaminated"
    ]
    spend = sum((episode.get("cost") or {}).get("usd") or 0 for episode in episodes)

    print()
    if aborted:
        # Before the invalid list, and before anything that looks like a number. A results file
        # written by an aborted run covers a fraction of the matrix it was asked for, and the one
        # way to make that dangerous is to let it print like a finished one.
        print(
            f"RUN ABORTED after {ABORT_AFTER} consecutive {aborted} failures.\n"
            f"  {len(episodes)} of {len(cases) * len(conditions) * arguments.seeds} episodes were "
            f"attempted. This is an environment failure, not a result:\n"
            f"  nothing here says anything about any agent, and the cells that never ran are\n"
            f"  missing rather than negative. Fix the environment and start again.\n"
        )
        if aborted == "authentication":
            print(
                "  For authentication specifically: the runner spawns a fresh CLI session per\n"
                "  episode, so it needs credentials that are valid now — not the ones this\n"
                "  process started with. Re-authenticate in an interactive terminal and re-run.\n"
            )
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
    if contaminated:
        # A different sentence from the invalid one, deliberately. "Excluded" is what happened to
        # these episodes; it is not what the operator needs to know. One contaminated episode means
        # the arms are not isolated, which is a statement about every other episode in the run —
        # including the ones that passed this check by not leaving verbatim evidence.
        print(
            f"{len(contaminated)}/{len(episodes)} episodes CONTAMINATED and excluded — an arm "
            f"reached the other arm's content:"
        )
        for episode in contaminated[:5]:
            print(f"  - {episode['case']} {episode['condition']['label']}: "
                  f"{episode['arm_contamination'][:90]}")
        if len(contaminated) > 5:
            print(f"  ... and {len(contaminated) - 5} more")
        print(
            "  This is a property of the setup, not of these episodes. The rest of the run is "
            "suspect:\n"
            "  the check sees verbatim text only, so an agent that read and paraphrased is "
            "counted as clean."
        )
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
