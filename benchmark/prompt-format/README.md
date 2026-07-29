# Prompt-format benchmark (EngiAI-style)

A second, complementary benchmark type, after **Appendix C.2 ("HPC Training
Prompts") of EngiAI, [arXiv:2605.19743](https://arxiv.org/abs/2605.19743)**.

Where the [`../inspect/`](../inspect/) benchmark fixes the prompt and flips the
*instructions*, this one fixes the instructions and flips the **prompt format** —
measuring how sensitive end-to-end task completion is to phrasing.

| Format | Prompt | Tests |
|--------|--------|-------|
| `explicit` | [`prompts/explicit.tmpl.md`](prompts/explicit.tmpl.md) | numbered steps that name the tools |
| `natural`  | [`prompts/natural.tmpl.md`](prompts/natural.tmpl.md) | high-level ask; agent must infer the workflow |

EngiAI's finding: agents complete the explicit form far more reliably than the
natural one, and later steps (submit → monitor → evaluate) degrade most. That
gap is precisely what a standardized `INSTRUCTIONS.md` should close — so combine
this with `../inspect/` into a **2×2** ({explicit, natural} × {instructions off,
on}) and test whether instructions recover natural-language performance (see the
commented `instructions:` axis in [`tasks.yaml`](tasks.yaml) and
[`../landscape.md`](../landscape.md)).

## The task

Identical across both formats (only the phrasing differs):

1. generate a SLURM script training with the right algorithm/problem/epochs/seed,
2. submit it,
3. monitor it to `COMPLETED`,
4. evaluate the trained model's metric.

Because we don't have EngiOpt, [`train_stub.py`](train_stub.py) is a tiny
deterministic stand-in training job (pure stdlib) that writes a `score` to
`results/metrics.json`. Swap in a real training entry point later — the scorer
only checks the four steps above.

## Files

- [`prompts/`](prompts/) — the two prompt templates (`{{placeholders}}`).
- [`tasks.yaml`](tasks.yaml) — the grid: formats × workloads × 10 seeds, 100 epochs.
- [`train_stub.py`](train_stub.py) — runnable stand-in training job.
- [`score.py`](score.py) — format-agnostic four-step completion oracle.

## Provenance caveat

The **prompt templates are reconstructed, not verbatim**. The exact Appendix C
strings are not present in the paper's public HTML rendering, so the templates
reproduce the *format* EngiAI describes (explicit vs natural) adapted to our
cluster. They are marked and drop-in replaceable — paste the verbatim EngiAI
prompts into `prompts/*.tmpl.md` if you obtain the PDF/supplementary material.

## Run

The runner (submitting rendered prompts to the agent on the mock cluster) is TBD
and shares the sandbox with `../inspect/`. Meanwhile the pieces work standalone:

```bash
# the stand-in job runs anywhere, no cluster needed
python train_stub.py --algorithm adam --problem beam --epochs 2 --seed 1 --out results/metrics.json

# and the metric step of the oracle scores that output
python score.py --algorithm adam --problem beam --epochs 2 --seed 1
```

## Status — skeleton

Working today: prompt templates, the task grid, the stand-in training job, and
the metric check in `score.py`. Stubbed (`TODO` in `score.py`): the
submitted/completed step checks, which must read real job ids and `sacct` state
from @dkn16's mock cluster, plus the small runner that renders `tasks.yaml` into
prompts and drives the agent.
