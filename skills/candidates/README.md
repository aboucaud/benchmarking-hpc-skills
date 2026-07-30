# Candidate skills (under test)

These are **inputs to the benchmark**, not skills for agents working on this repo. The harness
copies the requested tier into an episode sandbox; nothing here should ever be installed into
`.claude/skills/` (that would put it in the context of every agent working on the repo and
contaminate every episode).

One directory per quality tier, matching the `skills` axis of the conditions matrix:

| Tier | What it is |
|---|---|
| `good/` | the real skills — the thing whose value we're trying to measure |
| `degraded/` | a deliberately vague variant: no guardrails, no estimation step (**Phase 2**) |

The `none` condition installs nothing, so it has no directory.

`degraded/` is not padding. If the harness can't separate a mediocre skill from a good one, it is
only measuring skill *presence*, and any later claim that a particular skill is worth adopting is
unsupported.

Each tier follows the standard skill package shape — a `SKILL.md` with `name` and `description`
frontmatter, plus `docs/`, `templates/`, `examples/`, `lib/`, `bin/` as needed — so a tier can be
dropped into a real agent's skill set unchanged.

**Open question — how a skill is delivered.** The first live run installed the bundle to
`work/.claude/skills/<name>/`, which is Claude-Code-specific; the proposal is to ship the skill as
plain markdown beside `INSTRUCTIONS.md` and point at it, so the benchmark isn't harness-specific and
matches what a centre can actually deploy. This is unsettled — see
[`../../docs/first-run-results.md`](../../docs/first-run-results.md) Decision 1 — and it blocks the
skills arm of the 2×2.
