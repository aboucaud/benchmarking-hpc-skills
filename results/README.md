# Benchmark results

Append-only. `benchmark/harness/episode.py` writes here (default `--results ./results`):

```
results/
  episodes-<YYYYMMDDThhmmss>.jsonl   # one JSON row per (case, condition, seed) episode
  artifacts/
    <case>__<condition>__seed<n>.transcript.json   # the agent's transcript
    <case>__<condition>__seed<n>.calls.jsonl        # stub + agent call log
    <case>__<condition>__seed<n>.scripts.json       # scripts the agent ran / submitted
```

Two rules:

- **Never edit or delete an existing run.** A run is a record of what happened, including the runs
  that went wrong. Supersede, don't overwrite.
- **Every run records the code revision and the descriptor it used.** A result whose inputs can't
  be identified isn't evidence — the harness stamps `schema_version` and the code revision into the
  records for this reason.

Everything under `results/` is **gitignored** (`results/**`, except this README) — runs get large
and are per-machine. When a PR discusses a result, commit the aggregated summary into the PR/docs
(e.g. `docs/first-run-results.md`) and say which run it came from, rather than committing the raw
`episodes-*.jsonl`.
