#!/usr/bin/env python3
"""Read the intervention stamp back: does this results file describe one experiment?

    uv run --with pyyaml src/hpcbench/harness/provenance.py results/episodes-*.jsonl
    uv run --with pyyaml src/hpcbench/harness/provenance.py results/*.jsonl --tree

`episode.intervention_digest` writes `episode["intervention"]` on both substrates — content
hashes of the document, the skill bundle and the case files, taken at materialization time.
Writing it changed nothing on its own: nothing read it, so a file pooling two experiments still
produced one rate, silently. This is the reader.

Two different questions, and only the first can fail a run:

1. **Do the records agree with each other?** Every doc-present episode in a pooled set must
   name the same document, every skills-good episode the same bundle, every episode of a case
   the same fixtures. Disagreement means the file is two runs wearing one set of labels — the
   #29 shape, where two substrates served two documents under `doc-present` for the whole pilot
   and the only visible difference was the rate. This is a hard error at the pooling point.

2. **Do they agree with the tree?** Advisory, and `--tree` only. The tree legitimately moves on
   after a run; the point is that nothing else says so. #34 was a whole matrix run against a
   skill bundle `main` did not have, and every record looked correct because they *were* all
   correct relative to each other. Only comparing against the material can catch that, and it
   is a re-run notice rather than an error.

**A missing stamp is unknown, never agreement.** Records predating the field carry no
`intervention` at all, and the easy bug is to let `None == None` read as "these match". They
are counted and named as unstamped, and they are never evidence that a set is homogeneous —
the 108 echo-stub records of the published matrix are exactly this case and are unrecoverable,
because nothing hashed the material while it existed. The Docker substrate's are not: see
`mock_cluster/backfill.py`, which recovers them from what it recorded at the time.

One field does not travel between substrates — `case_files_sha256`, because the two deliver
`prompt.md` differently. It is grouped and compared within a substrate, and `GLOBAL_FIELDS`
says why at the point where that choice is made.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Fields whose value must be constant across every record that has one, on either substrate.
#
# `case_files_sha256` is deliberately absent, and not only because it is per-case. It is also
# per-SUBSTRATE: the echo stub appends the site-guidance pointer to `prompt.md` and the Docker
# substrate builds its pointer into the prompt it sends instead, so the same unchanged case
# stamps two different values (measured: B2-home-output is `f0b5890dc8b2` under the stub and
# `c8c965924e11` under Docker, with identical file names and an identical document). Comparing
# it across substrates reports drift that is really a difference in delivery, so it is grouped
# and compared within a substrate only.
#
# The two fields here are cross-substrate on purpose: `document_sha256` is a plain content hash
# and `skills_sha256` is the same roll-up on both sides, which is what makes "did both substrates
# serve the one document" (#29) a question the data can answer.
GLOBAL_FIELDS = ("document_sha256", "skills_sha256")

# The stub is the default because its records predate `substrate` entirely.
STUB, DOCKER = "echo-stub", "docker-slurm"


def substrate_of(episode: dict) -> str:
    return str(episode.get("substrate") or STUB)


def short(digest: str | None) -> str:
    return "--------" if digest is None else digest[:12]


def stamp_of(episode: dict) -> dict | None:
    """The record's intervention block, or `None` if it predates the field.

    `None` and `{}` are both "this record cannot say", and neither is `{"document_sha256": None}`
    — which is a record that *can* say, and says the arm carried no document.
    """
    stamp = episode.get("intervention")
    return stamp if isinstance(stamp, dict) and stamp else None


def _describe(episode: dict) -> str:
    label = (episode.get("condition") or {}).get("label", "?")
    return f"{episode.get('case', '?')}/{label}/seed{episode.get('seed', '?')}"


@dataclass
class Audit:
    """What a set of records can and cannot say about which experiment produced it."""

    stamped: int = 0
    unstamped: list[str] = field(default_factory=list)
    values: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # Keyed by (substrate, case) — see GLOBAL_FIELDS on why the substrate belongs in the key.
    case_files: dict[tuple[str, str], set[str]] = field(default_factory=lambda: defaultdict(set))
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> list[str]:
        """Lines fit for a report. Says what is known *and* what is unknown, always both."""
        lines = []
        for name in GLOBAL_FIELDS:
            seen = sorted(self.values[name])
            if not seen:
                lines.append(f"- `{name}`: none — no record in this set carried one.")
            elif len(seen) == 1:
                lines.append(f"- `{name}`: `{short(seen[0])}`")
            else:
                lines.append(
                    f"- **`{name}`: {len(seen)} distinct values** "
                    f"({', '.join(f'`{short(value)}`' for value in seen)}) — these records were "
                    f"not run against the same material."
                )
        if self.unstamped:
            lines.append(
                f"- **{len(self.unstamped)} of {self.stamped + len(self.unstamped)} records carry "
                f"no stamp.** They predate `episode['intervention']`, so they cannot say which "
                f"material they ran against. Unknown, not matching: they are no evidence that "
                f"this set is homogeneous."
            )
        return lines


def audit(episodes: list[dict]) -> Audit:
    """Check that a set of records describes one experiment. Never reads the tree."""
    result = Audit()
    for episode in episodes:
        stamp = stamp_of(episode)
        if stamp is None:
            result.unstamped.append(_describe(episode))
            continue
        result.stamped += 1
        for name in GLOBAL_FIELDS:
            value = stamp.get(name)
            # `None` is not collected. In a doc-absent episode it is the correct answer and means
            # "no document was given" — folding it in would report every 2x2 matrix as carrying
            # two documents, and a check that fires on every healthy run is a check nobody reads.
            if value is not None:
                result.values[name].add(value)
        if stamp.get("case_files_sha256") is not None:
            key = (substrate_of(episode), episode.get("case", "?"))
            result.case_files[key].add(stamp["case_files_sha256"])

    for name in GLOBAL_FIELDS:
        seen = sorted(result.values[name])
        if len(seen) > 1:
            offenders = {
                short(stamp[name]): _describe(episode)
                for episode in episodes
                if (stamp := stamp_of(episode)) and stamp.get(name) is not None
            }
            result.problems.append(
                f"{name}: {len(seen)} distinct values across one results file — "
                + ", ".join(f"{value} (e.g. {where})" for value, where in sorted(offenders.items()))
            )

    for (substrate, case), seen in sorted(result.case_files.items()):
        if len(seen) > 1:
            result.problems.append(
                f"case_files_sha256: {case} on {substrate} ran against {len(seen)} versions of "
                f"its own fixtures ({', '.join(short(value) for value in sorted(seen))})"
            )
    return result


def tree_stamp(
    cases: list[Path], skills_path: Path | None = None, substrate: str = STUB
) -> dict[str, dict]:
    """What each case would stamp if it were materialized from the working tree right now.

    Materialized for real, through whichever substrate's own code path, rather than hashing the
    source files in place. Both substrates transform what they copy — the stub flattens `assets/`
    and appends the site-guidance pointer to `prompt.md`, Docker adds its agent fixtures and
    delivers its pointer in the prompt instead — so the bytes an agent sees are not the bytes on
    disk, and by different amounts. Recomputing either here would be a second implementation of
    the thing whose drift this module exists to detect.

    Imported lazily: the audit above is stdlib-only and runs inside the reporters, while this
    reaches into both harnesses and is only ever asked for from the command line.
    """
    import tempfile

    if substrate == DOCKER:
        import hashlib

        from mock_cluster.episode import (
            Condition as DockerCondition,
        )
        from mock_cluster.episode import (
            intervention_from_digests,
            materialize_condition,
        )

        docker_condition = DockerCondition(doc=True, skills="good" if skills_path else "none")
        return {
            case_dir.name: intervention_from_digests({
                name: hashlib.sha256(content).hexdigest()
                for name, content in materialize_condition(
                    case_dir, docker_condition, skills_path
                ).items()
            })
            for case_dir in cases
        }

    from hpcbench.harness.episode import Condition, intervention_digest, materialize

    condition = Condition(doc=True, skills="good" if skills_path else "none")
    stamps = {}
    for case_dir in cases:
        with tempfile.TemporaryDirectory(prefix="hpcbench-provenance-") as temporary:
            sandbox = Path(temporary) / "sandbox"
            materialize(case_dir, sandbox, condition, skills_path)
            stamps[case_dir.name] = intervention_digest(sandbox / "work", condition)
    return stamps


def drift(episodes: list[dict], trees: dict[str, dict[str, dict]]) -> list[str]:
    """Which stamped records ran against material the tree no longer has.

    Advisory by design. A run is a measurement of the experiment as it stood, and the experiment
    is allowed to change afterwards — what is not allowed is for that to be invisible. Each line
    here means the same thing: those numbers cannot be reproduced from this checkout, and the
    honest next step is a re-run rather than a re-score.

    `trees` is keyed by substrate, and a record is only ever compared against its own. Comparing
    a Docker record's `case_files_sha256` against the stub's tree reports every case as drifted,
    including cases nobody has touched — that is a difference in how the two substrates deliver
    the prompt, not a change in the experiment.
    """
    notices = []
    for name in ("document_sha256", "skills_sha256", "case_files_sha256"):
        by_case = name == "case_files_sha256"
        mismatched: dict[tuple[str, str], int] = defaultdict(int)
        for episode in episodes:
            stamp = stamp_of(episode)
            if stamp is None or stamp.get(name) is None:
                continue
            case = episode.get("case", "?")
            substrate = substrate_of(episode)
            expected = ((trees.get(substrate) or {}).get(case) or {}).get(name)
            if expected is not None and stamp[name] != expected:
                mismatched[(substrate, case if by_case else "")] += 1
        for (substrate, case), count in sorted(mismatched.items()):
            where = f" for {case}" if case else ""
            notices.append(
                f"{name}{where} on {substrate}: {count} record(s) ran against material this "
                f"checkout no longer has — re-run rather than re-score."
            )
    return notices


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("episodes", nargs="+", type=Path, help="episodes*.jsonl, judged or not")
    parser.add_argument("--tree", action="store_true",
                        help="also compare against the working tree; advisory, never fatal")
    parser.add_argument("--skills", type=Path, default=None,
                        help="skill bundle to materialize for the --tree comparison")
    arguments = parser.parse_args()

    records = []
    for path in arguments.episodes:
        records += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not records:
        print("no records", file=sys.stderr)
        return 1

    result = audit(records)
    print(f"{len(records)} records from {len(arguments.episodes)} file(s)")
    for line in result.summary():
        print(f"  {line.lstrip('- ')}")

    if arguments.tree:
        from hpcbench.paths import BENCHMARK
        cases = sorted(
            path for path in (BENCHMARK / "cases").iterdir() if (path / "case.yaml").exists()
        )
        # Only the substrates actually present, so a stub-only file does not pay to materialize
        # the Docker tree and vice versa.
        trees = {
            substrate: tree_stamp(cases, arguments.skills, substrate)
            for substrate in sorted({substrate_of(record) for record in records})
        }
        for notice in drift(records, trees) or ["tree: matches"]:
            print(f"  {notice}")

    for problem in result.problems:
        print(f"MIXED: {problem}", file=sys.stderr)
    return 1 if result.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
