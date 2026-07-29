# Candidate skills (under test)

These are **inputs to the benchmark**, not skills for agents working on this repo. The
harness copies the requested tier into an episode sandbox; nothing here should ever be
installed into `.claude/skills/`.

One directory per quality tier, matching the `skills` axis of the conditions matrix:

| Tier | What it is |
|---|---|
| `good/` | the real skills — the thing whose value we're trying to measure |
| `degraded/` | a deliberately vague variant: no guardrails, no estimation step |

The `none` condition installs nothing, so it has no directory.

`degraded/` is not padding. If the harness can't separate a mediocre skill from a good one,
it is only measuring skill *presence*, and any later claim that a particular skill is worth
adopting is unsupported.

Each tier follows the standard skill package shape — a `SKILL.md` with `name` and
`description` frontmatter, plus `docs/`, `templates/`, `examples/`, `lib/`, `bin/` as
needed — so a tier can be dropped into a real agent's skill set unchanged.
