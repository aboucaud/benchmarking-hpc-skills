#!/usr/bin/env python3
"""Tests for the HTML report generator.

    uv run --with pyyaml --with pytest pytest tests/test_report_html.py -q

These cover the things that can regress *silently* — where the page still renders, still looks
finished, and is now wrong or unusable:

  - `test_l1_only_file_renders_and_says_so` — an unjudged file must render, and must announce that
    it is not the primary endpoint. A page that quietly falls back to L1 and presents the result
    with the same confidence as a judged one is the worst failure available here.
  - `test_an_unstable_cell_is_marked_unstable` — stability is the load-bearing encoding. If the
    marker stops being emitted, every cell reads as a finding.
  - `test_stability_is_not_carried_by_colour_alone` — the marker has to survive a reader who
    cannot see the fill, so it is asserted as text and as per-seed shape, not as a class name.
  - `test_no_external_references` — "self-contained" is a promise about a file that is emailed
    around and opened offline. One `<script src>` breaks it and nothing looks different locally.
  - `test_grid_numbers_match_report_py` — the two reports must not disagree. They share
    `endpoint_of`/`cell_marks`, and this pins that they still do.

The palette is validated by the dataviz skill's own script rather than here — it is a property of
the colour values, not of this code, and re-implementing ΔE in a test would be exactly the
eyeballing the skill forbids. Recorded runs, all against the skill's `validate_palette.js`:

    node validate_palette.js "#2a78d6,#eb6834,#1baf7a" --mode light --pairs all   -> ALL PASS
    node validate_palette.js "#3987e5,#d95926,#199e70" --mode dark  --pairs all \
        --surface "#1a1a19"                                                       -> ALL PASS
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from hpcbench.harness import report, report_html  # noqa: E402

# ------------------------------------------------------------------------------------------
# Fixtures — synthetic episodes, so the tests do not depend on a run having been done
# ------------------------------------------------------------------------------------------


def episode(
    case: str,
    condition: str,
    seed: int,
    prevented: bool,
    *,
    judged: bool = True,
    submitted: bool = True,
    rejected: int = 0,
) -> dict:
    record = {
        "case": case,
        "family": case[:1],
        "condition": {"label": condition, "doc": "present" in condition, "skills": "none"},
        "seed": seed,
        "model": "sonnet",
        "validity": "ok",
        "cost": {"usd": 0.06},
        "evidence": {"workload_submitted": submitted, "submissions_rejected": rejected},
        "l1": {
            "prevented": prevented,
            "prevented_without_running": prevented and not submitted,
            "static": {"verdict": "pass" if prevented else "fail", "findings": []},
            "call_log": {"verdict": "pass", "findings": []},
        },
    }
    if judged:
        record["l2"] = {
            "verdict": "prevented" if prevented else "not_prevented",
            "judge_model": "opus",
            "prompt_version": "l2-1",
            "cost_usd": 0.4,
            "readings": [
                {
                    "verdict": "prevented" if prevented else "not_prevented",
                    "confidence": "high",
                    "recognition_quote": (
                        "the loop issues one srun per iteration" if prevented else ""
                    ),
                }
            ],
        }
        record["endpoint"] = {"prevented": prevented, "fixed_by_accident": False}
    return record


@pytest.fixture
def unstable_run() -> list[dict]:
    """One cell that flips (2 of 5), one that never does (0 of 5)."""
    records = []
    for seed in range(5):
        records.append(
            episode("A1-srun-loop", "doc-present_skills-none", seed, prevented=seed < 2)
        )
        records.append(
            episode("A2-poll-storm", "doc-absent_skills-none", seed, prevented=False)
        )
    return records


def write(tmp_path: Path, records: list[dict], name: str = "episodes.jsonl") -> Path:
    path = tmp_path / name
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    return path


def render(tmp_path: Path, records: list[dict], **kwargs) -> str:
    return report_html.build_page(records, "Test report", ["episodes.jsonl"], [], **kwargs)


# ------------------------------------------------------------------------------------------


def test_l1_only_file_renders_and_says_so(tmp_path):
    """No `l2`/`endpoint` key anywhere: it must render, and it must not present itself as the
    primary endpoint."""
    records = [
        episode("A1-srun-loop", "doc-present_skills-good", 0, prevented=True, judged=False),
        episode("C2-over-request", "doc-present_skills-good", 0, prevented=False, judged=False),
    ]
    page = render(tmp_path, records)

    assert "<title>" in page and page.rstrip().endswith("</html>")
    assert "1/1" in page and "0/1" in page  # both cells scored off L1
    lowered = page.lower()
    assert "not the primary endpoint" in lowered
    assert "l1 only" in lowered
    assert "judge.py" in page  # tells the reader how to get the real endpoint


def test_l1_only_marks_every_cell_as_single_seed(tmp_path):
    """One seed and a coin flip look identical — the page has to say which it is looking at."""
    records = [episode("A1-srun-loop", "doc-present_skills-good", 0, prevented=True, judged=False)]
    page = render(tmp_path, records)
    assert "1 seed" in page


def test_an_unstable_cell_is_marked_unstable(tmp_path, unstable_run):
    page = render(tmp_path, unstable_run)
    assert ">flips<" in page, "the unstable cell lost its marker"
    # ...and the stable cell did not acquire one.
    assert page.count(">flips<") == 1 + 1, "expected one cell marker plus one legend key"
    assert "flips across seeds" in page  # the per-case table's own wording


def test_stability_is_not_carried_by_colour_alone(tmp_path, unstable_run):
    """The distinction has to survive a reader who cannot see the fill: a text chip in the cell,
    per-seed shapes, and a stability column in the table view."""
    page = render(tmp_path, unstable_run)
    assert "dot dot-on" in page and "dot dot-off" in page  # filled vs hollow, not two colours
    assert "flips across seeds" in page and "consistent" in page  # words, in the per-case table
    assert "Stability" in page


def test_stable_cells_are_not_reported_as_flipping(tmp_path):
    records = [
        episode("A1-srun-loop", "doc-absent_skills-none", s, prevented=True) for s in range(5)
    ]
    page = render(tmp_path, records)
    assert page.count(">flips<") == 1, "only the legend key should mention flips"
    assert "5/5" in page


def test_no_external_references(tmp_path, unstable_run):
    """Self-contained: no network request when the file is opened offline."""
    page = render(tmp_path, unstable_run)
    forbidden = [
        r"https?://",
        r"src\s*=",
        r"<link\b",
        r"@import",
        r"<iframe\b",
        r"url\(",
        r"//cdn\.",
        r"fonts\.googleapis",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, page, re.I), f"external reference matched {pattern!r}"
    assert "<style>" in page and "<script>" in page  # inlined, not linked


def test_partial_file_with_a_truncated_line_still_loads(tmp_path):
    """The harness writes incrementally; a half-written last line must not stop the report."""
    path = write(tmp_path, [episode("A1-srun-loop", "doc-absent_skills-none", 0, prevented=True)])
    with path.open("a") as handle:
        handle.write('{"case": "A2-poll-storm", "condi')
    episodes, notes = report_html.load([str(path)])
    assert len(episodes) == 1
    assert notes and "skipped" in notes[0]

    page = report_html.build_page(episodes, "t", [path.name], notes)
    assert "partial" in page.lower()


def test_both_themes_are_declared_under_both_scopes(tmp_path, unstable_run):
    """The OS setting and the page's own toggle must each be able to win."""
    page = render(tmp_path, unstable_run)
    assert "prefers-color-scheme: dark" in page
    assert ':root[data-theme="dark"]' in page
    assert ':root:where(:not([data-theme="light"]))' in page


