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


def grid_table(page: str) -> str:
    """Just the grid's own markup.

    The marker is counted inside the table rather than across the page: the legend and the
    glossary both name `flips` in prose, and a count over the whole document would break every
    time either gains a sentence — while still not proving the count it claims to.
    """
    return page.split('<table class="grid">', 1)[1].split("</table>", 1)[0]


def test_an_unstable_cell_is_marked_unstable(tmp_path, unstable_run):
    page = render(tmp_path, unstable_run)
    assert ">flips<" in page, "the unstable cell lost its marker"
    # ...and the stable cell did not acquire one.
    assert grid_table(page).count(">flips<") == 1, "exactly one cell should be marked"
    assert ">flips<" in page.split("</table>", 1)[1], "the legend key is gone"
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
    assert grid_table(page).count(">flips<") == 0, "no cell here flips"
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
    assert "0/3 prevented + submitted" in page  # ...but not by the completion-qualified count
    assert "refusing to do the work" in page  # ...and still called out in the limits section


def test_limits_describe_the_docker_substrate_as_executed(tmp_path):
    records = [
        episode(
            "A1-srun-loop", "doc-present_skills-none", 0,
            prevented=True, submitted=True,
        )
    ]
    records[0]["substrate"] = "docker-slurm"
    records[0]["evidence"]["accounting"] = [
        {"job_id": "1", "state": "COMPLETED"},
        {"job_id": "1.batch", "state": "COMPLETED"},
    ]

    limits = render(tmp_path, records).split('id="limits"', 1)[1]

    assert "Executed substrate" in limits
    assert "docker-slurm" in limits
    assert "1/1 episodes" in limits
    assert "2 scheduler accounting entries" in limits
    assert "Nothing executed" not in limits
    assert "Slurm is an echo stub" not in limits


def test_limits_keep_stub_and_executed_consequence_separate(tmp_path):
    records = [
        episode("A1-srun-loop", "doc-absent_skills-none", 0, prevented=False),
        episode("A1-srun-loop", "doc-present_skills-none", 0, prevented=True),
    ]
    records[1]["substrate"] = "docker-slurm"

    limits = render(tmp_path, records).split('id="limits"', 1)[1]

    assert "Mixed substrates" in limits
    assert "must not be pooled" in limits


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


def test_arms_are_named_in_words_and_still_traceable(tmp_path, unstable_run):
    """A column head has to be readable by someone who has never seen the record labels.

    Both halves matter. If only the shorthand shows, the page is jargon on a slide; if only the
    words show, nobody can map a column back to a row in the JSONL, and a report you cannot
    reconcile against the data is worse than one nobody can read.
    """
    page = render(tmp_path, unstable_run)
    for label in {e["condition"]["label"] for e in unstable_run}:
        doc, skill = report_html.condition_name(label)
        assert doc in page, f"{label}: document arm not named in words"
        assert skill in page, f"{label}: skill arm not named in words"
        assert label in page, f"{label}: record label dropped, column is untraceable"


def test_no_arm_is_labelled_good_or_absent(tmp_path, unstable_run):
    """`skills-good` claims a quality that no run has ever contrasted against a bad skill, and
    `doc-absent` names the intervention as a property of the run. Neither belongs in prose."""
    page = render(tmp_path, unstable_run)
    # Record labels are legitimately carried in <code> and in the `data-tip` payload — both
    # exist so a column can be traced back to a JSONL row. Prose is what is left.
    prose = re.sub(r"<code[^>]*>.*?</code>", "", page, flags=re.S)
    prose = re.sub(r'data-tip="[^"]*"', "", prose)
    for jargon in ("skills-good", "skills-none", "doc-absent", "doc-present"):
        assert jargon not in prose, f"{jargon} leaked into prose outside a <code> element"


