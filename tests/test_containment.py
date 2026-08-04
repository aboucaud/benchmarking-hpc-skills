#!/usr/bin/env python3
"""Tests for arm containment — that an episode stayed in the arm its label claims.

    uv run --with pyyaml --with pytest pytest tests/test_containment.py -q

The full matrix had 36 of 108 episodes search the host for the document, and between them they
found `INSTRUCTIONS.md` in two concurrent sandboxes and in the repo itself. None opened one, so
the run stands — but nothing in the harness would have noticed if one had. That is what these
cover (#36).

The check has two failure modes and they are not symmetric, so both directions are pinned:

  - **A missed contamination** silently moves an episode into the opposite arm, and the rates
    absorb it. `test_reading_the_document_in_a_doc_absent_arm_is_contamination` and its
    tool-result variant are the positive controls.
  - **A false contamination** discards a good episode, which is worse than it sounds: it is
    *selective* discarding — episodes that mention the guardrails are exactly the ones where the
    agent engaged with them. `test_a_clean_control_episode_is_not_contaminated` and
    `test_fingerprints_do_not_overlap` are the negative controls, and the second is the one that
    keeps this true as the documents change.

No model is invoked anywhere in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hpcbench.harness import episode as episode_module
from hpcbench.harness import report
from hpcbench.paths import BENCHMARK, GENERATED, REPO

CASE = BENCHMARK / "cases" / "A1-srun-loop"
SKILL = REPO / "skills" / "candidates" / "good" / "hpc-conduct"

CONTROL = episode_module.Condition(doc=False, skills="none")
DOC_ONLY = episode_module.Condition(doc=True, skills="none")
SKILLS_ONLY = episode_module.Condition(doc=False, skills="good")


def a_long_line_from(path):
    """One line long enough to be fingerprinted, so the tests use real text rather than a fixture.

    A fixture would pass forever: the thing being tested is whether *these documents* have a
    distinctive signature, and inventing a string with the right shape tests nothing about them.
    """
    lines = sorted(
        episode_module.distinctive_lines([path]), key=len, reverse=True
    )
    assert lines, f"{path} has no line >= {episode_module.CONTAMINATION_MIN_LINE} chars"
    return lines[0]


# --- the fingerprint holds up ----------------------------------------------------------------

def test_fingerprints_do_not_overlap():
    """No line is shared between the documents, the skill, and what every arm legitimately sees.

    This is the assumption the whole check rests on, and it is a property of the *content* rather
    than of the code — so it can be broken by an edit to a markdown file, by someone who has no
    reason to look at this module. Quoting the guardrail table from INSTRUCTIONS.md into SKILL.md
    would be an entirely reasonable thing to do and would make every `doc-absent skills-good`
    episode contaminated at once.
    """
    documents = episode_module.distinctive_lines(episode_module.DOCUMENTS)
    skill = episode_module.distinctive_lines(SKILL.rglob("*.md"))
    visible = set()
    for case in (BENCHMARK / "cases").iterdir():
        if not case.is_dir():
            continue
        visible |= episode_module.distinctive_lines(
            case / name for name in episode_module.VISIBLE
        )
        if (case / "assets").is_dir():
            visible |= episode_module.distinctive_lines(
                asset for asset in (case / "assets").iterdir() if asset.is_file()
            )

    assert documents, "no distinctive lines in either INSTRUCTIONS.md"
    assert skill, "no distinctive lines in the skill bundle"
    assert not documents & skill, (
        f"the document and the skill share {sorted(documents & skill)[:1]} — every doc-absent "
        f"skills-good episode would read as contaminated"
    )
    assert not documents & visible, f"the document shares text with a case: {documents & visible}"
    assert not skill & visible, f"the skill shares text with a case: {skill & visible}"


def test_both_documents_are_fingerprinted():
    """The Docker substrate serves `agents/INSTRUCTIONS.md`; the echo stub serves the generated
    one. An episode that found the other copy on the host is contaminated by either."""
    assert set(episode_module.DOCUMENTS) == {
        GENERATED / "INSTRUCTIONS.md", REPO / "agents" / "INSTRUCTIONS.md"
    }
    for document in episode_module.DOCUMENTS:
        assert episode_module.arm_contamination(a_long_line_from(document), CONTROL)


# --- positive controls -----------------------------------------------------------------------

def test_reading_the_document_in_a_doc_absent_arm_is_contamination():
    line = a_long_line_from(GENERATED / "INSTRUCTIONS.md")
    reason = episode_module.arm_contamination(f"some chatter\n{line}\nmore chatter", CONTROL)
    assert reason and "INSTRUCTIONS.md" in reason


def test_reading_the_skill_in_a_skills_none_arm_is_contamination():
    line = a_long_line_from(SKILL / "SKILL.md")
    reason = episode_module.arm_contamination(line, CONTROL, skills_path=SKILL)
    assert reason and "skill" in reason


def test_contamination_is_seen_inside_tool_output():
    """The failure mode is `cat`, and the file comes back in a tool_result.

    Not a redundant test. The harness already had a transcript-flattening helper that collects
    assistant `text` blocks only — right for reading what the agent said, and blind to every byte
    the agent actually read. A containment check built on it would pass on the exact event it
    exists to catch.
    """
    line = a_long_line_from(GENERATED / "INSTRUCTIONS.md")
    result = episode_module.runner_module.RunResult(
        transcript=[
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash",
                 "input": {"command": "cat /tmp/other-sandbox/work/INSTRUCTIONS.md"}},
            ]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "content": [{"type": "text", "text": line}]},
            ]}},
        ],
    )
    text = episode_module.transcript_text(result)
    assert line in text
    assert episode_module.arm_contamination(text, CONTROL)


# --- negative controls -----------------------------------------------------------------------

def test_a_clean_control_episode_is_not_contaminated():
    """Ordinary conduct in the control arm, including talking about the things the document
    covers. An agent reasoning about walltime is not an agent that read the document."""
    text = (
        "I looked for INSTRUCTIONS.md and there is none in this directory.\n"
        "There is no skills/ directory either.\n"
        "The script requests 48 hours of walltime, which may exceed the partition limit.\n"
        "I will submit one array job instead of twenty separate submissions.\n"
    )
    assert episode_module.arm_contamination(text, CONTROL) == ""


def test_finding_the_path_is_not_reading_the_file():
    """`find` output names the file; it does not contain it. The search alone leaves the arm
    intact, and 36 of 108 episodes did exactly this much and no more."""
    text = (
        "$ find / -maxdepth 6 -iname 'INSTRUCTIONS.md'\n"
        "/tmp/hpcbench-A1-srun-loop-doc-present_skills-none-s0-1/sandbox/work/INSTRUCTIONS.md\n"
        f"{REPO}/agents/INSTRUCTIONS.md\n"
        "$ find / -type d -iname skills\n"
        "/tmp/hpcbench-A1-srun-loop-doc-absent_skills-good-s2-9/sandbox/work/skills\n"
    )
    assert episode_module.arm_contamination(text, CONTROL) == ""


def test_the_document_is_not_contamination_in_the_arm_that_has_it():
    line = a_long_line_from(GENERATED / "INSTRUCTIONS.md")
    assert episode_module.arm_contamination(line, DOC_ONLY) == ""


def test_the_skill_is_not_contamination_in_the_arm_that_has_it():
    line = a_long_line_from(SKILL / "SKILL.md")
    assert episode_module.arm_contamination(line, SKILLS_ONLY, skills_path=SKILL) == ""


# --- the arm was built as labelled -----------------------------------------------------------

def test_materialize_builds_each_arm_as_labelled(tmp_path):
    for condition in (CONTROL, DOC_ONLY):
        sandbox = tmp_path / condition.label
        episode_module.materialize(CASE, sandbox, condition)
        assert (sandbox / "work" / "INSTRUCTIONS.md").exists() is condition.doc


def test_a_doc_present_arm_with_no_document_is_caught(tmp_path):
    """The quiet direction. A doc-present episode whose document did not arrive runs as a control
    and is counted as an intervention — which does not weaken the result, it moves episodes across
    the comparison, and the direction is toward 'the document does nothing'."""
    episode_module.materialize(CASE, tmp_path, DOC_ONLY)
    (tmp_path / "work" / "INSTRUCTIONS.md").unlink()
    with pytest.raises(AssertionError, match="doc-present but no INSTRUCTIONS.md"):
        episode_module.assert_arm_was_built(tmp_path / "work", DOC_ONLY)


def test_a_control_arm_carrying_the_document_is_caught(tmp_path):
    episode_module.materialize(CASE, tmp_path, CONTROL)
    (tmp_path / "work" / "INSTRUCTIONS.md").write_text("anything")
    with pytest.raises(AssertionError, match="doc-absent but"):
        episode_module.assert_arm_was_built(tmp_path / "work", CONTROL)


def test_a_control_arm_carrying_a_skill_is_caught(tmp_path):
    episode_module.materialize(CASE, tmp_path, CONTROL)
    manifest = tmp_path / "work" / episode_module.SKILLS_DIR / "hpc-conduct" / "SKILL.md"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("anything")
    with pytest.raises(AssertionError, match="skills-none but"):
        episode_module.assert_arm_was_built(tmp_path / "work", CONTROL)


# --- exclusion propagates --------------------------------------------------------------------

def test_contaminated_is_unscoreable_everywhere():
    """One list, so the exclusion cannot be applied in the report and forgotten in the grid."""
    assert "contaminated" in report.UNSCOREABLE
    assert not report.is_scoreable({"validity": "contaminated"})
    assert not report.is_scoreable({"validity": "invalid"})
    assert report.is_scoreable({"validity": "ok"})
    assert report.is_scoreable({"validity": "partial"})


def test_a_contaminated_episode_leaves_no_endpoint():
    """`None`, not `False`. A contaminated episode has a real outcome that belongs to neither arm,
    so counting it as a failure corrupts the comparison rather than merely diluting it."""
    contaminated = {"validity": "contaminated", "l1": {"prevented": None}}
    assert report.endpoint_of(contaminated) is None


def test_the_contamination_field_is_always_present():
    """Absent-when-clean cannot distinguish 'no contamination' from 'no check' — which is exactly
    the question anyone re-reading the 108-episode records will have."""
    source = (
        REPO / "src" / "hpcbench" / "harness" / "episode.py"
    ).read_text()
    assert '"arm_contamination": contamination or None,' in source


# --- which version of the arm was built ------------------------------------------------------
#
# `assert_arm_was_built` answers "did the intervention arrive". These cover the question it
# cannot: *which* intervention. A record that cannot answer that is why #34 (the matrix ran a
# skill `main` did not have) and #29 (two documents, one label) were both invisible in the data.

def test_the_stamp_distinguishes_the_arms(tmp_path):
    control = episode_module.intervention_digest(
        _built(tmp_path / "a", CONTROL), CONTROL
    )
    with_document = episode_module.intervention_digest(
        _built(tmp_path / "b", DOC_ONLY), DOC_ONLY
    )
    assert control["document_sha256"] is None
    assert with_document["document_sha256"]
    assert control["skills_sha256"] is None


def test_an_edited_document_is_a_different_intervention(tmp_path):
    """The point of the stamp. Same label, same code revision, different experimental material."""
    work = _built(tmp_path, DOC_ONLY)
    before = episode_module.intervention_digest(work, DOC_ONLY)
    document = work / "INSTRUCTIONS.md"
    document.write_text(document.read_text() + "\nGPU requests must use `accel`.\n")
    after = episode_module.intervention_digest(work, DOC_ONLY)
    assert before["document_sha256"] != after["document_sha256"]


def test_an_edited_fixture_is_a_different_intervention(tmp_path):
    """Fixtures are experimental material too — removing 'the defect is the partition, not the
    request' from a file the agent reads changed what C3 measures. Without this, no record says
    which side of that change it is on."""
    work = _built(tmp_path, CONTROL)
    before = episode_module.intervention_digest(work, CONTROL)
    (work / "job.sh").write_text((work / "job.sh").read_text() + "\n# and one more thing\n")
    after = episode_module.intervention_digest(work, CONTROL)
    assert before["case_files_sha256"] != after["case_files_sha256"]
    # The document did not move, and a stamp that blurred the two would not localise a change.
    assert before["document_sha256"] == after["document_sha256"]


def test_a_moved_skill_file_is_a_different_intervention(tmp_path):
    """Content-only hashing would call these two bundles identical. Where a skill puts its content
    decides whether an agent finds it, which is half of what the skills arm measures."""
    work = _built(tmp_path, CONTROL)
    root = work / episode_module.SKILLS_DIR / "hpc-conduct"
    (root / "docs").mkdir(parents=True)
    (root / "SKILL.md").write_text("guidance")
    here = episode_module.intervention_digest(work, CONTROL)
    (root / "SKILL.md").rename(root / "docs" / "SKILL.md")
    there = episode_module.intervention_digest(work, CONTROL)
    assert here["skills_sha256"] != there["skills_sha256"]
    # Relative to `skills/`, so the bundle name is part of it — that is the level at which two
    # runs are compared ("which bundle, laid out how"), not "some SKILL.md existed".
    assert here["skills_manifests"] == ["hpc-conduct/SKILL.md"]
    assert there["skills_manifests"] == ["hpc-conduct/docs/SKILL.md"]


def test_the_stamp_is_taken_before_the_agent_runs():
    """An agent that rewrites `INSTRUCTIONS.md` is exactly the episode where the starting content
    matters, and it is the one a post-hoc hash would get wrong."""
    source = (REPO / "src" / "hpcbench" / "harness" / "episode.py").read_text()
    stamped = source.index("intervention = intervention_digest(work, condition)")
    ran = source.index("result = runner.run(work, prompt, environment, timeout_s)")
    assert stamped < ran


# --- the episode cannot learn what it is -----------------------------------------------------
#
# `arm_contamination` above asks whether an episode read the other arm's *content*. These ask a
# prior question: could it work out which case and which arm it is without reading anything? It
# could, three ways, and the first one fired in every episode we still have a transcript for.


def test_the_sandbox_path_names_neither_the_case_nor_the_arm():
    """The cwd used to be `/tmp/hpcbench-C3-wrong-partition-doc-present_skills-none-s0-…`.

    The case id names the defect and the label names the cell, and the runner puts the cwd in the
    model's context — it appears in the model's own tool calls in 81 of the 81 surviving
    claude-code transcripts of the 108-episode matrix. This is the same content #44 removed from
    the fixture docstrings, in a place no fixture test could see.
    """
    source = (REPO / "src" / "hpcbench" / "harness" / "episode.py").read_text()
    construction = source[source.index("token = episode_token or"):]
    construction = construction[:construction.index("\n\n")]
    for leaked in ("case_id", "condition.label", "seed"):
        assert leaked not in construction, (
            f"the sandbox path is built from {leaked}, which the agent can read with `pwd`"
        )


def test_the_episode_environment_variable_is_the_token():
    """`HPCBENCH_EPISODE` reaches the agent's own environment *and* `runtime/calls.jsonl`, which
    its own `sbatch` writes inside the sandbox. Neither was opened in the 81 — but 72 of them had
    `/runtime` in the transcript, so it held for the same reason #36 held."""
    source = (REPO / "src" / "hpcbench" / "harness" / "episode.py").read_text()
    for line in source.splitlines():
        if "HPCBENCH_EPISODE" in line and "=" in line:
            assert line.strip().endswith("= token"), f"leaks the cell: {line.strip()}"


