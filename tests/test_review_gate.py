#!/usr/bin/env python3
"""#10 and #25 — the two things blocked on someone who has run a facility.

    uv run --with pyyaml --with pytest pytest tests/test_review_gate.py -q

Neither is resolved by code and neither should be. What code can do is make the human decision
possible and make it hard to fake, and that is what these cover:

  - **#10** — a sign-off has to name someone. `signed-off` was a bare string, so the gate that
    decides whether anything here counts as evidence was one word anybody could type. An agent
    working in this repo is the case that matters: it has every incentive to clear a blocker and
    no standing whatever to review a Slurm case.
  - **#25** — the threshold that decides the skills result must not move as a side effect of
    analysing it. The calibration tool evaluates candidate rules; it must not install one, and it
    must reproduce the stored run before any counterfactual it prints is worth reading.
"""

from __future__ import annotations

import json

import pytest
import yaml

from hpcbench import controller_calibration as calibration
from hpcbench import review_packet, validate_cases
from hpcbench.paths import BENCHMARK, GENERATED

CASES = sorted(path for path in (BENCHMARK / "cases").iterdir() if (path / "case.yaml").exists())


def signed(**overrides):
    base = {
        "review_status": "signed-off",
        "reviewed_by": "djbard",
        "reviewed_on": "2026-08-03",
        "reviewed_questions": {
            "defect_realistic": "yes",
            "rest_of_script_clean": "yes",
            "remedies_complete": "yes",
        },
    }
    return {**base, **overrides}


# --- #10: a sign-off names someone ------------------------------------------------------------


def test_a_complete_signoff_passes():
    assert validate_cases.check_signoff_is_attributable("X", signed()) == []


@pytest.mark.parametrize("missing", ["reviewed_by", "reviewed_on", "reviewed_questions"])
def test_an_unattributed_signoff_is_rejected(missing):
    """The whole gate, in one assertion: `signed-off` alone is a claim with nobody behind it."""
    problems = validate_cases.check_signoff_is_attributable("X", signed(**{missing: None}))
    assert problems and missing in problems[0]


def test_a_signoff_that_skipped_a_question_says_so():
    """A reviewer who read the script and one who read the remedy list have done different jobs,
    and the second is the one that catches a case marked wrong for a different valid fix."""
    partial = signed(reviewed_questions={"defect_realistic": "yes"})
    problems = validate_cases.check_signoff_is_attributable("X", partial)
    assert any("rest_of_script_clean" in p for p in problems)
    assert any("remedies_complete" in p for p in problems)


def test_attribution_on_a_pending_case_is_rejected():
    """Half a sign-off reads as a whole one to anything grepping for a reviewer's name."""
    problems = validate_cases.check_signoff_is_attributable(
        "X", {"review_status": "pending", "reviewed_by": "djbard"}
    )
    assert problems and "either it is signed off or it is not" in problems[0]


def test_a_plain_pending_case_is_fine():
    assert validate_cases.check_signoff_is_attributable("X", {"review_status": "pending"}) == []


def test_no_case_is_signed_off_yet():
    """The honest state, pinned so it cannot drift quietly in either direction.

    If this fails because a case was genuinely reviewed, delete the case from the list — that is a
    good day. It fails loudly rather than letting a sign-off appear without anyone noticing which
    is which.
    """
    signed_off = {
        path.name for path in CASES
        if yaml.safe_load((path / "case.yaml").read_text()).get("review_status") == "signed-off"
    }
    assert signed_off == set(), (
        f"{sorted(signed_off)} are now signed off — update this test deliberately, and check the "
        f"sign-off names a person"
    )


@pytest.mark.parametrize("case_dir", CASES, ids=lambda path: path.name)
def test_the_committed_review_packet_matches_its_case(case_dir):
    """A stale packet is worse than none: it is what a reviewer signs off against.

    The packets are committed so a sysadmin can click one file instead of opening six, which is
    #10's actual obstacle — and the cost of committing generated content is that it drifts the
    moment anyone edits a case. The packet stamps the digest of everything it quotes; this
    compares that against the tree.
    """
    packet = BENCHMARK.parent / "docs" / "case-review" / f"{case_dir.name}.md"
    assert packet.exists(), (
        f"{case_dir.name} has no review packet — run "
        f"`uv run --with pyyaml src/hpcbench/review_packet.py`"
    )
    assert review_packet.case_digest(case_dir) in packet.read_text(), (
        f"{packet.name} was generated from a different version of {case_dir.name} — regenerate it"
    )


