from __future__ import annotations

import json

import pytest

from .episode import GENERATED
from .qualification import no_agent_controller_floor
from .substrate import SubstrateError

LIMITS = json.loads((GENERATED / "detectors.json").read_text())


def event(episode_id: str, index: int) -> dict:
    return {
        "event": "slurm_client",
        "episode_id": episode_id,
        "command": "scontrol",
        "outcome": "accepted",
        "ts": float(index),
        "iso": f"2026-01-01T00:00:{index:02d}Z",
        "exit": 0,
    }


def test_no_agent_floor_excludes_infrastructure_healthchecks():
    events = [event("infrastructure", index) for index in range(12)]

    report = no_agent_controller_floor(events, "qualification", LIMITS)

    assert report == {
        "peak_queries_per_minute": 0,
        "episode_events": 0,
        "infrastructure_events_excluded": 12,
    }


def test_no_agent_floor_rejects_an_episode_attributed_query():
    events = [
        event("infrastructure", 0),
        event("qualification", 1),
    ]

    with pytest.raises(SubstrateError, match="expected zero"):
        no_agent_controller_floor(events, "qualification", LIMITS)