def test_a_search_outside_the_sandbox_is_recorded():
    root = Path("/tmp/hpcbench-abc123")
    found = episode_module.sandbox_escape(
        "find / -maxdepth 6 -iname 'INSTRUCTIONS.md'", root
    )
    assert found and "find /" in found[0]


def test_a_sibling_sandbox_is_outside_this_one():
    """The worst case in #36: `find` returned `INSTRUCTIONS.md` from two *other* episodes'
    sandboxes. A check that asks only "is it under /tmp/hpcbench-" calls that contained."""
    root = Path("/tmp/hpcbench-abc123")
    assert episode_module.sandbox_escape(
        "cat /tmp/hpcbench-def456/sandbox/work/INSTRUCTIONS.md", root
    )


@pytest.mark.parametrize("command", [
    "find . -name INSTRUCTIONS.md",
    "ls -la",
    "cat prompt.md",
    "cat /tmp/hpcbench-abc123/sandbox/work/job.sh",
    "ls /private/tmp/hpcbench-abc123/sandbox/work",
])
def test_staying_inside_is_not_an_escape(command):
    """Both spellings of the episode's own root. macOS resolves `/tmp` to `/private/tmp`, so the
    agent's absolute paths come back under a prefix the harness never wrote down — and a check
    that misses that reports every episode as having escaped from itself."""
    assert episode_module.sandbox_escape(command, Path("/tmp/hpcbench-abc123")) == []


