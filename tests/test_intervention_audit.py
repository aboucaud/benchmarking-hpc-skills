#!/usr/bin/env python3
"""Tests that the intervention stamp is read, and read the way it has to be read.

    uv run --with pyyaml --with pytest pytest tests/test_intervention_audit.py -q

The stamp was written first and consumed by nothing, which is the state where provenance looks
solved and isn't: `episode["intervention"]` existed on both substrates while a results file
pooling two experiments still produced one rate in silence. These tests are about the reader.

Two invariants carry most of the weight, and both are ways to get the wrong answer while
looking right:

  - **A missing stamp is unknown, never agreement.** Records predating the field have no
    `intervention` at all. The natural implementation collects the field, gets `None` from every
    old record, finds one distinct value, and reports a homogeneous set — a clean bill of health
    for exactly the records that cannot support one.
  - **`None` from a stamped record is not the same thing.** A doc-absent episode *did* stamp,
    and its answer is "no document". Counting that as a distinct document would fire on every
    healthy 2x2 matrix, and a check that fails on every good run is a check people learn to skip.
"""

from __future__ import annotations

import json

import pytest

from hpcbench import astra_results
from hpcbench.harness import provenance
from hpcbench.harness.report import report

DOCUMENT = "a" * 64
OTHER_DOCUMENT = "b" * 64
BUNDLE = "c" * 64


def episode(case="A1-srun-loop", doc=True, skills="none", *, stamp=..., substrate=None, seed=0):
    """A record carrying only what the audit reads."""
    record = {
        "case": case,
        "family": case[0],
        "seed": seed,
        "condition": {"doc": doc, "skills": skills,
                      "label": f"doc-{'present' if doc else 'absent'}_skills-{skills}"},
    }
    if substrate:
        record["substrate"] = substrate
    if stamp is not ...:
        record["intervention"] = stamp
    return record


def manifest_from(tmp_path):
    directory = tmp_path / "out" / "u" / "intervention_manifest"
    return json.loads((directory / "intervention_manifest.json").read_text())


def stamp(document=DOCUMENT, skills=None, case_files="d" * 64):
    return {
        "document_sha256": document,
        "skills_sha256": skills,
        "skills_manifests": [],
        "case_files_sha256": case_files,
    }


# --- the set agrees with itself --------------------------------------------------------------


def test_one_experiment_is_not_a_problem():
    result = provenance.audit([episode(seed=n, stamp=stamp()) for n in range(3)])
    assert result.ok
    assert result.stamped == 3
    assert result.values["document_sha256"] == {DOCUMENT}


def test_two_documents_under_one_label_is_a_problem():
    """The #29 shape: same `doc-present` label, two documents, and nothing else showing it."""
    records = [
        episode(seed=0, stamp=stamp(document=DOCUMENT)),
        episode(seed=1, stamp=stamp(document=OTHER_DOCUMENT)),
    ]
    result = provenance.audit(records)
    assert not result.ok
    assert "document_sha256" in result.problems[0]
    # The digests are named, not just counted — "two documents" is not actionable on its own.
    assert DOCUMENT[:12] in result.problems[0] and OTHER_DOCUMENT[:12] in result.problems[0]


def test_two_skill_bundles_under_one_label_is_a_problem():
    """#34's shape, seen from the reader: one label, two bundles, both looking correct."""
    result = provenance.audit([
        episode(skills="good", seed=0, stamp=stamp(skills=BUNDLE)),
        episode(skills="good", seed=1, stamp=stamp(skills=OTHER_DOCUMENT)),
    ])
    assert not result.ok
    assert any("skills_sha256" in problem for problem in result.problems)


def test_the_control_arm_is_not_a_second_document():
    """`None` from a stamped doc-absent episode is an answer, not a disagreement.

    Every healthy 2x2 matrix mixes stamped nulls with stamped digests. If that read as two
    documents the guard would fire on every correct run.
    """
    result = provenance.audit([
        episode(doc=True, stamp=stamp(document=DOCUMENT)),
        episode(doc=False, stamp=stamp(document=None)),
    ])
    assert result.ok
    assert result.values["document_sha256"] == {DOCUMENT}


# --- a missing stamp is unknown ---------------------------------------------------------------


def test_unstamped_records_are_counted_not_forgiven():
    """The invariant the whole module turns on."""
    result = provenance.audit([episode(seed=0), episode(seed=1)])
    assert result.stamped == 0
    assert len(result.unstamped) == 2
    assert "carry no stamp" in " ".join(result.summary())
    # Not a *problem* — nothing is known to conflict. But nothing is known to agree either, and
    # the summary must not let a reader take silence for a pass.
    assert "no record in this set carried one" in " ".join(result.summary())


def test_an_unstamped_record_does_not_vouch_for_a_stamped_one():
    result = provenance.audit([episode(seed=0, stamp=stamp()), episode(seed=1)])
    assert result.stamped == 1 and len(result.unstamped) == 1
    assert "1 of 2 records carry no stamp" in " ".join(result.summary())


@pytest.mark.parametrize("empty", [None, {}])
def test_an_empty_stamp_reads_as_no_stamp(empty):
    """`{}` is what a partially-written record looks like, and knows exactly as much as `None`."""
    assert provenance.stamp_of(episode(stamp=empty)) is None


# --- substrate boundaries ---------------------------------------------------------------------


