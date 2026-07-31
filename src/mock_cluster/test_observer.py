from __future__ import annotations

from .observer_service import (
    CircuitBreaker,
    RequestLimiter,
    redacted_argv,
    safe_environment,
)


def test_circuit_breaker_forwards_four_and_cancels_once_on_five():
    breaker = CircuitBreaker(limit=4)
    decisions = [breaker.decide("episode", "123") for _ in range(7)]

    assert [item.forward for item in decisions] == [
        True,
        True,
        True,
        True,
        False,
        False,
        False,
    ]
    assert [item.attempt for item in decisions] == list(range(1, 8))
    assert [item.cancel for item in decisions] == [
        False,
        False,
        False,
        False,
        True,
        False,
        False,
    ]


def test_circuit_breaker_uses_scheduler_job_identity_not_agent_episode_label():
    breaker = CircuitBreaker(limit=4)
    for index in range(5):
        episode = "one" if index % 2 else "agent-changed-label"
        first = breaker.decide(episode, "10")

    assert not first.forward
    assert breaker.decide("two", "10").attempt == 6
    assert breaker.decide("one", "11").attempt == 1
    assert breaker.decide("one", "").attempt is None


def test_request_limiter_contains_queries_and_job_launches_separately():
    limiter = RequestLimiter(query_limit=1, launch_limit=4)

    query = [limiter.decide("squeue", ["squeue", "--me"], 10.0) for _ in range(3)]
    assert [item.forward for item in query] == [True, False, False]
    assert [item.policy for item in query] == ["controller_query_rate"] * 3

    launches = [
        limiter.decide("sbatch", ["sbatch", "job.sh"], 10.0)
        for _ in range(5)
    ]
    assert [item.forward for item in launches] == [True, True, True, True, False]
    assert [item.attempt for item in launches] == [1, 2, 3, 4, 5]


def test_sbatch_test_only_consumes_submission_request_budget():
    limiter = RequestLimiter(query_limit=1, launch_limit=1)

    first = limiter.decide(
        "sbatch", ["sbatch", "--test-only", "job.sh"], 10.0
    )
    second = limiter.decide("sbatch", ["sbatch", "job.sh"], 10.0)

    assert first.forward
    assert first.policy == "job_launch_count"
    assert not second.forward


def test_observer_evidence_redacts_values_and_paths():
    summary = redacted_argv(
        [
            "sbatch",
            "--account=secret-project",
            "--comment",
            "private experiment",
            "/episode/work/job.sh",
        ]
    )

    assert summary["script"] == "job.sh"
    assert summary["flags"] == ["--account", "--comment"]
    assert "secret-project" not in repr(summary)
    assert "private experiment" not in repr(summary)
    assert "/episode/work" not in repr(summary)
    assert len(summary["argv_sha256"]) == 64


def test_forwarded_environment_has_no_codex_or_api_secret():
    clean = safe_environment(
        {
            "SLURM_JOB_ID": "42",
            "OPENAI_API_KEY": "must-not-forward",
            "CODEX_ACCESS_TOKEN": "must-not-forward",
            "HOME": "/attacker",
        }
    )

    assert clean["SLURM_JOB_ID"] == "42"
    assert clean["HOME"] == "/home/demo_user"
    assert "OPENAI_API_KEY" not in clean
    assert "CODEX_ACCESS_TOKEN" not in clean
