#!/usr/bin/env bash
#
# The full 2x2 overnight, then the judge pass.
#
#     ./scripts/run-matrix.sh
#
# 9 cases x 4 conditions x 3 seeds = 108 episodes on the echo-stub substrate. No Docker, no
# cluster, no network beyond the model API. Roughly 2.5-3 h.
#
# Cost, and the honest range. The pilot measured $0.062/episode to run and $0.45 per *judged*
# episode, which puts this at about $7 + $20 = under $30. But a four-episode rehearsal of this
# exact pipeline judged at $1.88/episode — 4x the pilot's rate, on a tiny sample where two of
# four drew judge disagreement and were re-read. If that rate is the real one rather than noise,
# judging lands nearer $80. Watch the "judge spend" line the judge prints, and stop it if the
# per-episode figure is far off the pilot's.
#
# Everything it needs is checked before the first episode. It is safe to re-run: results are
# appended under results/ with a timestamp, never overwritten.
#
# Deliberately NOT here: --skip-live-preflight. If authentication is broken, this must fail in
# the first ten seconds rather than at 3am with 40 episodes of environment failures in the file.

set -euo pipefail

cd "$(dirname "$0")/.."

SKILLS="skills/candidates/good/hpc-conduct"
SEEDS="${SEEDS:-3}"
STAMP="$(date +%Y%m%dT%H%M%S)"
LOG="results/run-${STAMP}.log"

# `zsh -lc` does not source ~/.zshrc — it is read for interactive shells only — so a key that
# works in your terminal is invisible to anything launched non-interactively. Pick it up
# explicitly rather than letting the preflight fail on a key that is, from the user's point of
# view, obviously set.
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -f "$HOME/.zshrc" ]; then
    # shellcheck disable=SC1091
    source "$HOME/.zshrc" >/dev/null 2>&1 || true
fi
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "ANTHROPIC_API_KEY is not set. Export it, or put it in ~/.zshrc." >&2
    exit 1
fi
export ANTHROPIC_API_KEY

echo "== gates =========================================================="
uv run --with pyyaml src/hpcbench/validate_cases.py >/dev/null
echo "  cases consistent with center.yaml"
uv run --with pyyaml src/hpcbench/render.py check >/dev/null
echo "  benchmark/generated/ up to date"
test -f "$SKILLS/SKILL.md" || { echo "no skill bundle at $SKILLS" >&2; exit 1; }
echo "  skill bundle present"

# Disk: an episode keeps a transcript, a call log and the scripts it touched. 108 of those plus
# the sandboxes is small, but a full disk mid-run corrupts the tail of a JSONL rather than
# stopping cleanly, so it is worth one check.
avail_gb="$(df -g . | awk 'NR==2 {print $4}')"
if [ "$avail_gb" -lt 5 ]; then
    echo "only ${avail_gb}G free — free some space first" >&2
    exit 1
fi
echo "  ${avail_gb}G free"

mkdir -p results
echo
echo "== running ========================================================"
echo "  108 episodes (9 cases x 4 conditions x ${SEEDS} seeds)"
echo "  log:     $LOG"
echo "  records: results/episodes-<stamp>.jsonl, written and flushed per episode"
echo
echo "  Safe to interrupt: every scored episode is already on disk. Nothing is"
echo "  buffered to the end of the run."
echo

# caffeinate: -i no idle sleep, -m no disk sleep, -s no system sleep on AC. Without it the
# machine suspends partway and the run dies silently. Closing the lid still sleeps it.
caffeinate -ims uv run --with pyyaml src/hpcbench/harness/episode.py all \
    --matrix \
    --skills "$SKILLS" \
    --seeds "$SEEDS" \
    --results results \
    2>&1 | tee "$LOG"

echo
echo "== judging ========================================================"
echo "  L1 alone cannot tell an agent that understood the problem from one"
echo "  that fixed it by accident. The primary endpoint needs this pass."
echo

# `opus`, matching the pilot. judge.py defaults to `sonnet`, and a run judged by a different
# model than the one that judged the pilot is not comparable to it — the judge is part of the
# measurement, which is why the report prints it in the provenance band.
LATEST="$(ls -t results/episodes-*.jsonl | head -1)"
#
# `--l1-pass-only` is what the pilot did and is why it judged 38 of 90 rather than all 90.
# An L1 failure is already a failure and L2 would only restate it; the distinctions L2 exists
# for — did the agent understand, is this a regression dressed as a fix — arise only once the
# script already looks correct. It is also most of the cost control: judging is ~75% of a run's
# spend, and this cuts it to the episodes where it changes an answer.
#
# The report knows the difference and says "L2 coverage: partial" in the provenance band, so
# this does not quietly become a claim of full coverage.
caffeinate -ims uv run --with pyyaml src/hpcbench/harness/judge.py "$LATEST" \
    --model opus --l1-pass-only 2>&1 | tee -a "$LOG"

JUDGED="${LATEST%.jsonl}.judged.jsonl"
echo
echo "== report ========================================================="
if [ -f "$JUDGED" ]; then
    uv run --with pyyaml python -m hpcbench.harness.report_html "$JUDGED" \
        --out "results/report-${STAMP}.html" \
        --title "Misuse-repair benchmark — full 2x2, ${SEEDS} seeds"
    echo "  open results/report-${STAMP}.html"
else
    echo "  no judged file at $JUDGED — render L1-only with:" >&2
    echo "    uv run --with pyyaml python -m hpcbench.harness.report_html $LATEST --out r.html" >&2
fi

echo
echo "Nine cases, one model, no sysadmin sign-off (#10), three seeds. The"
echo "report states all of it before it states a number; keep it that way"
echo "when the numbers get quoted."
