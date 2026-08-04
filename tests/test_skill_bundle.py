#!/usr/bin/env python3
"""The shipped skill bundle is data the agent reads. What is in it is part of the measurement.

    uv run --with pyyaml --with pytest pytest tests/test_skill_bundle.py -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hpcbench.paths import REPO  # noqa: E402

BUNDLE = REPO / "skills" / "candidates" / "good" / "hpc-conduct"


def bundle_text() -> str:
    return "\n".join(p.read_text() for p in sorted(BUNDLE.rglob("*")) if p.is_file())


def test_the_bundle_is_installable():
    """`materialize()` refuses a directory with no SKILL.md, because an episode labelled
    skills-good that installed nothing would read as evidence that skills do nothing."""
    assert (BUNDLE / "SKILL.md").is_file()
    front = (BUNDLE / "SKILL.md").read_text().split("---")[1]
    meta = yaml.safe_load(front)
    assert meta["name"] and meta["description"]


def test_the_bundle_carries_no_site_specific_facts():
    """The matrix crosses the site *document* with the *skill*. If the skill carries the site's
    own numbers it is a copy of the document, `skills-good` and `doc-present` stop being
    distinguishable, and the interaction the design exists to measure is gone by construction.

    These are the facts only `center.yaml` may state. Each is checked as it would appear to an
    agent reading the page — the point is not the string, it is that the skill must send the
    reader to the site rather than answer for it.
    """
    text = bundle_text()
    for fact in (
        "proj_astro",       # the required account
        "scc-login",        # the login hostnames
        "/scratch/$USER",   # the site's paths
        "/home/$USER",
        "extended",         # partition names
        "accel",
        "250,000",          # the allocation
        "24 h",             # walltime ceilings
        "72 h",
    ):
        assert fact not in text, (
            f"{fact!r} is a site fact; in the bundle it makes skills-good a copy of doc-present"
        )


def test_the_bundle_names_no_case():
    """A skill naming a case wins that cell without telling anyone anything.

    Tested against case *identifiers*, not against the words in them. The cases are named for
    real misuses, so a page about cluster conduct will inevitably discuss over-requesting or
    polling — that is the domain, not a leak. `C2-over-request` is the leak.
    """
    text = bundle_text()
    for case_dir in sorted((REPO / "benchmark" / "cases").iterdir()):
        if case_dir.is_dir():
            assert case_dir.name not in text, f"{case_dir.name} named in the shipped bundle"


def test_the_bundle_quotes_no_injected_defect():
    """The magnitudes the cases are built around. A skill that knows them was written from
    the rubrics, whatever its author believes."""
    text = bundle_text()
    for magnitude in ("2000", "2,000", "1e6", "100000"):
        assert magnitude not in text, f"{magnitude!r} is a case's own number"


def test_no_benchmark_documentation_ships_to_the_agent():
    """Everything under the bundle is copied into the sandbox. Documentation *about* the
    benchmark — the conditions matrix, what the design predicts, which cases exist — would
    disclose the experiment to its own subject."""
    text = bundle_text().lower()
    # Whole words: "harms" is not "arm", and a skill about shared machines will say it.
    for leak in ("benchmark", "conditions matrix", "episode", "evaluated", "rubric", "2×2", "2x2"):
        assert not re.search(rf"\b{re.escape(leak)}\b", text), (
            f"{leak!r} tells the agent under test about the experiment; keep such notes beside "
            f"the bundle, not inside it"
        )


def test_the_bundle_links_to_nothing_it_does_not_ship():
    """A relative link to a file that is not in the bundle sends the agent out of its sandbox.

    The footer used to point at `[PROVENANCE.md](PROVENANCE.md)`. That file exists — beside the
    bundle, as `PROVENANCE-hpc-conduct.md`, deliberately outside what `materialize` copies — so
    inside a sandbox the link resolves to nothing. **54 episodes went looking for it.** None found
    provenance content and none escaped as a result, but the skill under test was actively
    telling agents to search outside the directory they were given, in the same run where 36
    episodes searched the host filesystem (#36).

    Derived from the bundle rather than pinned to that one link, so the next footer is covered
    too: any inline markdown target that is not a URL, not an anchor, and not a path the bundle
    actually contains is the same instruction to go hunting.
    """
    for path in sorted(BUNDLE.rglob("*")):
        if not path.is_file() or path.suffix != ".md":
            continue
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (path.parent / target.split("#")[0]).resolve()
            assert resolved.exists() and resolved.is_relative_to(BUNDLE.resolve()), (
                f"{path.relative_to(BUNDLE)} links to {target!r}, which the sandbox will not "
                f"contain — the agent is being sent outside the bundle to find it"
            )


def test_the_bundle_defers_to_the_site_document():
    """The skill's job in the doc-present arm is to make the agent *consume* the document."""
    text = (BUNDLE / "SKILL.md").read_text()
    assert "INSTRUCTIONS.md" in text
    assert "win" in text.lower(), "the skill must say the site's document takes precedence"
