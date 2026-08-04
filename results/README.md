# Benchmark results

Append-only. `src/hpcbench/harness/episode.py` writes here (default `--results ./results`):

```
results/
  episodes-<YYYYMMDDThhmmss>.jsonl   # one JSON row per (case, condition, seed) episode
  artifacts/
    <YYYYMMDDThhmmss>/                                # the same stamp as the run's .jsonl
      <case>__<condition>__seed<n>.transcript.json    # the agent's transcript
      <case>__<condition>__seed<n>.calls.jsonl        # stub + agent call log
      <case>__<condition>__seed<n>.scripts.json       # scripts the agent ran / submitted
```

The artifacts used to sit directly under `artifacts/` with no run stamp, so a second run into the
same `--results` overwrote the first cell by cell. That happened: a `scripted-asis` calibration
replaced 27 of the 108-episode matrix's transcripts, every one of them `doc-absent_skills-none`.
Records written before this change carry a bare stem and still resolve against `artifacts/`.

Two rules:

- **Never edit or delete an existing run.** A run is a record of what happened, including the runs
  that went wrong. Supersede, don't overwrite. The harness no longer relies on people remembering
  this: artifact paths carry the run stamp, and a collision is suffixed rather than clobbered.
- **Every run records the code revision and the descriptor it used.** A result whose inputs can't
  be identified isn't evidence — the harness stamps `schema_version` and the code revision into the
  records for this reason.

Everything under `results/` is **gitignored** (`results/**`, except this README) — runs get large
and are per-machine. When a PR discusses a result, commit the aggregated summary into the PR/docs
(e.g. `docs/first-run-results.md`) and say which run it came from, rather than committing the raw
`episodes-*.jsonl`.