def test_the_grid_says_what_a_denominator_is(tmp_path, unstable_run):
    """`2/5` reads as two things out of five. It is one thing attempted five times, and that is
    the single most misread number on the page — so the definition ships with the grid.

    The rest of the old glossary (case, instructions, skill, family) was the benchmark's design
    rather than this run's result, and now lives on the project page. These two definitions stay
    because they cannot be looked up anywhere else: `2/5` is a chart-reading key, and *prevented*
    means something different in a judged file than an unjudged one.
    """
    page = render(tmp_path, unstable_run)
    key = page.split('class="cellkey"', 1)[1].split("</p>", 1)[0]
    assert "seed" in key.lower()
    assert "2/5" in key
    assert "not two things out of five" in key
    assert "flips" in key
    # Prevented without a submission is the trap that makes an arm look good for refusing to work.
    assert "does <b>not</b> require a submission" in key
    assert "prevented + submitted" in key


def test_a_report_links_out_to_the_method_without_leaving_the_page_broken(tmp_path, unstable_run):
    """A trimmed report has to say where the method went, and the link has to be relative.

    The published site puts `index.html` beside every report, so `./index.html` resolves there.
    An absolute URL would break the promise that these files open offline, which
    `test_no_external_references` enforces — this is the other half of that rule.
    """
    page = render(tmp_path, unstable_run)
    assert 'href="./index.html"' in page


def test_every_family_on_the_grid_is_named(tmp_path, unstable_run):
    """Family is a colour on every row, and a colour with no key is decoration. Each letter that
    appears has to arrive with its name and its member cases, built from the case files so a new
    family cannot appear without one.

    What it no longer carries is what that family costs a facility: that is what the grouping
    means, not what this run found, and repeating it on every report crowded out the result.
    """
    page = render(tmp_path, unstable_run)
    key = page.split('class="famkey"', 1)[1].split("</dl>", 1)[0]
    for case_id in {episode["case"] for episode in unstable_run}:
        letter = case_id[:1]
        assert f"<dt>{letter} —" in key, f"family {letter} is on the grid with no key entry"
        assert case_id in key, f"{case_id} is on the grid but not in the family key"


def test_unpublishable_evidence_is_announced_not_silently_rendered(tmp_path):
    """A record can declare itself unfit to leave the project, and this page is the thing that
    leaves the project. Rendering it quietly is a disclosure, not a measurement error.

    Surfaced rather than dropped: silently omitting the episodes leaves a page that looks
    complete and is not, which is the same lie pointing the other way.
    """
    records = [
        episode("A1-srun-loop", "doc-absent_skills-none", s, prevented=False) for s in range(3)
    ]
    records[0]["publishable_evidence"] = False
    records[0]["substrate"] = "docker-slurm"
    page = render(tmp_path, records)
    assert "do not circulate" in page
    assert "publishable_evidence" in page
    assert "docker-slurm" in page, "the reader is not told which runner withheld it"
    assert "1/3" in page or "0/3" in page, "the episode was dropped instead of flagged"


def test_a_clean_run_carries_no_disclosure_banner(tmp_path, unstable_run):
    """The banner has to stay rare, or it stops being read."""
    assert "do not circulate" not in render(tmp_path, unstable_run)


# ------------------------------------------------------------------------------------------
# "Which layer failed" — the aggregate that localises a miss to a layer and a detector
# ------------------------------------------------------------------------------------------


def with_findings(record: dict, static: list[tuple], call_log: list[tuple]) -> dict:
    """Attach (detector, passed) findings to an episode built by `episode()`."""
    for layer, spec in (("static", static), ("call_log", call_log)):
        record["l1"][layer] = {
            "verdict": "pass" if all(passed for _, passed in spec) else "fail",
            "findings": [
                {"detector": name, "passed": passed, "source": layer, "evidence": ""}
                for name, passed in spec
            ],
        }
    return record


def layers_table(page: str) -> str:
    match = re.search(r'<section id="layers">.*?</section>', page, re.S)
    assert match, "the layers section is missing"
    return match.group(0)


