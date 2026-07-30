from __future__ import annotations

import json

from .runner import parse_codex_jsonl


def test_codex_jsonl_recovers_completed_commands_and_usage():
    output = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "t1"}),
            "not json",
            json.dumps(
                {
                    "type": "item.completed",
                    "timestamp_epoch": 100.0,
                    "item": {
                        "id": "i1",
                        "type": "command_execution",
                        "command": "sed -n '1,80p' job.sh",
                        "exit_code": 0,
                    },
                }
            ),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "i2",
                        "type": "agent_message",
                        "text": "Submitted job 12.",
                    },
                }
            ),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 1000,
                        "cached_input_tokens": 750,
                        "output_tokens": 200,
                    },
                }
            ),
        ]
    )

    commands, transcript, message, cost = parse_codex_jsonl(output)

    assert len(transcript) == 4
    assert commands == [
        {
            "ts": 100.0,
            "command": "sed -n '1,80p' job.sh",
            "cwd": "",
            "exit": 0,
            "item_id": "i1",
        }
    ]
    assert message == "Submitted job 12."
    assert cost == {
        "input_tokens": 1000,
        "cached_input_tokens": 750,
        "output_tokens": 200,
    }


def test_codex_jsonl_tolerates_bytes_and_unknown_items():
    commands, transcript, message, cost = parse_codex_jsonl(
        b'{"type":"item.completed","item":{"id":"x","type":"file_change"}}\n'
    )

    assert commands == []
    assert len(transcript) == 1
    assert message == ""
    assert cost == {
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
    }
