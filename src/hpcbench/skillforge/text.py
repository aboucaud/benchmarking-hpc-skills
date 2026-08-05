#!/usr/bin/env python3
"""Token-level text comparison, shared by the probe distance guard and by description ranking.

Deliberately dependency-free and deterministic. Ranking a probe against four skill descriptions is a
decision the forge makes about its own output, and a decision that costs nothing and returns the
same answer twice is worth more here than a better metric that needs a model call — the whole
argument for measuring routing offline is that it is free and repeatable.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    """Lowercased alphanumeric words.

    No stemming and no stopword list. Both would need tuning against the very probes they are used
    to judge, and an untuned heuristic that is easy to reason about beats a tuned one that is not.
    """
    return set(_WORD.findall(text.lower()))


def containment(probe: str, document: str) -> float:
    """What fraction of `probe`'s vocabulary already appears in `document`.

    Asymmetric on purpose. A probe is one sentence and a case's `prompt.md` is a paragraph, so their
    symmetric overlap (Jaccard) stays low even when the probe was copied out of the prompt word for
    word — the denominator is dominated by everything else the prompt says. Containment asks the
    question that actually matters, *how much of this probe is already in that text*, and answers
    ~1.0 for a lifted sentence however long the source is.
    """
    needle = tokens(probe)
    if not needle:
        return 0.0
    return len(needle & tokens(document)) / len(needle)
