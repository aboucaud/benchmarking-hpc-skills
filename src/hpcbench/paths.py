"""Where the data lives, stated once.

Before the layout split, code and data shared a tree and every module worked out where the
descriptor was by walking up from its own file — `BENCHMARK = Path(__file__).parent`, or
`.parent.parent` one directory deeper. That silently encodes the directory depth of each
module into its path arithmetic, so moving a file moved the data with it.

Now the code is a package under `src/` and the data is `benchmark/`, so the two cannot be
confused, and the walk happens exactly here.

`benchmark/` is located relative to the repository root because it is *input to a run*, not
package data: the cases, the descriptor and the generated documents are things a reviewer
edits and a run reads. Installing `hpcbench` into a virtualenv and running it against a
different checkout is not a thing this benchmark does, and pretending otherwise would mean
shipping nine misuse cases inside a wheel.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent          # src/hpcbench
REPO = PACKAGE.parent.parent                       # repository root
BENCHMARK = REPO / "benchmark"                     # the data half of the split
CENTER = BENCHMARK / "center.yaml"                 # the single source of truth
CASES = BENCHMARK / "cases"
GENERATED = BENCHMARK / "generated"
# Stage 0 of the skill forge (#48). Both sit directly under `benchmark/`, never inside `cases/` —
# they are inputs to authoring, not things an episode runs, and a directory under `cases/` is read
# as a case by `validate_cases.py` and by both harnesses' `all`.
ARCHETYPES = BENCHMARK / "archetypes.yaml"
PROBES = BENCHMARK / "routing-probes.yaml"
# Where a facility publishes its document. Generated from CENTER, same bytes as
# GENERATED/INSTRUCTIONS.md — the Docker substrate reads it from here (#29).
AGENTS = REPO / "agents"
