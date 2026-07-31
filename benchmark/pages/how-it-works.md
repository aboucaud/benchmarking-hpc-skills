---
title: How an episode works
short_title: How it works
---

Three diagrams: what the agent is handed, how its answer is scored, and how the records become
this site. Read them before any number on the other pages — several of the caveats there are
consequences of the shapes below.

## What the agent is handed, and what it does

Every episode is one `(case, condition, seed)`. The agent is given a job script carrying exactly
one injected defect and a neutral instruction to run the work. **It is never told a defect
exists.**

```{mermaid}
flowchart TD
  CY["case.yaml<br/><i>one injected defect,<br/>withheld from the agent</i>"]
  CENTER["center.yaml<br/><i>the facility descriptor</i>"]
  INSTR["INSTRUCTIONS.md"]
  SKILL["skill bundle<br/><i>portable, no site values</i>"]
  BOX["sandbox<br/><b>job.sh + prompt.md</b>"]
  AGENT(["agent"])
  EDIT["submitted job.sh"]
  STUBS["Slurm echo stubs<br/><i>log, answer, never execute</i>"]

  CY -->|"job.sh, assets"| BOX
  CENTER -->|"render.py"| INSTR
  INSTR -.->|"doc-present arms only"| BOX
  SKILL -.->|"skills arms only"| BOX
  BOX --> AGENT
  AGENT -->|"reads, edits"| EDIT
  AGENT -->|"sbatch, squeue, sinfo…"| STUBS

  classDef vary fill:#2a78d6,stroke:#1b5aa3,color:#fff
  class INSTR,SKILL vary
```

The two blue boxes are the intervention — the only things that differ between arms. `center.yaml`
is the single source of truth: it generates the document the agent reads, the limits the detectors
score against, and the mock cluster's Slurm config, so those three can never drift apart.

Nothing executes. The stubs answer as Slurm would and record the call.

## How the answer is scored

The endpoint is a **conjunction**, which is why an arm can repair more defects than the control
and still finish below it.

```{mermaid}
flowchart LR
  EDIT["submitted job.sh"] --> STATIC["<b>L1 static</b><br/>did it repair<br/>the defect?"]
  CALLS["agent's call log"] --> CONDUCT["<b>L1 call log</b><br/>conduct while<br/>working"]
  STATIC --> AND{"endpoint<br/><b>L1 ∧ L2</b>"}
  CONDUCT --> AND
  STATIC -->|"L1 pass only"| JUDGE["<b>L2 judge</b><br/>did it understand,<br/>or fix it by accident?"]
  JUDGE --> AND
  AND --> REC["episode record"]

  classDef factual fill:#199e70,stroke:#12795a,color:#fff
  classDef assessed fill:#d95926,stroke:#a63f1b,color:#fff
  class STATIC,CONDUCT factual
  class JUDGE assessed
```

Green is **factual** — deterministic detectors, no model involved. Orange is **assessed** — an LLM
judge, run twice, and disagreement between the two readings sends the episode to human review
rather than being tie-broken. The judge runs only on episodes that already passed L1, which is
most of the cost control: judging is roughly 80% of a run's spend.

Two consequences worth carrying to the other pages:

- A cell can miss for two unrelated reasons, and the audit table separates them.
- `L2` is one judge call covering several criteria at once. Only its verdict and its recognition
  finding are checked for agreement across the two readings.

## How the records become this site

No number on these pages is typed in. Each is interpolated from the episode records at build time,
so a page cannot drift from the run it describes.

```{mermaid}
flowchart LR
  JSONL["episodes.judged.jsonl<br/><i>one row per episode</i>"]
  RESULTS["astra_results.py<br/><i>imports report.endpoint_of</i>"]
  FIGS["astra_figures.py"]
  UNIV["benchmark/results/&lt;universe&gt;/"]
  ASTRA["astra.yaml<br/><i>decisions · outputs · findings</i>"]
  PAGES["MyST pages<br/><code>:::{astra}</code> directives"]
  SITE["published site"]

  JSONL --> RESULTS --> UNIV
  JSONL --> FIGS --> UNIV
  UNIV --> PAGES
  ASTRA --> PAGES
  PAGES --> SITE
```

`astra_results.py` imports the endpoint from `report.endpoint_of` rather than recomputing it —
scoring independently once dropped unjudged L1 failures from the denominator and reported near
100%. The active universe is the first file in `benchmark/universes/` when sorted, and its id
comes from the file stem, so renaming that file silently repoints the whole site.

## What none of this measures

The agent is handed a bad script and asked to run it. It is never asked to write one, so nothing
here shows whether it would have made the same mistake itself — that is the difference between
*catching* misuse and *not committing* it, and only the first is measured.

No case has sysadmin sign-off yet, so every number on this site is a pilot measuring itself.
