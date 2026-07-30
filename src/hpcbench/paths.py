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
