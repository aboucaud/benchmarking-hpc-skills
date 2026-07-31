#!/usr/bin/env python3
"""Tests for the ASTRA/MySTRA layer — the spec, the materialized results, the figures.

    uv run --with pyyaml --with pytest pytest tests/test_astra.py -q

The report published from this layer states measured numbers. The failure mode that matters
is therefore not a crash but a *plausible wrong number*, so these tests are weighted toward
the ways a number can look fine and be wrong. The ones worth reading first:

  - `test_unjudged_l1_failures_are_failures_not_unscored` — the trap that actually fired.
    Scoring with `judge.combine` instead of `report.endpoint_of` silently drops every
    unjudged L1 failure from the denominator and reports 100%. This test builds exactly
    that record shape and fails if the rate is not 1/2.
  - `test_grid_matches_the_reporters_own_reading` — the materialized grid and `report.py`
    must agree cell for cell, because they are two readings of one run and only one of them
    is published.
  - `test_every_declared_case_figure_has_an_artifact` — a declared output with no file
    renders as "Pending Output" in the report, which looks like an unfinished analysis
    rather than a broken build.
  - `test_findings_do_not_restate_a_measured_count` — the whole point of the MySTRA layer.
    A finding that hard-codes a count goes stale against the run it is rendered beside.
"""

from __future__ import annotations

import csv
import json
import re

import pytest
import yaml

from hpcbench import astra_figures, astra_results
from hpcbench.harness import report
from hpcbench.paths import BENCHMARK

ASTRA = BENCHMARK / "astra.yaml"
UNIVERSES = BENCHMARK / "universes"
RESULTS = BENCHMARK / "results"
UNIVERSE = "active_full_matrix"


@pytest.fixture(scope="module")
def spec():
    return yaml.safe_load(ASTRA.read_text())


@pytest.fixture(scope="module")
def grid_rows():
    path = RESULTS / UNIVERSE / "per_case_grid" / "per_case_grid.csv"
    return list(csv.DictReader(path.open()))


def episode(case, doc, skills, *, l1_prevented, l2_verdict=None, endpoint=None, **evidence):
    """A record shaped like the harness's, with only the fields the scoring path reads."""
    record = {
        "case": case,
        "family": case[0],
        "condition": {"doc": doc == "present", "skills": skills,
                      "label": f"doc-{doc}_skills-{skills}"},
        "validity": "ok",
        "seed": 0,
        "l1": {"prevented": l1_prevented},
        "evidence": {"workload_submitted": True, "submissions_rejected": 0, **evidence},
    }
    if l2_verdict is not None:
        record["l2"] = {"verdict": l2_verdict}
    if endpoint is not None:
        record["endpoint"] = endpoint
    return record


# --- the trap ------------------------------------------------------------------------------

def test_unjudged_l1_failures_are_failures_not_unscored():
    """An L1 failure with no L2 block is a failure, and must stay in the denominator.

    Judging with `--l1-pass-only` leaves every L1 failure without an `endpoint`. Reading
    those as "not scored on both layers" drops them, and the rate becomes the pass rate of
    the episodes that already passed L1 — which is close to 1.0 by construction.
    """
    records = [
        episode("A1-x", "absent", "none", l1_prevented=True,
                l2_verdict="prevented", endpoint={"prevented": True}),
        # Judged nothing: this is what `--l1-pass-only` leaves behind.
        episode("A1-x", "absent", "none", l1_prevented=False),
    ]
    rows = astra_results.rows_from(records)
    assert len(rows) == 1
    row = rows[0]
    assert row["scored"] == 2, "the unjudged L1 failure was dropped from the denominator"
    assert row["prevented"] == 1
    assert row["rate"] == 0.5, f"expected 1/2, got {row['rate']} — the 100% bug is back"


def test_endpoint_reading_is_the_reporters_own():
    """Not a second implementation. If the reporter changes, this layer follows."""
    judged = episode("C1-x", "present", "none", l1_prevented=True, endpoint={"prevented": False})
    # L1 says prevented, the endpoint says otherwise (e.g. a forbidden regression). The
    # endpoint wins, and only because we defer to the reporter rather than reading `l1`.
    assert report.endpoint_of(judged) is False
    assert astra_results.rows_from([judged])[0]["prevented"] == 0


# --- agreement with the reporter -----------------------------------------------------------

def test_grid_matches_the_reporters_own_reading(grid_rows):
    """Two readings of one run; the published one must not diverge from the reporter's."""
    source = sorted(RESULTS.parent.parent.glob("results/episodes-*.judged.jsonl"))
    if not source:
        pytest.skip("no judged records checked in")
    records = [json.loads(line) for line in source[-1].read_text().splitlines() if line.strip()]

    expected = {}
    for record in records:
        key = (record["case"], "present" if record["condition"]["doc"] else "absent",
               record["condition"]["skills"])
        expected.setdefault(key, []).append(report.endpoint_of(record))

    for row in grid_rows:
        key = (row["case"], row["doc"], row["skills"])
        verdicts = [v for v in expected[key] if v is not None]
        assert int(row["scored"]) == len(verdicts), f"{key} denominator disagrees"
        assert int(row["prevented"]) == sum(1 for v in verdicts if v), f"{key} numerator disagrees"