def test_case_files_are_compared_within_a_substrate():
    """Measured, not assumed: the same unchanged case stamps two values on the two substrates.

    The stub appends the site-guidance pointer to `prompt.md` and Docker delivers its pointer in
    the prompt it sends, so `case_files_sha256` differs by construction. Comparing across
    substrates would report every case as having two fixture versions, forever.
    """
    result = provenance.audit([
        episode(substrate="echo-stub", stamp=stamp(case_files="e" * 64)),
        episode(substrate="docker-slurm", stamp=stamp(case_files="f" * 64)),
    ])
    assert result.ok


def test_two_fixture_versions_on_one_substrate_is_a_problem():
    result = provenance.audit([
        episode(substrate="echo-stub", seed=0, stamp=stamp(case_files="e" * 64)),
        episode(substrate="echo-stub", seed=1, stamp=stamp(case_files="f" * 64)),
    ])
    assert not result.ok
    assert "A1-srun-loop on echo-stub" in result.problems[0]


def test_drift_compares_a_record_against_its_own_substrate():
    """Cross-substrate comparison here is the same error as above, in the other direction."""
    trees = {
        "echo-stub": {"A1-srun-loop": stamp(case_files="e" * 64)},
        "docker-slurm": {"A1-srun-loop": stamp(case_files="f" * 64)},
    }
    matching = [
        episode(substrate="echo-stub", stamp=stamp(case_files="e" * 64)),
        episode(substrate="docker-slurm", stamp=stamp(case_files="f" * 64)),
    ]
    assert provenance.drift(matching, trees) == []

    moved = [episode(substrate="docker-slurm", stamp=stamp(case_files="e" * 64))]
    assert len(provenance.drift(moved, trees)) == 1
    assert "docker-slurm" in provenance.drift(moved, trees)[0]


def test_drift_says_nothing_about_records_that_cannot_answer():
    trees = {"echo-stub": {"A1-srun-loop": stamp()}}
    assert provenance.drift([episode()], trees) == []


# --- the consumers ------------------------------------------------------------------------------


def test_the_pooling_point_refuses_a_mixed_file(tmp_path, monkeypatch, capsys):
    """The check that would have caught #29 before it became a published rate."""
    records = [
        episode(seed=0, stamp=stamp(document=DOCUMENT)),
        episode(seed=1, stamp=stamp(document=OTHER_DOCUMENT)),
    ]
    for record in records:
        record["l1"] = {"prevented": True}
        record["validity"] = "ok"
        record["endpoint"] = {"prevented": True}
    path = tmp_path / "episodes.judged.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records))

    monkeypatch.setattr(astra_results, "RESULTS", tmp_path / "out")
    monkeypatch.setattr(astra_results, "BENCHMARK", tmp_path / "benchmark")
    monkeypatch.setattr("sys.argv", ["astra_results.py", str(path), "--universe", "u"])
    assert astra_results.main() == 1
    assert "mixed intervention" in capsys.readouterr().err
    # Nothing published. A refusal that still writes the artifact is not a refusal.
    assert not (tmp_path / "out").exists()


def test_the_pooling_point_can_be_overridden_on_purpose(tmp_path, monkeypatch):
    records = [
        episode(seed=0, stamp=stamp(document=DOCUMENT)),
        episode(seed=1, stamp=stamp(document=OTHER_DOCUMENT)),
    ]
    for record in records:
        record["l1"] = {"prevented": True}
        record["validity"] = "ok"
        record["endpoint"] = {"prevented": True}
    path = tmp_path / "episodes.judged.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records))

    monkeypatch.setattr(astra_results, "RESULTS", tmp_path / "out")
    monkeypatch.setattr(astra_results, "BENCHMARK", tmp_path / "benchmark")
    monkeypatch.setattr("sys.argv", ["astra_results.py", str(path), "--universe", "u",
                                     "--allow-mixed-intervention"])
    assert astra_results.main() == 0
    manifest = manifest_from(tmp_path)
    # Published, and saying so. An override that hid what it overrode is worse than no check.
    assert manifest["mixed"]
    assert sorted(manifest["document_sha256"]) == sorted([DOCUMENT, OTHER_DOCUMENT])


def test_the_manifest_separates_stamped_from_unstamped(tmp_path, monkeypatch):
    records = [episode(seed=0, stamp=stamp()), episode(seed=1)]
    for record in records:
        record["l1"] = {"prevented": True}
        record["validity"] = "ok"
    path = tmp_path / "episodes.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records))

    monkeypatch.setattr(astra_results, "RESULTS", tmp_path / "out")
    monkeypatch.setattr(astra_results, "BENCHMARK", tmp_path / "benchmark")
    monkeypatch.setattr("sys.argv", ["astra_results.py", str(path), "--universe", "u"])
    assert astra_results.main() == 0
    assert manifest_from(tmp_path) == {"episodes": 2, "stamped": 1, "unstamped": 1,
                                       **manifest_from(tmp_path)}


def test_the_report_says_which_intervention_ran():
    records = [episode(seed=0, stamp=stamp()), episode(seed=1, stamp=stamp())]
    for record in records:
        record["l1"] = {"prevented": True}
        record["validity"] = "ok"
        record["evidence"] = {"workload_submitted": True, "submissions_rejected": 0}
    text = report(records)
    assert "## Which intervention ran" in text
    assert DOCUMENT[:12] in text


def test_the_report_names_a_mixed_run_as_mixed():
    records = [
        episode(seed=0, stamp=stamp(document=DOCUMENT)),
        episode(seed=1, stamp=stamp(document=OTHER_DOCUMENT)),
    ]
    for record in records:
        record["l1"] = {"prevented": True}
        record["validity"] = "ok"
        record["evidence"] = {"workload_submitted": True, "submissions_rejected": 0}
    text = report(records)
    assert "pool more than one experiment" in text
