#!/usr/bin/env python3
"""The job-type taxonomy is data that later stages depend on, so its shape is asserted here.

    uv run --with pyyaml --with pytest pytest tests/test_taxonomy.py -q

Five types, four of them measured. `data_movement` is documented but `measured: false` — it maps to
a real facility axis and no current case exercises staging, which answers the routing design's open
question 1 without displacing one of the four that are measured.

The provenance floor of two sources per type is the part worth defending. A job type sourced from
one centre's user guide is that centre's idiosyncrasy wearing a general name, and a skill authored
from it inherits the mistake with no way to notice.
"""

from __future__ import annotations

import pytest
import yaml

from hpcbench.paths import ARCHETYPES

EXPECTED_IDS = {"serial_cpu", "gpu_train", "sweep", "mpi", "data_movement"}
MEASURED_IDS = {"serial_cpu", "gpu_train", "sweep", "mpi"}

REQUIRED = (
    "id",
    "title",
    "measured",
    "what_it_computes",
    "distinguishing_shape",
    "scale_character",
    "scheduler_features",
    "sibling_boundaries",
    "provenance",
)

# Word caps, pinned because their absence is what broke the first pass.
#
# Round 1 of the taxonomy research averaged ~900 words of prose per type and was rejected 5/5 —
# for importing failure-mode framing out of user guides, and for citations that claimed more than
# the page they cited. Both failures trace to length: an entry that tries to state every centre's
# resource envelope will reach for text written about harm, and will over-claim its sources.
# The cap is the structural fix, so it is a test rather than a note in a brief.
CAPS = {
    "title": 8,
    "what_it_computes": 60,
    "distinguishing_shape": 60,
    "scale_character": 40,
    "sibling_boundaries": 80,
}

# Where a magnitude may appear. Nowhere else: the job type carries the practice, the site document
# carries the number. `scheduler_features` is exempt because a flag like `--nodes=1` IS the feature,
# and `provenance` is exempt because a citation is evidence rather than a claim.
PROSE_FIELDS = tuple(CAPS)


def archetypes() -> list[dict]:
    return yaml.safe_load(ARCHETYPES.read_text())["archetypes"]


def test_the_file_exists_and_declares_a_list():
    assert ARCHETYPES.is_file(), f"{ARCHETYPES} is missing"
    assert isinstance(archetypes(), list)


def test_exactly_the_five_expected_types():
    ids = [entry["id"] for entry in archetypes()]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"
    assert set(ids) == EXPECTED_IDS


def test_four_are_measured_and_data_movement_is_not():
    measured = {entry["id"] for entry in archetypes() if entry["measured"]}
    assert measured == MEASURED_IDS, (
        "the routing design measures four types; data_movement is documented but not measured "
        "because no case exercises staging"
    )


@pytest.mark.parametrize("field", REQUIRED)
def test_every_type_carries_every_required_field(field):
    for entry in archetypes():
        assert entry.get(field) not in (None, "", []), f"{entry.get('id')}: {field} is empty"


def test_provenance_is_citable():
    for entry in archetypes():
        provenance = entry["provenance"]
        assert len(provenance) >= 2, (
            f"{entry['id']}: only {len(provenance)} source(s) — one centre's user guide is that "
            f"centre's idiosyncrasy, not a job type"
        )
        for citation in provenance:
            assert set(citation) == {"source", "url", "supports"}, (
                f"{entry['id']}: citation keys are {sorted(citation)}"
            )
            assert citation["url"].startswith("http"), f"{entry['id']}: {citation['url']!r}"
            assert len(citation["supports"].split()) >= 5, (
                f"{entry['id']}: {citation['url']} has a supports field too short to check against "
                f"the page it cites"
            )


@pytest.mark.parametrize("field,cap", sorted(CAPS.items()))
def test_prose_stays_under_its_cap(field, cap):
    for entry in archetypes():
        words = len(str(entry[field]).split())
        assert words <= cap, f"{entry['id']}: {field} is {words} words, cap is {cap}"


@pytest.mark.parametrize("field", PROSE_FIELDS)
def test_the_taxonomy_states_no_magnitudes(field):
    """No digit in any prose field.

    This is the interface contract made mechanical. #32's surviving thesis is that a portable
    artefact carries the *practice* and the site document carries the *magnitude* — and that a
    practice shipped without its magnitude can be worse than nothing, because the agent then picks
    the magnitude itself. The resolution is not for the taxonomy to guess a number; it is for the
    taxonomy to state none, and say where the number comes from.

    Spelled-out quantities ("one node", "a single task") are the intended form and pass.
    """
    for entry in archetypes():
        text = str(entry[field])
        digits = sorted({character for character in text if character.isdigit()})
        assert not digits, (
            f"{entry['id']}: {field} states a magnitude ({digits}) — "
            f"{text[:120]!r}. Numbers belong in the site document, not in a portable job type."
        )


def test_provenance_cites_distinct_pages():
    """Two citations of the same URL are one source wearing two hats.

    The draft this file replaced met the two-source floor for `gpu_train` by quoting a single IDRIS
    page twice. It passed a count and failed the thing the count was standing in for.
    """
    for entry in archetypes():
        urls = [citation["url"] for citation in entry["provenance"]]
        assert len(set(urls)) >= 2, (
            f"{entry['id']}: {len(urls)} citations across {len(set(urls))} distinct page(s)"
        )


def test_scheduler_features_are_a_list_of_strings():
    for entry in archetypes():
        features = entry["scheduler_features"]
        assert isinstance(features, list), f"{entry['id']}: scheduler_features is not a list"
        assert all(isinstance(item, str) and item for item in features), (
            f"{entry['id']}: scheduler_features holds a non-string or empty entry"
        )
