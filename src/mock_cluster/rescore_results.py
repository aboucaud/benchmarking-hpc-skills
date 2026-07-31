"""Recompute stored Docker-Slurm L1 results from episode-scoped evidence."""

from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .episode import CASES, GENERATED, events_for_episode
from .score import DOCKER_L1_SCORING_VERSION, score_episode


def rescore_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy whose L1 score excludes other episode/infrastructure events."""
    if record.get("substrate") != "docker-slurm":
        raise ValueError("only docker-slurm records can be rescored by this module")
    case_dir = CASES / str(record["case"])
    if not case_dir.is_dir():
        raise ValueError(f"unknown case: {record['case']}")

    updated = copy.deepcopy(record)
    evidence = updated["evidence"]
    raw_events = evidence.get("observer", [])
    episode_id = str(updated["episode_id"])
    scored_events = events_for_episode(raw_events, episode_id)
    final_files = {
        name: content.encode()
        for name, content in evidence.get("final_files", {}).items()
        if isinstance(name, str) and isinstance(content, str)
    }
    case = yaml.safe_load((case_dir / "case.yaml").read_text())
    limits = json.loads((GENERATED / "detectors.json").read_text())

    updated.setdefault(
        "score_correction",
        {
            "kind": "docker_l1_rescore",
            "reason": (
                "recomputed with episode-scoped observer events, executed-plus-"
                "submitted static targets, and execution-aware login-process "
                "attribution"
            ),
            "previous_l1": copy.deepcopy(updated.get("l1")),
            "raw_observer_evidence_preserved": True,
            "scoring_version": DOCKER_L1_SCORING_VERSION,
        },
    )
    updated["l1"] = score_episode(
        case=case,
        limits=limits,
        original_job=(case_dir / "job.sh").read_text(),
        files=final_files,
        events=scored_events,
        commands=updated.get("agent", {}).get("commands", []),
        processes=evidence.get("login_processes", []),
    )
    evidence["workload_submitted"] = updated["l1"]["workload_submitted"]
    evidence["scored_observer_event_count"] = len(scored_events)
    evidence["observer_scoring_scope"] = {
        "episode_id": episode_id,
        "included_events": len(scored_events),
        "excluded_events": len(raw_events) - len(scored_events),
    }
    return updated


def _atomic_write(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    os.replace(temporary, path)


def rescore_file(path: Path) -> int:
    if path.suffix == ".jsonl":
        records = [
            rescore_record(json.loads(line))
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        content = "".join(
            json.dumps(record, sort_keys=True) + "\n" for record in records
        )
    elif path.suffix == ".json":
        records = [rescore_record(json.loads(path.read_text()))]
        content = json.dumps(records[0], indent=2, sort_keys=True) + "\n"
    else:
        raise ValueError(f"unsupported result file: {path}")
    _atomic_write(path, content)
    return len(records)


def result_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if not target.is_dir():
        raise ValueError(f"result path does not exist: {target}")
    return [
        *sorted(target.glob("episodes-*.jsonl")),
        *sorted((target / "artifacts").glob("*.json")),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    arguments = parser.parse_args(argv)

    total = 0
    for path in result_files(arguments.path):
        count = rescore_file(path)
        total += count
        print(f"rescored {count}: {path}")
    print(f"rescored {total} stored record copies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
