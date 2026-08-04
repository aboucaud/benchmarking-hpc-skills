#!/usr/bin/env python3
"""Tests that both substrates can say which intervention they ran.

    uv run --with pyyaml --with pytest pytest src/mock_cluster/test_provenance.py -q

Needs no container: it hashes the file set `materialize_condition` builds, which is decided
before anything is started.

This substrate has recorded `evidence.input_sha256` from the beginning, and that turned out to
matter: its 90 stored records name the `agents/INSTRUCTIONS.md` they ran against, which is not
the one in the tree today (#29 rewrote it). The echo stub recorded no such thing, which is how
the matrix came to be run against a skill version `main` did not have (#34) with every record
looking identical.

The roll-up added here is derived from those same per-file hashes and exists for one reason: the
two substrates should answer "which intervention" in the same words, so pooling two runs does not
require knowing which harness wrote each record. The cross-substrate equality below is the claim
that makes that worth anything, so it is checked against the real bundle rather than asserted.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from hpcbench.harness import episode as stub_episode  # noqa: E402
from mock_cluster.episode import (  # noqa: E402
    DOCUMENT_PATH,
    SKILLS_PREFIX,
    Condition,
    _rollup,
    materialize_condition,
)

CASE = REPO / "benchmark" / "cases" / "A1-srun-loop"
SKILL = REPO / "skills" / "candidates" / "good" / "hpc-conduct"

CONTROL = Condition(doc=False, skills="none")
BOTH = Condition(doc=True, skills="good")


def docker_stamp(condition, skills_path=None):
    files = materialize_condition(CASE, condition, skills_path)
    digests = {
        name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())
    }
    return {
        "document_sha256": digests.get(DOCUMENT_PATH),
        "skills_sha256": _rollup(digests, SKILLS_PREFIX),
        "case_files_sha256": _rollup(digests, "", exclude=(DOCUMENT_PATH, SKILLS_PREFIX)),
    }


def test_the_control_arm_stamps_no_intervention():
    stamp = docker_stamp(CONTROL)
    assert stamp["document_sha256"] is None
    assert stamp["skills_sha256"] is None
    assert stamp["case_files_sha256"]  # the fixtures are always part of what was given


@pytest.mark.skipif(not SKILL.is_dir(), reason="skills under test are data, not part of this repo")
def test_both_substrates_hash_the_same_skill_bundle_the_same_way(tmp_path):
    """The claim the shared field name rests on.

    Without this the two `skills_sha256` values are two numbers that happen to share a key, and
    a reader comparing them across substrates would conclude the runs used different bundles
    whenever the layouts differed — the opposite of what the field is for.
    """
    condition = stub_episode.Condition(doc=True, skills="good")
    stub_episode.materialize(CASE, tmp_path, condition, SKILL)
    stub = stub_episode.intervention_digest(tmp_path / "work", condition)
    docker = docker_stamp(BOTH, SKILL)
    assert stub["skills_sha256"] == docker["skills_sha256"]


@pytest.mark.skipif(not SKILL.is_dir(), reason="skills under test are data, not part of this repo")
def test_both_substrates_hash_the_same_document(tmp_path):
    """Equal exactly when both are serving the one document #29 asked for. A plain content hash
    on both sides on purpose: this is the check that would have caught two documents, one label."""
    stub_episode.materialize(CASE, tmp_path, stub_episode.Condition(doc=True, skills="none"))
    stub = stub_episode.intervention_digest(
        tmp_path / "work", stub_episode.Condition(doc=True, skills="none")
    )
    assert stub["document_sha256"] == docker_stamp(BOTH, SKILL)["document_sha256"]


def test_the_case_roll_up_excludes_the_interventions(tmp_path):
    """Otherwise a doc-present episode's `case_files_sha256` differs from a control's for a reason
    that has nothing to do with the fixtures, and the field stops localising anything."""
    control = docker_stamp(CONTROL)["case_files_sha256"]
    assert control == docker_stamp(Condition(doc=True, skills="none"))["case_files_sha256"]


def test_a_roll_up_over_nothing_is_none():
    """`None`, not the hash of the empty string — which is a real-looking digest that would read
    as "a bundle was installed and it was empty"."""
    assert _rollup({}, SKILLS_PREFIX) is None
    assert _rollup({"job.sh": "abc"}, SKILLS_PREFIX) is None
