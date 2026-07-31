# Docs index

What each document is, its status, and the order to read them in. Code and case data live under
[`../benchmark/`](../benchmark/); this folder is prose.

## Current — read these first

| Doc | Role |
|---|---|
| [`prd.md`](prd.md) | **Start here.** Product overview: problem, thesis, MVP design with ASCII schemas, roadmap, and the open questions that need a decision. |
| [`mvp-misuse-benchmark.md`](mvp-misuse-benchmark.md) | The canonical **design & methodology** for the MVP — cases, episode flow, the three judging layers, endpoints, threats to validity. The PRD summarises this; this is the detail. |
| [`first-run-results.md`](first-run-results.md) | The **results home**: what the live runs showed, what they do and don't support, and the decisions they put in front of the team. All run findings belong here, not in the design doc. |
| [`docker-slurm-real-and-agent-visible-config.md`](docker-slurm-real-and-agent-visible-config.md) | Operator reference for the physical Docker limits and the production-shaped Slurm resources exposed to agents. |
| [`docker-slurm-all-cases.md`](docker-slurm-all-cases.md) | Coverage and laptop-safety behavior for running every case against real Docker Slurm services. |

Reading order: `prd.md` → `mvp-misuse-benchmark.md` → `first-run-results.md`.

## Future

| Doc | Role |
|---|---|
| [`benchmark-methodology.md`](benchmark-methodology.md) | The **Phase-2 target**: the more ambitious version (time-accelerated simulator, measured node-hours, 6-condition matrix). Superseded by the MVP for the hack; kept as the direction of travel. |

## Background / historical — context, not current guidance

| Doc | Role |
|---|---|
| [`context.md`](context.md) | Synthesis of the AAI4Science summit notes that framed the project. |
| [`working-notes.md`](working-notes.md) | Early planning notes and a first hand-written `INSTRUCTIONS.md` template (the canonical, generated instance now lives at [`../benchmark/generated/INSTRUCTIONS.md`](../benchmark/generated/INSTRUCTIONS.md)). |
| [`../benchmark/landscape.md`](../benchmark/landscape.md) | Prior-art / framework survey. Its *recommendation* (Inspect AI + a prompt-format layer) was **not** the path taken — the MVP uses echo-stubs + a `claude-code` runner, and those skeletons were retired in #13. The survey and sources remain useful. |
