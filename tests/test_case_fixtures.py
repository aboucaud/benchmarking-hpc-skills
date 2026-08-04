#!/usr/bin/env python3
"""Tests that the files handed to the agent do not describe the experiment.

    uv run --with pyyaml --with pytest pytest tests/test_case_fixtures.py -q

`episode.py` withholds `case.yaml`, `reference.sh` and `rubric.md` because an agent that reads
the rubric is measuring nothing, and it asserts that at materialization time rather than trusting
it. That covers the files. It did not cover their *contents* leaking into the files that are
handed over — and they had:

  - three cases shipped a comment reading "The defect in case A2 lives in the driver, not here",
    which is the answer key's first half — read in **12 of 12** episodes of each of A2, A3 and B3;
  - `C3-wrong-partition/assets/train_photoz.py` said "the defect is the partition, not the
    request", while C3's own `case.yaml` claims the correct target "cannot be learned from the
    script". Read in **5 of 6** doc-present episodes and **0 of 6** doc-absent ones — an
    imbalance aligned with the intervention, in the case carrying the sharpest published result;
  - six fixtures opened "Nothing in this benchmark executes", telling the agent it is under
    measurement. That one is balanced across arms (15/16/18/17 of 108), so it costs external
    validity rather than internal.

So the vocabulary below is not a style rule. Each entry is a phrase that was in a file an agent
read, and the list is keyed off `case.yaml` so a case added later is covered without anyone
remembering this file exists.

What is deliberately *not* forbidden: the physical facts of the workload. C3's trainer must still
show that it needs GPUs, or `gpus-dropped-to-fit-partition` becomes unfalsifiable. The line is
between what the program is and what the experiment thinks about it.
"""

from __future__ import annotations

import pytest
import yaml

from hpcbench.harness.episode import VISIBLE, WITHHELD
from hpcbench.paths import BENCHMARK, REPO

CASES = sorted(path for path in (BENCHMARK / "cases").iterdir() if (path / "case.yaml").exists())

# The other substrate's copy of the same files.
#
# `mock_cluster.materialize_condition` copies `assets/` and then calls `files.update(
# agent_fixture_files(case))`, so where a file exists in both trees the Docker one wins outright.
# Seven cases are overridden, covering every file the stub's fixture pass rewrote — which means
# the checks below ran against files no Docker agent ever saw. These were written separately and
# were already clean, so the leak was stub-only and the Docker results are not implicated; the
# gap was that nothing said so.
DOCKER_FIXTURES = REPO / "src" / "mock_cluster" / "fixtures"
DOCKER_CASES = sorted(
    path for path in DOCKER_FIXTURES.iterdir()
    if path.is_dir() and path.name != "qualification"
)

# Phrases that only make sense if the writer knew this was an experiment. Lowercased before match.
#
# "stub" and "placeholder" are absent on purpose: real pipelines contain both, and a fixture that
# claims to do work it does not do is a different lie. What an agent must not be told is that the
# thing measuring it exists.
EXPERIMENT_WORDS = (
    "benchmark",
    "rubric",
    "case.yaml",
    "reference.sh",
    "injected",
    "accepted_remedies",
    "forbidden_regressions",
    "clean by construction",
)

# Phrases that state the finding rather than the facts. These are the ones that were actually read.
ANSWER_WORDS = (
    "the defect",
    "no defect",
    "the remedy",
    "the fix is",
    "this case",
    "the case turns on",
    "is the case",
)


def visible_files(case_dir):
    """Exactly what `materialize` copies into the sandbox, derived the same way it derives it."""
    files = [case_dir / name for name in VISIBLE]
    if (case_dir / "assets").is_dir():
        files += sorted(path for path in (case_dir / "assets").iterdir() if path.is_file())
    return [path for path in files if path.exists()]


def readable(path):
    try:
        return path.read_text()
    except (UnicodeDecodeError, OSError):
        return ""


@pytest.mark.parametrize("case_dir", CASES, ids=lambda path: path.name)
def test_no_visible_file_says_it_is_a_benchmark(case_dir):
    """The agent may know the program is a placeholder. It may not know it is being measured."""
    for path in visible_files(case_dir):
        text = readable(path).lower()
        found = [word for word in EXPERIMENT_WORDS if word in text]
        assert not found, (
            f"{path.relative_to(BENCHMARK)} tells the agent about the experiment: {found}"
        )


