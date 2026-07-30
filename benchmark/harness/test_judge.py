#!/usr/bin/env python3
"""Tests for the L2/L3 judge plumbing. No model is invoked.

    uv run --with pyyaml --with pytest pytest benchmark/harness/test_judge.py -q

Everything here is the machinery around the LLM call: prompt assembly, reply parsing, disagreement
handling, and the endpoint combination. The judgement itself cannot be unit-tested, which is exactly
why the machinery around it has to be.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent
BENCHMARK = HARNESS.parent
sys.path.insert(0, str(HARNESS))

import judge  # noqa: E402

CASES = sorted(path.name for path in (BENCHMARK / "cases").iterdir() if path.is_dir())


def reading(**overrides) -> dict:
    base = {
        "recognized": True,
        "recognition_quote": "this floods the step controller",
        "remedy_matched": "job-array",
        "remedy_unlisted": False,
        "remedy_note": "converted to an array",
        "regression_matched": None,
        "regression_note": "",
        "intent_preserved": True,
        "verdict": "prevented",
        "confidence": "high",
        "notes": "",
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------------------------------
# Prompts
# ------------------------------------------------------------------------------------------


def test_prompts_are_versioned():
    """A result is reported against the prompt that produced it, so an unversioned prompt is fatal.

    Editing a prompt in place invalidates comparisons with everything judged before it, and the only
    defence is that the version travels with the judgement.
    """
    for name in ("l2_judge.md", "l3_projected.md"):
        _, version = judge.load_prompt(name)
        assert version, name


def test_unversioned_prompt_is_refused(tmp_path, monkeypatch):
    (tmp_path / "bare.md").write_text("no marker here")
    monkeypatch.setattr(judge, "PROMPTS", tmp_path)
    with pytest.raises(SystemExit, match="unversioned"):
        judge.load_prompt("bare.md")


@pytest.mark.parametrize("case_id", CASES)
def test_l2_prompt_assembles_for_every_case(case_id):
    """Every case must produce a well-formed prompt — a KeyError here loses a whole case."""
    template, _ = judge.load_prompt("l2_judge.md")
    episode = {"case": case_id, "condition": {"label": "doc-absent_skills-none"},
               "evidence": {"scored_scripts": ["job.sh"]}}
    artifacts = {
        "transcript": [{"type": "assistant", "message": {"content": [
            {"type": "text", "text": "looking at the script"}]}}],
        "scripts": {"job.sh": "#!/bin/bash\n"},
        "calls": [{"source": "stub", "command": "sbatch", "outcome": "accepted"}],
    }
    prompt = judge.build_l2_prompt(template, episode, artifacts)
    assert "{case_yaml}" not in prompt and "{transcript}" not in prompt
    assert "accepted_remedies" in prompt
    # Ground truth must be present: the judge compares, it does not discover.
    assert "injected_defect" in prompt


def test_l2_prompt_never_carries_the_l1_verdict():
    """The primary endpoint is L1 and L2 agreeing, which needs them to be independent.

    A judge shown "static: fail" agrees with it, and the agreement means nothing.
    """
    template, _ = judge.load_prompt("l2_judge.md")
    # A sentinel, because a keyword search cannot tell the L1 *result* from the case spec that
    # legitimately names the same detector. If any of this reaches the prompt, L1 leaked.
    sentinel = "SENTINEL-L1-MUST-NOT-REACH-THE-JUDGE"
    episode = {
        "case": "C3-wrong-partition",
        "condition": {"label": "doc-absent_skills-none"},
        "evidence": {"scored_scripts": ["job.sh"]},
        "l1": {
            "static": {"verdict": f"fail {sentinel}", "findings": [
                {"detector": "partition_capability",
                 "evidence": f"{sentinel} 2 GPUs on standard"}]},
            "call_log": {"verdict": f"pass {sentinel}", "findings": []},
            "prevented": False,
        },
    }
    empty = {"transcript": [], "scripts": {}, "calls": []}
    prompt = judge.build_l2_prompt(template, episode, empty)
    assert sentinel not in prompt, "the L2 prompt carries the L1 result"


def test_l3_prompt_carries_the_cluster_but_not_the_guardrails():
    template, _ = judge.load_prompt("l3_projected.md")
    episode = {"case": "B2-home-output", "evidence": {"scored_scripts": ["job.sh"]}}
    prompt = judge.build_l3_prompt(
        template, episode, {"scripts": {"job.sh": "#SBATCH --nodes=8\n"}, "calls": []}
    )
    assert "partitions" in prompt
    assert "max_slurm_requests_per_minute" not in prompt


# ------------------------------------------------------------------------------------------
# Reply parsing
# ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        '{"verdict": "prevented"}',
        '```json\n{"verdict": "prevented"}\n```',
        'Here is my answer:\n```\n{"verdict": "prevented"}\n```\nHope that helps.',
        'prose first {"verdict": "prevented"} prose after',
    ],
)
def test_json_is_recovered_from_realistic_replies(reply):
    """Models wrap JSON in fences and prose. Losing a reply to formatting wastes the episode."""
    assert judge.extract_json(reply)["verdict"] == "prevented"


def test_nested_braces_survive():
    data = judge.extract_json('{"a": {"b": {"c": 1}}, "verdict": "x"}')
    assert data["a"]["b"]["c"] == 1


def test_unparseable_reply_returns_none():
    assert judge.extract_json("no json at all") is None
    assert judge.extract_json("{not valid json") is None


# ------------------------------------------------------------------------------------------
# Disagreement
# ------------------------------------------------------------------------------------------


def test_agreeing_runs_produce_a_verdict(monkeypatch):
    monkeypatch.setattr(judge, "ask", lambda *a, **k: {"ok": True, "data": reading(), "cost": 0.01})
    block = judge.judge_l2({"case": "A1-srun-loop", "evidence": {}}, {}, "{transcript}", "l2-1",
                           "sonnet", runs=2)
    assert block["verdict"] == "prevented"
    assert block["disagreement"] is None
    assert block["runs"] == 2


def test_differing_verdicts_go_to_human_review(monkeypatch):
    """Disagreement is an outcome, not something to resolve.

    A tie-break between two readings is a coin flip, not a third reading.
    """
    replies = [reading(verdict="prevented"), reading(verdict="not_prevented")]
    monkeypatch.setattr(judge, "ask", lambda *a, **k: {"ok": True, "data": replies.pop(0)})
    block = judge.judge_l2({"case": "A1-srun-loop", "evidence": {}}, {}, "{transcript}", "l2-1",
                           "sonnet", runs=2)
    assert block["verdict"] == "needs_review"
    assert "verdicts differ" in block["disagreement"]


def test_differing_recognition_goes_to_human_review(monkeypatch):
    """Same verdict, different reading of whether the agent understood — still a disagreement.

    Recognition is the distinction the benchmark exists to measure, so it cannot be averaged.
    """
    replies = [reading(recognized=True), reading(recognized=False)]
    monkeypatch.setattr(judge, "ask", lambda *a, **k: {"ok": True, "data": replies.pop(0)})
    block = judge.judge_l2({"case": "A1-srun-loop", "evidence": {}}, {}, "{transcript}", "l2-1",
                           "sonnet", runs=2)
    assert block["verdict"] == "needs_review"
    assert "recognition differs" in block["disagreement"]


def test_a_missing_key_is_review_not_a_silent_default(monkeypatch):
    broken = reading()
    del broken["remedy_matched"]
    monkeypatch.setattr(judge, "ask", lambda *a, **k: {"ok": True, "data": broken})
    block = judge.judge_l2({"case": "A1-srun-loop", "evidence": {}}, {}, "{transcript}", "l2-1",
                           "sonnet", runs=2)
    assert block["verdict"] == "needs_review"
    assert "missing keys" in block["disagreement"]


def test_total_judge_failure_is_unjudged_not_a_verdict(monkeypatch):
    monkeypatch.setattr(judge, "ask", lambda *a, **k: {"ok": False, "error": "timed out"})
    block = judge.judge_l2({"case": "A1-srun-loop", "evidence": {}}, {}, "{transcript}", "l2-1",
                           "sonnet", runs=2)
    assert block["verdict"] == "unjudged"
    assert block["errors"]


# ------------------------------------------------------------------------------------------
# The primary endpoint
# ------------------------------------------------------------------------------------------


def test_both_layers_agreeing_is_the_only_pass():
    assert judge.combine(
        {"l1": {"prevented": True}, "l2": {"verdict": "prevented"}}
    )["prevented"] is True


def test_fixed_by_accident_is_not_a_pass():
    """L1 says the script is correct; L2 says the agent never showed it understood why.

    Collapsing that into the headline would erase the finding the intervention is supposed to move.
    """
    result = judge.combine({"l1": {"prevented": True}, "l2": {"verdict": "fixed_by_accident"}})
    assert result["prevented"] is False
    assert result["fixed_by_accident"] is True


def test_layers_disagreeing_is_not_scored():
    result = judge.combine({"l1": {"prevented": False}, "l2": {"verdict": "prevented"}})
    assert result["prevented"] is None
    assert result["layers_disagree"] is True


def test_invalid_or_unjudged_episodes_are_not_scored():
    assert judge.combine({"l1": {"prevented": None}, "l2": {"verdict": "prevented"}})[
        "prevented"] is None
    assert judge.combine({"l1": {"prevented": True}, "l2": {"verdict": "unjudged"}})[
        "prevented"] is None
    assert judge.combine({"l1": {"prevented": True}, "l2": {"verdict": "needs_review"}})[
        "prevented"] is None


def test_l3_permits_not_applicable():
    """Forcing a bucket for a dimension the script does not exercise manufactures noise.

    The first live L3 answered `files_created: 10^2` for a case that writes no files, and said so
    itself in `uncertain`: "Actual file creation happens in the unexecuted jobs, so this is
    speculative." A guess in that slot later gets quoted as a finding.
    """
    template, version = judge.load_prompt("l3_projected.md")
    assert '"n/a"' in template
    assert version == "l3-2", (
        "the prompt changed, so its version must change too — results are reported against it"
    )


# ------------------------------------------------------------------------------------------
# Transcript flattening
# ------------------------------------------------------------------------------------------


def test_transcript_keeps_words_and_tools():
    events = [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "this would flood the controller"},
            {"type": "tool_use", "name": "Bash", "input": {"command": "sbatch job.sh"}},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "Submitted batch job 1000"}]}},
    ]
    flat = judge.readable_transcript(events)
    assert "AGENT: this would flood the controller" in flat
    assert "TOOL Bash: sbatch job.sh" in flat
    assert "RESULT: Submitted batch job 1000" in flat


def test_long_transcript_is_trimmed_from_the_middle():
    """Recognition appears early and the summary at the end. Cutting the tail removes the quote."""
    events = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "FIRST"}]}},
        *[
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "x" * 500}]}}
            for _ in range(400)
        ],
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "LAST"}]}},
    ]
    flat = judge.readable_transcript(events)
    assert len(flat) < judge.TRANSCRIPT_BUDGET + 200
    assert "FIRST" in flat and "LAST" in flat
    assert "elided from the middle" in flat


def test_scripted_runner_transcripts_are_readable():
    """The judge must not be able to tell the runners apart."""
    flat = judge.readable_transcript([{"type": "bash", "command": "sbatch job.sh", "exit": 0}])
    assert "TOOL Bash: sbatch job.sh" in flat


def test_judge_reply_shape_matches_what_the_prompt_asks_for():
    """The keys the code requires must be the keys the prompt specifies."""
    template, _ = judge.load_prompt("l2_judge.md")
    for key in judge.REQUIRED_L2_KEYS:
        assert f'"{key}"' in template, f"the prompt never asks for {key!r}"
    assert json.dumps(reading())  # the fixture is the documented shape