def test_the_packet_quotes_nothing_withheld():
    """A packet that included `reference.sh` or `rubric.md` would have the reviewer reading a
    different object from the one under test.

    Subtracted, not merely collected — the same correction `assert_nothing_withheld_leaked` needed.
    `reference.sh` is `job.sh` with the defect repaired, so it shares its `#SBATCH` headers, module
    loads and output paths with the file the packet is *supposed* to quote. Without the
    subtraction this fires on `INDIR=/scratch/$USER/lightcurve-fit/input`, which is in `job.sh` and
    is not a secret.
    """
    for case_dir in CASES:
        packet = (BENCHMARK.parent / "docs" / "case-review" / f"{case_dir.name}.md").read_text()
        visible = {
            line.strip()
            for name in ("job.sh", "prompt.md")
            if (case_dir / name).exists()
            for line in (case_dir / name).read_text().splitlines()
        }
        if (case_dir / "assets").is_dir():
            visible |= {
                line.strip()
                for asset in (case_dir / "assets").iterdir() if asset.is_file()
                for line in asset.read_text().splitlines()
            }
        for withheld in ("reference.sh", "rubric.md"):
            source = case_dir / withheld
            if not source.exists():
                continue
            secret = {
                line.strip() for line in source.read_text().splitlines()
                if len(line.strip()) >= 40
            } - visible
            leaked = sorted(line for line in secret if line in packet)
            assert not leaked, f"{case_dir.name} packet quotes {withheld}: {leaked[:1]}"


# --- #25: the threshold does not move ---------------------------------------------------------


def test_the_query_budget_is_still_one():
    """Pinned against the one edit #25 exists to prevent: raising the cap after seeing which way
    it moves the skills arm. If this changes, it changes in a PR that says so and the matrix is
    re-run rather than re-scored."""
    limits = json.loads((GENERATED / "detectors.json").read_text())
    assert limits["controller"]["max_calls_per_minute"] == 1


def test_the_calibration_tool_installs_nothing():
    """It evaluates rules. A tool that could also apply one makes the wrong move a one-liner."""
    source = (BENCHMARK.parent / "src" / "hpcbench" / "controller_calibration.py").read_text()
    # The call forms, not the words. The docstring names `center.yaml` in order to say it does not
    # touch it, and a substring check cannot tell that from touching it.
    for forbidden in (".write_text(", ".write_bytes(", ".mkdir(", ".unlink(", ".rename(",
                      '"center.yaml"', "'center.yaml'", 'open(', "safe_dump("):
        assert forbidden not in source, f"the calibration tool can write ({forbidden!r})"


def test_a_rule_over_the_stored_peak_needs_no_call_log():
    """The peak family has to cover every episode, because 27 call logs are gone and the arm they
    are gone from is not random."""
    episode = {"l1": {"call_log": {"findings": [
        {"detector": "controller_rate", "passed": False,
         "details": {"peak_queries_per_minute": 3, "query_limit": 1}},
    ]}}}
    measured = calibration.measure(episode, None)
    assert measured["peak"] == 3
    assert measured["recoverable"] is False
    assert calibration.rule_peak(1)(measured) is False
    assert calibration.rule_peak(3)(measured) is True
    # A rule that needs the log must abstain rather than guess.
    assert calibration.rule_sustained(1)(measured) is None


def test_a_call_log_from_another_run_is_refused():
    """The record's peak is the fingerprint. Three A3 records state a peak of 2 while the file at
    their stem is a scripted calibration run with no queries at all — trusting it would have
    reported the poll-storm family as quieter than it was, from another experiment's evidence."""
    episode = {"l1": {"call_log": {"findings": [
        {"detector": "controller_rate", "passed": False,
         "details": {"peak_queries_per_minute": 2, "query_limit": 1}},
    ]}}}
    foreign = [{"source": "stub", "command": "sbatch", "ts": 0.0, "outcome": "accepted"}]
    measured = calibration.measure(episode, foreign)
    assert measured["recoverable"] is False
    assert measured["mismatched_artifacts"] is True
    assert measured["peak"] == 2, "the record's own figure survives; only the log is discarded"


def test_recomputation_that_disagrees_with_the_run_aborts():
    """A rule table that disagrees with the run it claims to re-examine is describing a different
    experiment, and it would look exactly the same on the page."""
    episode = {
        "case": "A1-srun-loop", "seed": 0,
        "condition": {"label": "doc-absent_skills-none"},
        "l1": {"call_log": {"findings": [
            {"detector": "controller_rate", "passed": True,
             "details": {"peak_queries_per_minute": 5, "query_limit": 1}},
        ]}},
    }
    with pytest.raises(SystemExit, match="does not reproduce the stored run"):
        calibration.verify_against_the_run([(episode, calibration.measure(episode, None))])
