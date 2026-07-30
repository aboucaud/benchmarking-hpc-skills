# Generated from `center.yaml`

Everything else in this directory is generated. Do not hand-edit it — regenerate:

```bash
uv run --with pyyaml benchmark/render.py write
```

Committed rather than built on demand, so a reviewer can read the document an agent was actually
shown, and so a stale artefact shows up as a diff. `render.py check` fails if any file here has
drifted from the descriptor.

| File | Consumer |
|---|---|
| `INSTRUCTIONS.md` | the intervention the agent reads in the doc-present arm |
| `detectors.json` | the limits the L1 detectors score against |
| `mock-cluster.conf` | node and partition config for the Docker cluster in `mock-cluster/` |
| `mock-cluster-gres.conf` | GPU GRES for the same, with no device behind it |

A fifth consumer is built per episode rather than committed: `stubs/install_stubs.py` writes
`cluster.json` into each sandbox, holding only what the echo stubs may answer.

## Why generated

Four renderings of one descriptor cannot contradict each other; four hand-written files can, and
the ways they do are quiet. A document promising a 24-hour ceiling while the scheduler enforces
thirty minutes invalidates every doc-present episode without failing anything, and the result
still looks like a result.

## `INSTRUCTIONS.md` is an intervention, not documentation

Two rules, both tested, both easy to break by being helpful:

**It must not reveal that it is part of an evaluation.** No mention of the benchmark, the
repository, or the word "fictional". An agent that knows it is being tested does not behave the
way it behaves at work, and natural conduct is the entire measurement. This is a deliberate
choice, recorded here rather than left implicit: the reader of a result should know the agent was
not told.

**It must not point at a specific case.** An earlier draft said the partition names "do not
describe their hardware" — true, useful, and aimed squarely at C3, the case carrying the whole
weight of the doc-present contrast. Coaching the intervention toward the case it is measured on
inflates its apparent value.

The document still has to *contain* the facts each family needs — a document that helps with
nothing measures nothing either. `test_render.py` checks both directions.

## Invariant versus scaled

Two substrates exist deliberately: echo stubs for cheap large-N, the Docker cluster for fidelity.
Cross-validating a case across them only means something if both present the same cluster — but
three containers cannot be four hundred 128-core nodes, so "the same cluster" has to be defined.

**Invariant** — partition names, walltime and node ceilings, which partition has GPUs, the default
partition, the account. Every case turns on one of these, so they must be identical on every
substrate.

**Scaled** — cores per node, memory, node counts, filesystem sizes. Nothing a case tests depends
on these being physically true. CPUs and GPUs in `mock-cluster.conf` are *advertised*: Slurm
schedules against the declared count, nothing here computes, and a request should be accepted or
rejected for the reason the case is about rather than because a laptop is small.

```bash
uv run --with pyyaml benchmark/render.py drift
```

compares the invariants against `mock-cluster/slurm.conf` and reports which cases the Docker
cluster is big enough to run.