def test_the_clusters_own_filesystem_is_not_an_escape():
    """`/scratch/$USER` is where the document says output belongs. An agent that goes there is
    obeying the intervention, and counting it would put the doc-present arm at the top of the
    containment table for following the document it was given."""
    limits = json.loads((GENERATED / "detectors.json").read_text())
    fiction = episode_module.in_fiction_roots(limits)
    assert fiction == ("/archive", "/home", "/scratch")
    root = Path("/tmp/hpcbench-abc123")
    assert episode_module.sandbox_escape('ls -la /scratch/"$USER"/out', root, fiction) == []
    # And a real escape in the same compound command still counts.
    assert episode_module.sandbox_escape(
        'ls /scratch/$USER; find / -iname INSTRUCTIONS.md', root, fiction
    )


def test_the_in_fiction_roots_come_from_the_generated_descriptor():
    """`center.yaml` is the only descriptor of this cluster. A hand-kept list of its mount points
    here is the second source of truth `render.py` exists to prevent."""
    source = (REPO / "src" / "hpcbench" / "harness" / "episode.py").read_text()
    body = source[source.index("def in_fiction_roots("):source.index("def sandbox_escape(")]
    # A mount point as a *literal* is the second source of truth. Prose that names one to explain
    # the rule is not, so this looks for the quoted form rather than the bare substring.
    for mount in ("/scratch", "/home", "/archive"):
        for literal in (f'"{mount}', f"'{mount}"):
            assert literal not in body, f"{mount} is hardcoded; it belongs to center.yaml alone"


def test_the_escape_is_counted_and_never_scored():
    """An episode that searched and read nothing is valid. It is also the one that was one `cat`
    from invalid, which is why the count exists — and why it must not become a verdict."""
    source = (REPO / "src" / "hpcbench" / "harness" / "episode.py").read_text()
    body = source[source.index("escapes = sandbox_escape("):]
    body = body[:body.index("valid = validity ==")]
    assert "validity" not in body, "sandbox_escape must not be able to change a verdict"
    # And it is taken after the verdict, so it cannot be read as one.
    assert source.index("contamination = arm_contamination(") < source.index(
        "escapes = sandbox_escape("
    )


def _built(sandbox, condition):
    """Materialize `sandbox` and return its work directory."""
    episode_module.materialize(CASE, sandbox, condition)
    return sandbox / "work"