@pytest.mark.parametrize("case_dir", CASES, ids=lambda path: path.name)
def test_no_visible_file_names_the_defect(case_dir):
    """Naming where the defect is — or is not — hands over the search, which is the task."""
    for path in visible_files(case_dir):
        text = readable(path).lower()
        found = [word for word in ANSWER_WORDS if word in text]
        assert not found, f"{path.relative_to(BENCHMARK)} discusses the defect: {found}"


@pytest.mark.parametrize("case_dir", CASES, ids=lambda path: path.name)
def test_no_visible_file_names_the_case(case_dir):
    """A file that names its own case identifier is quoting the answer key it was written beside."""
    identifier = case_dir.name
    short = identifier.split("-")[0].lower()  # A2, C3 — how the leaked comments actually wrote it
    for path in visible_files(case_dir):
        text = readable(path)
        assert identifier not in text, f"{path.relative_to(BENCHMARK)} names its case: {identifier}"
        assert f"case {short}" not in text.lower(), (
            f"{path.relative_to(BENCHMARK)} names its case: case {short}"
        )


@pytest.mark.parametrize("case_dir", CASES, ids=lambda path: path.name)
def test_no_visible_file_quotes_a_remedy_identifier(case_dir):
    """The accepted-remedy ids are the answer key's index. None of them belongs in a fixture."""
    case = yaml.safe_load((case_dir / "case.yaml").read_text())
    identifiers = [
        entry["id"]
        for key in ("accepted_remedies", "forbidden_regressions")
        for entry in (case.get(key) or [])
        if isinstance(entry, dict) and entry.get("id")
    ]
    for path in visible_files(case_dir):
        text = readable(path).lower()
        found = [identifier for identifier in identifiers if identifier.lower() in text]
        assert not found, f"{path.relative_to(BENCHMARK)} quotes the answer key: {found}"


@pytest.mark.parametrize("case_dir", DOCKER_CASES, ids=lambda path: path.name)
def test_the_docker_substrates_own_fixtures_are_held_to_the_same_rule(case_dir):
    """Same rule, other substrate. These files replace the ones above, so they are what is read.

    Split from the tests above rather than folded into `visible_files` because the two trees are
    not the same set: Docker overrides seven cases and inherits the rest, and a helper that
    silently merged them would stop being able to say which file an agent actually got.
    """
    for path in sorted(case_dir.rglob("*")):
        if not path.is_file():
            continue
        text = readable(path).lower()
        found = [word for word in EXPERIMENT_WORDS + ANSWER_WORDS if word in text]
        assert not found, f"{path.relative_to(DOCKER_FIXTURES)} describes the experiment: {found}"
        assert case_dir.name not in readable(path), (
            f"{path.relative_to(DOCKER_FIXTURES)} names its case"
        )


def test_the_docker_override_covers_what_the_stub_rewrote():
    """If Docker ever stops shadowing a rewritten file, the stub's version becomes live there.

    Without this the two trees drift apart silently: the override is positional (`dict.update`
    after the assets are copied), so a file removed from `mock_cluster/fixtures/` does not fail
    anything — it just quietly starts serving `benchmark/cases/<case>/assets/` to Docker agents
    instead, and only the case-file digest would ever show it.
    """
    for case_dir in DOCKER_CASES:
        assets = BENCHMARK / "cases" / case_dir.name / "assets"
        shadowed = {path.name for path in case_dir.rglob("*") if path.is_file()}
        assert shadowed, f"{case_dir.name} has an empty override directory"
        if assets.is_dir():
            inherited = {path.name for path in assets.iterdir() if path.is_file()} - shadowed
            assert not inherited, (
                f"{case_dir.name}: Docker overrides some assets but inherits {sorted(inherited)} "
                f"— those reach a Docker agent from benchmark/cases/, not from this tree"
            )


def test_the_visible_set_is_the_one_the_harness_copies():
    """If `materialize` starts copying something else, these tests must start reading it.

    Without this the suite goes quietly out of date the day a case gains a file: every test above
    would still pass, over a set that is no longer what the agent gets.
    """
    assert VISIBLE == ("job.sh", "prompt.md")
    assert WITHHELD == ("case.yaml", "reference.sh", "rubric.md")
    for case_dir in CASES:
        copied = {path.name for path in visible_files(case_dir)}
        withheld = {name for name in WITHHELD if (case_dir / name).exists()}
        assert not (copied & withheld)
