#!/usr/bin/env python3
"""The taxonomy must not have been written from the answer key.

    uv run --with pyyaml --with pytest pytest tests/test_taxonomy_is_not_the_answer_key.py -q

#32's first process failure was a firewall that leaked. This applies the same rule one level
earlier: if the *taxonomy* is shaped by the nine cases, then every skill authored from it is shaped
by them too, and no later firewall can undo that. The routing design puts it as a rule — *a job type
described in terms of what can go wrong with it has been written from the answer key* — and a rule
that depends on remembering is a convention, so it is mechanical here.

Three of these checks are exact and one is a heuristic, which is said out loud rather than hidden.
The exact ones cannot be argued with. The vocabulary check is a smoke alarm, and #10's human review
is the only real check.
"""

from __future__ import annotations

import json
import re

import yaml

from hpcbench.paths import ARCHETYPES, CASES, CENTER, GENERATED

# Site facts that could only be true of the fixture centre: paths, hostnames, module versions,
# walltimes, hardware strings, the account, the facility name, its support address and docs URL.
# Recognised by shape — anything holding a digit or one of these separators is an identifier rather
# than an English word.
_IDENTIFIER = re.compile(r"[0-9/$@:\-]")

# Bare alphabetic scalars from center.yaml are partition names and policy values. Partition names
# must not appear: "the standard partition" is this fixture, not a job type. Two are allowed:
#
#   slurm      the scheduler itself, which the taxonomy is entitled to name
#   forbidden  a policy *value* in the conduct map, not a fact about this centre
#
# Widening this set is a review decision. If a taxonomy sentence trips on `standard` or `debug`,
# reword the sentence — those are partition names here, and a skill that leans on them is not
# portable.
ALLOWED_BARE_WORDS = {"slurm", "forbidden"}

# Words that describe misuse rather than work. Heuristic — see the module docstring.
FAILURE_VOCABULARY = (
    "misuse",
    "mistake",
    "wrong",
    "incorrect",
    "avoid",
    "should not",
    "must not",
    "excessive",
    "flood",
    "hammer",
    "storm",
    "abuse",
    "violat",
    "defect",
    "bad practice",
    "anti-pattern",
    "pitfall",
    "harm",
)


# The fields in which the taxonomy makes its claims, as opposed to the fields in which it cites
# evidence. `scheduler_features` names real Slurm flags at real centres and `provenance.supports`
# quotes real pages — a check that bans ordinary facility vocabulary has to leave those alone or it
# bans the evidence along with the claim.
PROSE_FIELDS = (
    "title",
    "what_it_computes",
    "distinguishing_shape",
    "scale_character",
    "sibling_boundaries",
)


def taxonomy_text() -> str:
    """Every human-readable string in the file, lowercased.

    `url` values are excluded: a citation URL may legitimately contain any word, and it is evidence
    for a claim rather than part of the claim.
    """
    chunks: list[str] = []

    def walk(node, key: str = "") -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                walk(value, name)
        elif isinstance(node, list):
            for value in node:
                walk(value, key)
        elif isinstance(node, str) and key != "url":
            chunks.append(node)

    walk(yaml.safe_load(ARCHETYPES.read_text()))
    return "\n".join(chunks).lower()


def prose_text() -> str:
    """Only the fields where the taxonomy describes a job type in its own voice."""
    document = yaml.safe_load(ARCHETYPES.read_text())
    return "\n".join(
        str(entry.get(field, "")) for entry in document["archetypes"] for field in PROSE_FIELDS
    ).lower()


def center_scalars() -> set[str]:
    banned: set[str] = set()

    def collect(node) -> None:
        if isinstance(node, dict):
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)
        elif isinstance(node, str) and len(node) >= 4:
            banned.add(node.strip())

    collect(yaml.safe_load(CENTER.read_text()))
    return banned


def detector_parameter_names() -> set[str]:
    """The scored parameters in the generated detector configuration.

    These are what the L1 detectors audit — `max_calls_per_minute`, `login_node_compute`,
    `small_file_threshold_mb`. A taxonomy that names one has been written against the scoring,
    which is the answer key by another route.

    Only keys holding an underscore count. The rest are containers (`controller`, `filesystem`,
    `conduct`, `partitions`) or single common words (`gpus`, `account`) that are ordinary HPC
    vocabulary — banning `filesystem` from a document about where job data lives would be a guard
    that has stopped tracking what it was written to catch.
    """
    names: set[str] = set()

    def collect(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if "_" in str(key):
                    names.add(str(key).lower())
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(json.loads((GENERATED / "detectors.json").read_text()))
    return names - {"schema_version", "generated_from"}


def test_no_case_id_appears():
    case_ids = sorted(path.name for path in CASES.iterdir() if path.is_dir())
    assert case_ids, "no cases found — this test would pass vacuously"
    text = taxonomy_text()
    leaked = [case_id for case_id in case_ids if case_id.lower() in text]
    assert not leaked, f"the taxonomy names benchmark cases: {leaked}"


def test_no_site_identifier_from_center_yaml_appears():
    """Paths, hostnames, module versions, walltimes, hardware, account, facility name."""
    text = taxonomy_text()
    identifiers = {
        scalar for scalar in center_scalars()
        if _IDENTIFIER.search(scalar) and len(scalar.split()) <= 6
    }
    assert identifiers, "no identifiers extracted from center.yaml — the test would pass vacuously"
    leaked = sorted(scalar for scalar in identifiers if scalar.lower() in text)
    assert not leaked, (
        f"the taxonomy states this centre's own values: {leaked}. The skill carries the practice; "
        f"the site document carries the magnitude."
    )


def test_no_partition_name_appears():
    """Prose only.

    `scheduler_features` and `provenance` are exempt because they name real flags at real centres:
    LUMI's accelerator partition is literally called `standard-g`, and a check that bans the bare
    word `standard` everywhere would reject a verbatim citation. The rule being enforced is that
    the taxonomy must not *describe* a job type using this fixture's vocabulary.
    """
    text = prose_text()
    bare = {
        scalar.lower() for scalar in center_scalars()
        if scalar.isalpha() and scalar.lower() not in ALLOWED_BARE_WORDS
    }
    leaked = sorted(word for word in bare if re.search(rf"\b{re.escape(word)}\b", text))
    assert not leaked, (
        f"the taxonomy uses words that are partition or policy names in center.yaml: {leaked}. "
        f"Reword rather than widening ALLOWED_BARE_WORDS — a taxonomy that leans on this fixture's "
        f"partition names is not portable."
    )


def test_no_detector_parameter_name_appears():
    text = taxonomy_text()
    names = detector_parameter_names()
    assert names, "no detector names extracted — the test would pass vacuously"
    leaked = sorted(name for name in names if re.search(rf"\b{re.escape(name)}\b", text))
    assert not leaked, f"the taxonomy names scored parameters: {leaked}"


def test_no_failure_vocabulary():
    """Heuristic, and deliberately so — see the module docstring.

    A job type is defined by what it computes. The moment it is defined by what goes wrong with it,
    it has been written from the answer key, and every skill authored from it inherits that.
    """
    text = taxonomy_text()
    found = sorted(word for word in FAILURE_VOCABULARY if word in text)
    assert not found, (
        f"the taxonomy describes what goes wrong rather than what the job computes: {found}. If "
        f"one of these is genuinely load-bearing, argue it in review and add it to an allowlist "
        f"with a reason — do not silently widen FAILURE_VOCABULARY."
    )
