# Benchmark results

Append-only. One directory per run:

```
results/YYYY-MM-DD-<who>-<label>/
  manifest.json     # conditions, seeds, model, code revision, center descriptor hash
  episodes/*.json   # one per (task, condition, seed)
  calls/*.jsonl     # simulator call logs
  summary.md        # what the run showed
```

Two rules:

- **Never edit or delete an existing run directory.** A run is a record of what
  happened, including the runs that went wrong. Supersede, don't overwrite.
- **Every run records the code revision and the descriptor hash it used.** A result
  whose inputs can't be identified isn't evidence.

Run directories are gitignored — they get large and they're per-machine. Commit only the
aggregated `summary.md` of a run a PR actually discusses, and say which run it came from.