def test_all_four_conditions_appear_even_when_not_run(tmp_path):
    """A hole in the 2x2 is a fact about the run; hiding the column would hide it."""
    records = [episode("A1-srun-loop", "doc-present_skills-good", 0, prevented=True)]
    page = render(tmp_path, records)
    for label in report.CONDITION_ORDER:
        assert label in page
    assert "not run" in page


def test_nothing_submitted_is_surfaced_not_folded_in(tmp_path):
    """An episode that prevents the defect by doing no work must not read as a clean pass."""
    records = [
        episode(
            "B3-login-node-compute", "doc-present_skills-good", s,
            prevented=True, submitted=False,
        )
        for s in range(3)
    ]
    page = render(tmp_path, records)
    assert "nothing ran" in page
    assert "3/3" in page  # still counted by the endpoint...
    assert "refusing to do the work" in page  # ...and still called out in the limits section


def test_case_metadata_is_read_from_case_yaml(tmp_path):
    """The injected defect is what makes the page more than a table of verdicts."""
    records = [episode("A1-srun-loop", "doc-absent_skills-none", 0, prevented=False)]
    page = render(tmp_path, records)
    assert "injected defect" in page.lower()
    assert "job array" in page.lower()  # from A1's own case.yaml


def test_withdrawn_stratification_is_not_reintroduced(tmp_path, unstable_run):
    """Splitting outcomes by whether the scheduler pushed back is a between-case comparison
    confounded with case difficulty. It was withdrawn; the page must not resurrect it."""
    page = render(tmp_path, unstable_run)
    assert "Was the agent pushed back on" not in page
    assert "withdrawn" in page  # and says so where rejections are shown


def test_labels_are_escaped(tmp_path):
    """Case ids and judge text reach the page from files; they are data, not markup."""
    records = [episode("<script>alert(1)</script>", "doc-absent_skills-none", 0, prevented=False)]
    page = render(tmp_path, records)
    assert "<script>alert(1)</script>" not in page.replace(report_html.JS, "")
    assert "&lt;script&gt;" in page


def test_wilson_and_fisher_are_computed_not_asserted():
    low, high = report_html.wilson(13, 45)
    assert 0.0 < low < 13 / 45 < high < 1.0
    # Reproduces the value recorded in docs/first-run-results.md for 13/45 vs 19/44.
    assert round(report_html.fisher_two_sided(13, 32, 19, 25), 2) == 0.19
    assert report_html.fisher_two_sided(0, 0, 0, 0) == 1.0


def test_grid_numbers_match_report_py(tmp_path, unstable_run):
    """The two reports share `endpoint_of`/`cell_marks`; this pins that they still agree."""
    text = report.report(unstable_run)
    page = render(tmp_path, unstable_run)
    for case, condition in {(e["case"], e["condition"]["label"]) for e in unstable_run}:
        group = [
            e for e in unstable_run
            if e["case"] == case and e["condition"]["label"] == condition
        ]
        stats = report_html.cell_stats(group)
        fraction = f"{stats['passed']}/{stats['n_scored']}"
        assert fraction in text, f"{fraction} missing from report.py output"
        assert fraction in page, f"{fraction} missing from the HTML"
        assert stats["unstable"] == (f"{fraction} UNSTABLE" in text)


def test_cli_writes_a_file(tmp_path, unstable_run):
    path = write(tmp_path, unstable_run)
    out = tmp_path / "report.html"
    result = subprocess.run(
        [sys.executable, "-m", "hpcbench.harness.report_html", str(path), "--out", str(out),
         "--title", "CLI check"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
    body = out.read_text()
    assert "CLI check" in body
    assert body.startswith("<!doctype html>")