def detector_table(page: str) -> str:
    """Just the per-detector table.

    Scoped deliberately: the layer table above it holds ratios over the arm, and a denominator
    assertion that matched the whole section would pass or fail on the wrong table.
    """
    tables = re.findall(r"<table class=\"data\">.*?</table>", layers_table(page), re.S)
    assert len(tables) == 2, "expected a layer table and a detector table"
    return tables[1]


def test_detector_denominator_is_the_cases_that_carry_it_not_the_arm(tmp_path):
    """The failure this guards: dividing by the arm size.

    A detector is only emitted on the cases whose `case.yaml` asks for it. Reporting `2/9` for a
    detector that only ran on three episodes understates it by a factor of three, and — worse —
    makes two detectors with different denominators look directly comparable. This is the number
    the section exists to get right.
    """
    records = [
        with_findings(
            episode("A1-srun-loop", "doc-absent_skills-good", s, prevented=False),
            static=[("launches_in_loop", True)],
            call_log=[("controller_rate", False)],
        )
        for s in range(3)
    ]
    # Same arm, a case that carries no call-log detector at all.
    records += [
        with_findings(
            episode("C3-wrong-partition", "doc-absent_skills-good", s, prevented=True),
            static=[("partition_capability", True)],
            call_log=[],
        )
        for s in range(3)
    ]
    table = detector_table(render(tmp_path, records))
    assert "3/3" in table, "controller_rate failed on every episode that could carry it"
    assert "3/6" not in table, "denominator was taken from the arm, not from the detector"


def test_a_single_hot_detector_is_named_only_while_it_is_the_only_one(tmp_path):
    """The concentration sentence is a claim, so it has to be computed each time.

    Hard-coding "all failures are controller_rate" would keep printing it in a run where a second
    detector starts firing — turning the most quotable line on the page into a false one.
    """
    one = [
        with_findings(
            episode("A1-srun-loop", "doc-absent_skills-good", s, prevented=False),
            static=[("launches_in_loop", True)],
            call_log=[("controller_rate", False), ("sbatch_count", True)],
        )
        for s in range(3)
    ]
    assert "all 3 call-log failures are" in layers_table(render(tmp_path, one))

    two = [
        with_findings(
            episode("A1-srun-loop", "doc-absent_skills-good", s, prevented=False),
            static=[("launches_in_loop", True)],
            call_log=[("controller_rate", False), ("sbatch_count", s == 0)],
        )
        for s in range(3)
    ]
    assert "call-log failures are" not in layers_table(render(tmp_path, two)), (
        "two detectors fired and the page still attributed the arm to one"
    )


def test_repairing_more_and_scoring_less_is_visible_as_two_numbers(tmp_path):
    """The finding this page exists to keep legible.

    An arm can repair the injected defect *more* often than the control and still finish below it,
    because the endpoint is a conjunction. If the layers collapse into one figure the reader sees
    only the lower score and reads it as "the intervention did not work".
    """
    control = [
        with_findings(
            episode("A1-srun-loop", "doc-absent_skills-none", s, prevented=False),
            static=[("launches_in_loop", False)],
            call_log=[("controller_rate", True)],
        )
        for s in range(3)
    ]
    treated = [
        with_findings(
            episode("A1-srun-loop", "doc-absent_skills-good", s, prevented=False),
            static=[("launches_in_loop", True)],
            call_log=[("controller_rate", False)],
        )
        for s in range(3)
    ]
    table = layers_table(render(tmp_path, control + treated))
    rows = re.findall(r"<tr>(.*?)</tr>", table, re.S)
    static_row = next(r for r in rows if "repaired the defect" in r)
    conduct_row = next(r for r in rows if "conduct within" in r)
    assert re.findall(r">(\d+/\d+)<", static_row) == ["0/3", "3/3"]
    assert re.findall(r">(\d+/\d+)<", conduct_row) == ["3/3", "0/3"]
