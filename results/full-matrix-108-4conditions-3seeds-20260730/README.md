# Full 2×2 — 108 episodes, echo-stub substrate

9 cases × 4 conditions × 3 seeds. Subject `sonnet` (`claude-code` runner), judge `opus`, judge
prompt `l2-1`. Written up in [`docs/full-matrix-results.md`](../../docs/full-matrix-results.md);
rendered as [`docs/reports/full-matrix-108-judged.html`](../../docs/reports/full-matrix-108-judged.html).

| file | what |
|---|---|
| `episodes.jsonl` | one row per episode: condition, seed, L1 findings per detector, evidence, cost |
| `episodes.judged.jsonl` | the same rows plus `l2` — judge verdict, both readings, disagreement |

Every number in the write-up and the report is recomputable from `episodes.judged.jsonl` alone.

## What is not here, and why

**The per-episode artifacts — transcripts, call logs, scripts — are deliberately not published.**

The agent prompt tells the agent to look for site guidance in the working directory *or under
`skills/`*. In the `doc-absent` arm there is nothing to find, and 36 of 108 episodes responded by
searching the host filesystem (`find / -maxdepth 6 -iname 'INSTRUCTIONS.md'`, `find / -type d
-iname skills`). The sandbox is a directory, not a container, so those searches succeeded — the
transcripts contain the operator's home directory layout, hostname, and the names of unrelated
private repositories. That is an artefact of who ran it, not data about the benchmark.

**The arms are not contaminated.** Checked before publishing, and worth stating precisely because
the searches make it a fair question:

- **0** episodes read a file outside their own sandbox, by any route — `Read`, `cat`, `head`, `sed`.
  The searches returned paths; no agent opened one.
- Distinctive `INSTRUCTIONS.md` text appears in **27/27** `doc-present_skills-none` and **27/27**
  `doc-present_skills-good` episodes, and **0/54** `doc-absent` ones.
- Distinctive `SKILL.md` text appears in **27/27** of each `skills-good` arm and **0/54**
  `skills-none` ones.

A clean 27/27/27/27 separation. The searches were a near miss rather than a leak, and the harness
should not rely on that twice — see the sandbox-isolation issue.

## Redaction

`episodes.judged.jsonl` has five occurrences of the operator's home path replaced with
`/Users/<redacted>`. All five are inside judge free-text notes, four of them the judge *reporting*
the filesystem escape above — kept rather than cut, because the observation is a finding. Nothing
else was altered; `episodes.jsonl` is byte-identical to the run output.

Per [`../README.md`](../README.md) results are append-only: this directory supersedes nothing and
must not be edited.