def test_unstable_is_disagreement_not_a_rate(grid_rows):
    """1/3 and 2/3 are both unstable; 0/3 and 3/3 are not. A rate cannot express that."""
    for row in grid_rows:
        scored, prevented = int(row["scored"]), int(row["prevented"])
        expected = bool(scored) and 0 < prevented < scored
        assert bool(int(row["unstable"])) == expected, f"{row['case']}/{row['doc']}"


def test_stratifiers_are_carried_not_folded(grid_rows):
    """`norun` and `rejected` decide whether a rate means anything, so they must survive."""
    for column in ("norun", "rejected", "needs_review", "excluded", "judged"):
        assert column in grid_rows[0], f"{column} was dropped from the published grid"
    assert any(int(row["norun"]) for row in grid_rows), (
        "no episode submitted nothing — either the run changed or the column stopped counting"
    )


# --- the spec ------------------------------------------------------------------------------

def test_spec_declares_no_cluster_facts(spec):
    """`center.yaml` is the single source of truth; restating limits here recreates drift."""
    text = yaml.safe_dump(spec)
    # Partition names and walltime ceilings are the two that would actually bite.
    for forbidden in ("standard", "extended", "accel", "scc-c", "scc-g"):
        assert not re.search(rf"\b{forbidden}\b", text), (
            f"astra.yaml names the cluster fact {forbidden!r} — it belongs in center.yaml"
        )


def test_every_declared_case_figure_has_an_artifact(spec):
    """A declared output with no file renders as 'Pending Output', not as an error."""
    declared = {
        output["id"]
        for output in spec["analyses"]["reporting"]["outputs"]
        if output.get("type") == "figure" and output["id"].startswith("case_")
    }
    assert declared, "no per-case figure outputs are declared"
    for output_id in declared:
        artifact = RESULTS / UNIVERSE / output_id / f"{output_id}.svg"
        assert artifact.exists(), f"{output_id} is declared but has no artifact"


def test_case_figures_cover_every_case_in_the_grid(spec, grid_rows):
    """A case present in the results but missing a figure is a silently unauditable case."""
    declared = {o["id"] for o in spec["analyses"]["reporting"]["outputs"]
                if o.get("type") == "figure" and o["id"].startswith("case_")}
    for case in {row["case"] for row in grid_rows}:
        assert astra_figures.output_id(case) in declared, f"{case} has no declared figure"


def test_findings_do_not_restate_a_measured_count(spec):
    """A count typed into a claim goes stale against the run rendered beside it.

    This is the failure the MySTRA layer exists to remove, so it is enforced on the claims
    themselves. Numbers may appear in `scope`, which names the run they came from.
    """
    written_out = re.compile(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        r"thirteen|fourteen|fifteen|eighteen|twenty|thirty|thirty-eight)\s+of\s+", re.I)
    for name, finding in spec["findings"].items():
        claim = finding["claim"]
        assert not written_out.search(claim), (
            f"finding {name!r} states a count in its claim; move it to a metric or to `scope`"
        )
        assert not re.search(r"\b\d+\s*/\s*\d+\b", claim), (
            f"finding {name!r} states a k/n in its claim"
        )


def test_every_finding_names_the_run_it_came_from(spec):
    """Findings from different runs render side by side; each must say which is which."""
    for name, finding in spec["findings"].items():
        if finding.get("derived"):
            assert finding.get("scope"), f"derived finding {name!r} has no scope"


def test_active_universe_is_the_one_mystra_selects():
    """MySTRA takes the first file in `universes/` when sorted, and the stem is the id.

    So the filename is load-bearing: rename it and the whole site repoints at a universe
    with no results, which renders as pending outputs rather than as an error.
    """
    files = sorted(p.name for p in UNIVERSES.glob("*.yaml"))
    assert files, "no universes"
    stem = files[0].removesuffix(".yaml")
    assert stem == UNIVERSE, f"MySTRA would select {stem!r}, but results live under {UNIVERSE!r}"
    assert (RESULTS / stem).is_dir(), f"selected universe {stem!r} has no results tree"


def test_universe_selections_name_real_options(spec):
    """A universe pinning an option that no longer exists fails late and quietly."""
    for path in UNIVERSES.glob("*.yaml"):
        universe = yaml.safe_load(path.read_text())
        for decision, option in (universe.get("decisions") or {}).items():
            assert decision in spec["decisions"], f"{path.name}: unknown decision {decision!r}"
            assert option in spec["decisions"][decision]["options"], (
                f"{path.name}: {decision}={option!r} is not an option"
            )


def test_excluded_options_carry_a_reason(spec):
    """`excluded` without `excluded_reason` is an unexplained dead end in the design record."""
    for name, decision in spec["decisions"].items():
        for option_id, option in decision["options"].items():
            if option.get("excluded"):
                assert option.get("excluded_reason"), (
                    f"{name}.{option_id} is excluded with no reason"
                )
