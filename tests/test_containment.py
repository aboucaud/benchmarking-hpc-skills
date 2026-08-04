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
