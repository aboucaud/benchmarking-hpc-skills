#!/usr/bin/env python3
"""Tests for the results landing-page generator.

    uv run --with pyyaml --with pytest pytest tests/test_report_index.py -q

The landing page is what GitHub Pages serves in front of the reports, so its failures are the
quiet kind — the page still renders and still looks finished:

  - `test_card_links_resolve_to_existing_files` — a card that links to a file that is not there is
    a dead link that looks alive. Every href the page emits must resolve to a report on disk.
  - `test_index_excludes_itself` — the generator writes `index.html` into the same directory it
    scans; if it listed itself, every rebuild would add a card pointing at the page you are on.
  - `test_empty_and_missing_dir_render_a_placeholder` — an empty grid reads as "no results". The
    empty/missing case must say so in words instead.
  - `test_report_without_provenance_is_still_listed` — chips are best-effort; a report the parser
    cannot read the provenance of must still get a card, or a markup change silently drops results.
  - `test_title_is_escaped` — report titles are data. One unescaped `<` turns a title into markup.
  - `test_no_external_resource_references` — "self-contained" is a promise about a file opened
    offline; one external stylesheet or script breaks it and nothing looks different locally.
"""

from __future__ import annotations

import re
from pathlib import Path

from hpcbench.harness import report_index


def _write_report(directory: Path, name: str, title: str, provenance: dict | None = None) -> Path:
    """A minimal report file: a <title> and, optionally, the provenance band the parser reads."""
    band = ""
    if provenance:
        band = "".join(
            f'<dt>{label}</dt><dd>{value} <span class="unit">note</span></dd>'
            for label, value in provenance.items()
        )
    path = directory / name
    path.write_text(
        f"<!doctype html><html><head><title>{title}</title></head>"
        f"<body>{band}</body></html>",
        encoding="utf-8",
    )
    return path


def test_report_title_becomes_a_card_linking_the_file(tmp_path):
    _write_report(tmp_path, "run-a.html", "Run A — 30 episodes")

    page = report_index.render_index(tmp_path)

    assert "Run A — 30 episodes" in page
    assert 'href="./run-a.html"' in page


def test_provenance_chips_are_lifted_when_present(tmp_path):
    _write_report(
        tmp_path,
        "run.html",
        "Run",
        provenance={"Episodes": "90", "Subject model": "sonnet", "Judge": "opus"},
    )

    page = report_index.render_index(tmp_path)

    for value in ("90", "sonnet", "opus"):
        assert value in page


def test_report_without_provenance_is_still_listed(tmp_path):
    # No provenance band at all — the card must still appear, just without chips.
    _write_report(tmp_path, "bare.html", "Bare report")

    reports = report_index.discover_reports(tmp_path)

    assert [r.filename for r in reports] == ["bare.html"]
    assert reports[0].chips == []


def test_episode_total_sums_every_report(tmp_path):
    _write_report(tmp_path, "a.html", "A", provenance={"Episodes": "108"})
    _write_report(tmp_path, "b.html", "B", provenance={"Episodes": "90"})

    assert report_index._episode_total(report_index.discover_reports(tmp_path)) == 198


def test_episode_total_is_withheld_when_a_report_cannot_be_read(tmp_path):
    # A partial sum reads as a complete one, and contradicts the cards below it. Better to show
    # no total than a total that quietly omits a run.
    _write_report(tmp_path, "a.html", "A", provenance={"Episodes": "108"})
    _write_report(tmp_path, "b.html", "B")

    reports = report_index.discover_reports(tmp_path)

    assert report_index._episode_total(reports) is None
    assert "episodes published" not in report_index.render_index(tmp_path)


def test_index_excludes_itself(tmp_path):
    _write_report(tmp_path, "real.html", "A real report")
    (tmp_path / "index.html").write_text("<title>stale index</title>", encoding="utf-8")

    reports = report_index.discover_reports(tmp_path)

    assert [r.filename for r in reports] == ["real.html"]


def test_reports_are_sorted_by_filename(tmp_path):
    _write_report(tmp_path, "c.html", "C")
    _write_report(tmp_path, "a.html", "A")
    _write_report(tmp_path, "b.html", "B")

    reports = report_index.discover_reports(tmp_path)

    assert [r.filename for r in reports] == ["a.html", "b.html", "c.html"]


def test_card_links_resolve_to_existing_files(tmp_path):
    _write_report(tmp_path, "run-a.html", "A")
    _write_report(tmp_path, "run-b.html", "B")

    page = report_index.render_index(tmp_path)

    hrefs = re.findall(r'class="card" href="\./([^"]+)"', page)
    assert hrefs, "no report cards were emitted"
    for href in hrefs:
        assert (tmp_path / href).exists(), f"card links a missing file: {href}"


def test_empty_and_missing_dir_render_a_placeholder(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    missing = tmp_path / "does-not-exist"

    for reports_dir in (empty, missing):
        page = report_index.render_index(reports_dir)
        assert "<title>" in page  # still a valid page
        assert 'class="card"' not in page  # no report cards
        assert "No reports" in page  # says so in words


def test_title_is_safe_in_output(tmp_path):
    # An ampersand, entity-encoded as a real report would write it, round-trips escaped.
    _write_report(tmp_path, "amp.html", "Doc &amp; skills")
    # A stray literal tag in a title must never reach the output as a live tag.
    _write_report(tmp_path, "inj.html", "<script>alert(1)</script>Run")

    page = report_index.render_index(tmp_path)

    assert "Doc &amp; skills" in page
    assert "<script>alert(1)</script>Run" not in page
    # The theme toggle is the only <script> on the page; no title injected another.
    assert page.count("<script>") == 1


def test_no_external_resource_references(tmp_path):
    _write_report(tmp_path, "run.html", "Run")

    page = report_index.render_index(tmp_path)
    # `xmlns="http://www.w3.org/2000/svg"` is an XML namespace name, never fetched. Drop it before
    # checking, so the check below stays a literal "no plaintext URLs" rule.
    page_without_namespaces = page.replace('xmlns="http://www.w3.org/2000/svg"', "")

    assert "<script src" not in page
    assert "<link " not in page
    assert "@import" not in page
    assert "http://" not in page_without_namespaces
    # Every absolute URL is an outbound link to a declared destination — never a fetched
    # resource. An undeclared host is how a self-contained page starts depending on a CDN.
    for url in re.findall(r'href="(https://[^"]+)"', page):
        assert url.startswith(report_index.EXTERNAL_LINK_PREFIXES), f"undeclared link: {url}"
    # Nothing outside an href may carry a URL either, except the repo URL shown as link text.
    remainder = re.sub(r'href="https://[^"]+"', "", page).replace(report_index.REPO_URL, "")
    assert "https://" not in remainder


def test_write_command_creates_output(tmp_path):
    reports = tmp_path / "docs" / "reports"
    reports.mkdir(parents=True)
    _write_report(reports, "run.html", "Run")
    out = tmp_path / "site" / "index.html"

    import sys

    argv = sys.argv
    sys.argv = ["report_index", "write", "--reports", str(reports), "--out", str(out)]
    try:
        assert report_index.main() == 0
    finally:
        sys.argv = argv

    assert out.exists()
    assert 'href="./run.html"' in out.read_text(encoding="utf-8")
