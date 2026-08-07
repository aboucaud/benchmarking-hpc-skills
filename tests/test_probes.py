#!/usr/bin/env python3
"""Routing probes are task sentences, and the holdout half stays sealed.

    uv run --with pyyaml --with pytest pytest tests/test_probes.py -q

A probe exists to ask one question — *given this task, which skill should load?* — so a probe that
carries a script, an asset or a defect has quietly become a benchmark case, and would drag the
review gate and the answer key along with it. Dropping simulation from Phase A is what makes a flat
file of sentences sufficient (#48); these tests are what keep it flat.

The last two tests are about a mistake this repo has already made. Last session an output directory
was created at `benchmark/cases/review/` and `validate_cases.py` immediately read it as a case,
reporting `missing ['case.yaml', 'job.sh', ...]`. Two new files under `benchmark/` earn the same
check before they are trusted.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
import yaml

from hpcbench.paths import ARCHETYPES, BENCHMARK, CASES, PROBES, REPO

# Keys that would make a probe into a case. Checked by name, so that adding one is a deliberate act
# rather than something that happens while a file grows.
CASE_KEYS = (
    "job",
    "job_sh",
    "script",
    "assets",
    "defect",
    "injected_defect",
    "review_status",
    "reference",
    "rubric",
    "detection",
    "accepted_remedies",
    "forbidden_regressions",
)


def probes() -> dict:
    return yaml.safe_load(PROBES.read_text())


def every_probe() -> list[dict]:
    document = probes()
    return [*document["visible"], *document["holdout"]]


def archetype_ids() -> set[str]:
    return {entry["id"] for entry in yaml.safe_load(ARCHETYPES.read_text())["archetypes"]}


def measured_ids() -> set[str]:
    return {
        entry["id"]
        for entry in yaml.safe_load(ARCHETYPES.read_text())["archetypes"]
        if entry["measured"]
    }


def test_both_halves_exist_and_are_non_empty():
    document = probes()
    assert document["visible"], "no visible probes"
    assert document["holdout"], "no holdout probes — F4 would have nothing to report"


def test_probe_ids_are_unique_across_both_halves():
    ids = [probe["id"] for probe in every_probe()]
    assert len(ids) == len(set(ids)), f"duplicate probe ids: {ids}"


def test_the_halves_are_disjoint():
    document = probes()
    visible = {probe["text"].strip().lower() for probe in document["visible"]}
    holdout = {probe["text"].strip().lower() for probe in document["holdout"]}
    overlap = visible & holdout
    assert not overlap, f"probe text appears in both halves: {sorted(overlap)}"


def test_every_measured_job_type_has_probes_on_both_sides():
    document = probes()
    for job_type in sorted(measured_ids()):
        visible = [probe for probe in document["visible"] if probe["job_type"] == job_type]
        holdout = [probe for probe in document["holdout"] if probe["job_type"] == job_type]
        assert len(visible) >= 2, f"{job_type}: {len(visible)} visible probe(s), need at least 2"
        assert len(holdout) >= 1, f"{job_type}: no holdout probe"


def test_every_probe_names_a_real_job_type():
    known = archetype_ids()
    for probe in every_probe():
        assert probe["job_type"] in known, (
            f"{probe['id']}: unknown job_type {probe['job_type']!r}"
        )


@pytest.mark.parametrize("key", CASE_KEYS)
def test_no_probe_carries_anything_that_would_make_it_a_case(key):
    for probe in every_probe():
        assert key not in probe, (
            f"{probe['id']} carries {key!r} — a probe is a sentence, not a case. See #48."
        )


def test_probe_text_contains_nothing_executable():
    for probe in every_probe():
        text = probe["text"]
        assert "#SBATCH" not in text, f"{probe['id']} contains an SBATCH directive"
        assert not text.lstrip().startswith("#!"), f"{probe['id']} starts with a shebang"
        assert set(probe) == {"id", "job_type", "text"}, (
            f"{probe['id']}: keys are {sorted(probe)}, expected id/job_type/text"
        )


def test_the_new_files_are_beside_the_cases_not_inside_them():
    for path in (PROBES, ARCHETYPES):
        assert path.parent == BENCHMARK, f"{path} is not directly under benchmark/"
        assert CASES not in path.parents, f"{path} is inside benchmark/cases/"


def test_case_enumeration_cannot_reach_the_new_files():
    """Both harnesses enumerate cases as `benchmark/cases/*/` directories.

    A file directly under `benchmark/` is unreachable by that walk. Asserted rather than assumed,
    because that walk is exactly what mistook `benchmark/cases/review/` for a case.
    """
    enumerated = {path.name for path in CASES.iterdir() if path.is_dir()}
    assert enumerated, "no case directories found — this test would pass vacuously"
    assert "routing-probes.yaml" not in enumerated
    assert "archetypes.yaml" not in enumerated


def test_validate_cases_still_passes_with_the_new_files_present():
    result = subprocess.run(
        [sys.executable, str(REPO / "src" / "hpcbench" / "validate_cases.py")],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        f"validate_cases.py now fails:\n{result.stdout}\n{result.stderr}"
    )
