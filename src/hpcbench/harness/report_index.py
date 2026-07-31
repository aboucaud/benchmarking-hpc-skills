#!/usr/bin/env python3
"""A landing page that lists every rendered report and links to it.

    uv run --with pyyaml python -m hpcbench.harness.report_index write \
        --reports docs/reports --out docs/reports/index.html

`report_html.py` renders one run into one self-contained page. Once there are several of those,
there is nothing that discovers them — this writes the index that sits in front of them, one card
per report, and is what GitHub Pages serves at the site root.

## It reads reports as opaque HTML

This module never imports `report_html`. A report is treated as a finished file whose *only*
guaranteed contract is its `<title>` — that is the card heading. The provenance chips (episode
count, subject model, judge) are a **best-effort** parse of the report's provenance band and are
silently dropped when absent, so a report that changes its internal markup still gets listed,
just without chips. The index therefore keeps working whether or not the report generator is
present in the tree, and cannot go stale against the generator's internals.

## What the page is built to prevent

**A dead link that looks alive.** Every card links to a sibling file that was found on disk at
build time; the page never invents an entry for a report that is not there. When the directory is
empty the page says so plainly rather than rendering an empty grid that reads as "no results".

**Reading a demo as a finding.** The lede states, before any card, that these are synthetic pilot
runs — the same caveat culture the reports themselves lead with. The index links results; it does
not endorse them.

## Self-contained, like the reports

No network requests, works offline, light/dark via `prefers-color-scheme` plus a Theme toggle that
stamps `data-theme` on the root (both directions win). The palette variables are the dataviz-skill
values the reports use, so the landing page and the pages it links to read as one surface.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

# Provenance labels lifted onto a card as chips, in display order. Each is best-effort: a report
# that does not carry the label simply contributes no chip. The value shown is the leading text of
# the report's `<dd>` (its `<span class="unit">…</span>` qualifier is dropped — it is caveat prose
# for the report, not a label for the index).
PROVENANCE_CHIPS = ("Episodes", "Subject model", "Judge")


@dataclass
class Report:
    """One rendered report file, as much as can be read from it without trusting its internals."""

    filename: str
    title: str
    chips: list[tuple[str, str]] = field(default_factory=list)


def _strip_tags(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _title_of(text: str, fallback: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    title = _strip_tags(match.group(1)) if match else ""
    return title or fallback


def _chips_of(text: str) -> list[tuple[str, str]]:
    """Best-effort `<dt>label</dt><dd>value …</dd>` pairs. Any label not found is skipped."""
    chips: list[tuple[str, str]] = []
    for label in PROVENANCE_CHIPS:
        match = re.search(
            rf"<dt>\s*{re.escape(label)}\s*</dt>\s*<dd>(.*?)</dd>",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            continue
        # Drop the trailing `<span class="unit">…</span>` qualifier, keep the leading value.
        value = _strip_tags(re.sub(r"<span\b.*", "", match.group(1), flags=re.DOTALL))
        if value:
            chips.append((label, value))
    return chips


def discover_reports(reports_dir: Path) -> list[Report]:
    """Every `*.html` in `reports_dir` except the index itself, sorted by filename."""
    if not reports_dir.is_dir():
        return []
    reports = []
    for path in sorted(reports_dir.glob("*.html")):
        if path.name == "index.html":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        reports.append(
            Report(
                filename=path.name,
                title=_title_of(text, fallback=path.stem),
                chips=_chips_of(text),
            )
        )
    return reports


# ------------------------------------------------------------------------------------------
# Presentation. Palette variables are the dataviz-skill values the reports carry, trimmed to the
# few this page uses, so the index and the reports it links share one surface in both modes.
# ------------------------------------------------------------------------------------------

_THEME_VARS_LIGHT = """
  color-scheme: light;
  --plane: #f9f9f7;
  --surface-1: #fcfcfb;
  --surface-2: #f2f1ed;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #898781;
  --border: rgba(11,11,11,0.10);
  --series-1: #2a78d6;
  --track: #cde2fb;
"""

_THEME_VARS_DARK = """
  color-scheme: dark;
  --plane: #0d0d0d;
  --surface-1: #1a1a19;
  --surface-2: #232322;
  --text-primary: #ffffff;
  --text-secondary: #c3c2b7;
  --text-muted: #898781;
  --border: rgba(255,255,255,0.10);
  --series-1: #3987e5;
  --track: #104281;
"""

_STYLE = f"""
.viz-root {{{_THEME_VARS_LIGHT}}}
@media (prefers-color-scheme: dark) {{
  :root:where(:not([data-theme="light"])) .viz-root {{{_THEME_VARS_DARK}}}
}}
:root[data-theme="dark"] .viz-root {{{_THEME_VARS_DARK}}}

* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
.viz-root {{
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--plane);
  color: var(--text-primary);
  line-height: 1.55;
  font-size: 15px;
  padding: 24px 20px 72px;
  min-height: 100vh;
}}
.wrap {{ max-width: 1180px; margin: 0 auto; }}
.topbar {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }}
h1 {{ font-size: 27px; font-weight: 600; margin: 0 0 6px; letter-spacing: -0.01em; }}
p {{ margin: 0 0 10px; }}
a {{ color: var(--series-1); }}
.lede {{ color: var(--text-secondary); max-width: 74ch; margin-bottom: 4px; }}
.muted {{ color: var(--text-muted); }}
.mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; }}
.count {{ color: var(--text-muted); font-size: 13px; margin: 20px 0 12px; }}
.theme {{
  font: inherit; font-size: 13px; cursor: pointer; white-space: nowrap;
  background: var(--surface-1); color: var(--text-secondary);
  border: 1px solid var(--border); border-radius: 999px; padding: 5px 13px;
}}
.grid {{
  display: grid; gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
}}
.card {{
  display: block; text-decoration: none; color: inherit;
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px 16px 14px;
  transition: border-color 0.12s ease, transform 0.12s ease;
}}
.card:hover {{ border-color: var(--series-1); transform: translateY(-1px); }}
.card h2 {{ font-size: 16px; font-weight: 600; margin: 0 0 6px; letter-spacing: -0.005em; }}
.card .file {{ color: var(--text-muted); margin: 0 0 12px; word-break: break-all; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.chip {{
  font-size: 12px; padding: 2px 9px; border-radius: 999px;
  background: var(--surface-2); border: 1px solid var(--border); color: var(--text-secondary);
}}
.chip b {{ color: var(--text-primary); font-weight: 600; }}
.empty {{
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 22px; color: var(--text-secondary); max-width: 74ch;
}}
.empty code {{
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px;
  background: var(--surface-2); padding: 1px 6px; border-radius: 5px;
}}
footer {{ margin-top: 48px; color: var(--text-muted); font-size: 13px; }}
"""

# `document` code is static; the labels it touches (button text) are literals, not report data.
_SCRIPT = """
(function () {
  var root = document.documentElement;
  var btn = document.getElementById('themeToggle');
  if (!btn) return;
  btn.addEventListener('click', function () {
    var now = root.getAttribute('data-theme');
    var dark = now ? now === 'dark'
                   : window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.setAttribute('data-theme', dark ? 'light' : 'dark');
    btn.textContent = dark ? 'Dark theme' : 'Light theme';
  });
})();
"""

REPO_URL = "https://github.com/aboucaud/benchmarking-hpc-skills"


def _card(report: Report) -> str:
    href = quote(report.filename)
    chips = "".join(
        f'<span class="chip">{html.escape(label)} <b>{html.escape(value)}</b></span>'
        for label, value in report.chips
    )
    chips_block = f'<div class="chips">{chips}</div>' if chips else ""
    return (
        f'<a class="card" href="./{href}">'
        f"<h2>{html.escape(report.title)}</h2>"
        f'<p class="file mono">{html.escape(report.filename)}</p>'
        f"{chips_block}"
        "</a>"
    )


def _body(reports: list[Report]) -> str:
    if reports:
        n = len(reports)
        count = f'<p class="count">{n} report{"s" if n != 1 else ""}</p>'
        grid = f'<div class="grid">{"".join(_card(r) for r in reports)}</div>'
        return count + grid
    return (
        '<div class="empty">'
        "<p>No reports have been rendered here yet.</p>"
        "<p>Render one from a run's episode records and drop it in this directory:</p>"
        "<p><code>uv run --with pyyaml python -m hpcbench.harness.report_html "
        "results/episodes-*.jsonl --out docs/reports/&lt;name&gt;.html</code></p>"
        "<p class=\"muted\">The next push to <code>main</code> rebuilds this page to list it.</p>"
        "</div>"
    )


def render_index(reports_dir: Path) -> str:
    """The full landing-page HTML for every report found in `reports_dir`."""
    reports = discover_reports(reports_dir)
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Benchmarking HPC skills — results</title>"
        f"<style>{_STYLE}</style></head>"
        '<body><div class="viz-root"><div class="wrap">'
        '<div class="topbar"><div>'
        "<h1>Benchmarking HPC skills — results</h1>"
        '<p class="lede">Does a centre-hosted <code>INSTRUCTIONS.md</code>, plus skills that '
        "consume it, stop a coding agent from misusing an HPC facility? Each report below renders "
        "one run of that misuse-repair benchmark. <b>These are synthetic pilot results</b> — read "
        "each report's provenance band before quoting any number from it.</p>"
        '</div><button class="theme" id="themeToggle" type="button">Theme</button></div>'
        f"{_body(reports)}"
        f'<footer>Generated from the report files in this directory. '
        f'Source: <a href="{REPO_URL}">{html.escape(REPO_URL)}</a>.</footer>'
        f"</div></div><script>{_SCRIPT}</script></body></html>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["write"], help="write the landing page")
    parser.add_argument(
        "--reports",
        default="docs/reports",
        help="directory of rendered *.html reports to list (default: docs/reports)",
    )
    parser.add_argument(
        "--out",
        default="docs/reports/index.html",
        help="path of the landing page to write (default: docs/reports/index.html)",
    )
    arguments = parser.parse_args()

    reports_dir = Path(arguments.reports)
    output = Path(arguments.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_index(reports_dir), encoding="utf-8")

    found = len(discover_reports(reports_dir))
    print(f"{output} — {found} report{'s' if found != 1 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
