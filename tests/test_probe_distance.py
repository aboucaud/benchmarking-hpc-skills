#!/usr/bin/env python3
"""No probe may be lifted from a case.

    uv run --with pyyaml --with pytest pytest tests/test_probe_distance.py -q

If the probes were written with the nine cases in view they are near-copies, and calling the holdout
half "held out" would be theatre — the one Phase A number the loop could not have optimised against
(#48, F4) would be measuring the benchmark instead.

This bounds the accidental version of that. It does **not** make the probes realistic: nobody with
sysadmin experience has signed them off (#10), and #48 says so in its risks. A guard against
copying is not a guarantee of representativeness.
"""

from __future__ import annotations

import yaml

from hpcbench.paths import CASES, PROBES
from hpcbench.skillforge.text import containment, tokens

# A probe sharing 70% of its vocabulary with a case prompt was written next to that prompt, whatever
# the author intended. Pinned rather than tuned: raising a threshold after seeing it fail is how a
# guard becomes decoration.
MAX_CONTAINMENT = 0.7


def every_probe() -> list[dict]:
    document = yaml.safe_load(PROBES.read_text())
    return [*document["visible"], *document["holdout"]]


def case_prompts() -> dict[str, str]:
    return {path.parent.name: path.read_text() for path in sorted(CASES.glob("*/prompt.md"))}


def test_tokens_ignores_case_and_punctuation():
    assert tokens("Run 500 jobs, please!") == {"run", "500", "jobs", "please"}


def test_containment_is_one_for_a_lifted_sentence():
    document = "please run the preprocessing step and then submit the array job"
    assert containment("run the preprocessing step", document) == 1.0


def test_containment_is_zero_for_unrelated_text():
    assert containment("alpha beta gamma", "delta epsilon zeta") == 0.0


def test_containment_is_zero_for_empty_input():
    assert containment("", "anything at all") == 0.0


def test_no_probe_is_lifted_from_a_case_prompt():
    prompts = case_prompts()
    assert prompts, "no case prompts found — this test would pass vacuously"
    offenders = []
    for probe in every_probe():
        for case_id, prompt in prompts.items():
            score = containment(probe["text"], prompt)
            if score > MAX_CONTAINMENT:
                offenders.append(f"{probe['id']} vs {case_id}: {score:.2f}")
    assert not offenders, (
        "probes overlap case prompts, so the holdout is not independent of the benchmark:\n  "
        + "\n  ".join(offenders)
        + "\nRewrite the probe. Do not raise MAX_CONTAINMENT."
    )
