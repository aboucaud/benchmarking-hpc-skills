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

import pytest

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


def test_diagram_assets_are_inlined(tmp_path):
    # Referenced with <img> they would neither work offline nor see the page's palette variables,
    # so they would keep their light-mode colours in dark mode. Inlined is the contract.
    page = report_index.render_index(tmp_path)

    for name in ("substrate-stubs.svg", "substrate-docker.svg"):
        assert (report_index.ASSETS / name).is_file(), f"missing asset: {name}"
        assert name not in page, f"{name} is referenced rather than inlined"
    assert "Shims on $PATH" in page
    assert "Site client gateway" in page
    # The authoring comment explains the file to an editor, not to a reader of the page.
    assert "Inlined into the landing page" not in page


def test_a_missing_diagram_asset_is_loud(tmp_path, monkeypatch):
    # A diagram that silently vanishes on deploy is exactly the failure this page is written to
    # avoid, so an absent asset must stop the build rather than render an empty figure.
    monkeypatch.setattr(report_index, "ASSETS", tmp_path / "nowhere")

    with pytest.raises(FileNotFoundError):
        report_index.render_index(tmp_path)


def test_svg_element_ids_are_unique_across_inlined_diagrams(tmp_path):
    # Every diagram is inlined into one document, so they share an id space. Two `<marker id="ar">`
    # means one diagram's arrowheads silently render with the other's definition.
    page = report_index.render_index(tmp_path)

    ids = re.findall(r'<(?:marker|linearGradient|clipPath|filter)\b[^>]*\bid="([^"]+)"', page)
    assert ids, "no SVG defs found — has the diagram markup changed?"
    assert len(ids) == len(set(ids)), f"duplicate SVG ids: {ids}"


def _write_document(root: Path, path: str, body: str) -> None:
    full = root / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body, encoding="utf-8")


def test_documents_are_shown_verbatim(tmp_path):
    # The section exists to show the reader the actual file, so it must not be paraphrased,
    # truncated, or rendered from markdown into something the agent never saw.
    root = tmp_path / "repo"
    _write_document(root, "benchmark/generated/INSTRUCTIONS.md", "# SCC\n\n- never poll <fast>\n")

    page = report_index.render_index(tmp_path, repo_root=root)

    assert "# SCC" in page
    # Document text is data: one stray angle bracket must not become markup.
    assert "- never poll &lt;fast&gt;" in page
    assert "<fast>" not in page


def test_both_documents_get_their_own_pane(tmp_path):
    root = tmp_path / "repo"
    _write_document(root, "benchmark/generated/INSTRUCTIONS.md", "GENERATED DOC")
    _write_document(root, "agents/INSTRUCTIONS.md", "AGENTS DOC")

    page = report_index.render_index(tmp_path, repo_root=root)

    assert "GENERATED DOC" in page and "AGENTS DOC" in page
    assert page.count('type="radio"') == 2
    # Exactly one pane starts visible, or the panes stack on top of each other on first paint.
    assert page.count(" checked>") == 1


def test_document_section_and_its_nav_entry_are_dropped_together(tmp_path):
    # A nav link to a section that was never rendered is a link to nowhere.
    page = report_index.render_index(tmp_path, repo_root=tmp_path / "empty")

    assert 'id="document"' not in page
    assert 'href="#document"' not in page


def test_document_tabs_need_no_script(tmp_path):
    # The page ships exactly one <script>, for the theme toggle. A viewer for a static file does
    # not justify a second one, and the CSS-only tabs must keep it that way.
    root = tmp_path / "repo"
    _write_document(root, "benchmark/generated/INSTRUCTIONS.md", "doc")
    _write_document(root, "agents/INSTRUCTIONS.md", "doc")

    page = report_index.render_index(tmp_path, repo_root=root)

    assert page.count("<script>") == 1


def test_no_external_resource_references(tmp_path):
    _write_report(tmp_path, "run.html", "Run")
    # A real document carries the facility's (fake) support URL. Quoted inside the page it is
    # inert text, but it must not be mistaken for a resource reference by the check below.
    root = tmp_path / "repo"
    _write_document(
        root, "benchmark/generated/INSTRUCTIONS.md", "Docs: https://scc.example.invalid/docs\n"
    )

    page = report_index.render_index(tmp_path, repo_root=root)
    assert "scc.example.invalid" in page, "the document was not included in this check"
    # `xmlns="http://www.w3.org/2000/svg"` is an XML namespace name, never fetched, and a URL
    # inside a <pre> is quoted document text. Neither is a resource this page loads. Drop both, so
    # the check below stays a literal "no plaintext URLs" rule over the page's own markup.
    markup = re.sub(r"<pre\b.*?</pre>", "", page, flags=re.DOTALL).replace(
        'xmlns="http://www.w3.org/2000/svg"', ""
    )

    assert "<script src" not in markup
    assert "<link " not in markup
    assert "@import" not in markup
    assert "http://" not in markup
    # Every absolute URL is an outbound link to a declared destination — never a fetched
    # resource. An undeclared host is how a self-contained page starts depending on a CDN.
    for url in re.findall(r'href="(https://[^"]+)"', markup):
        assert url.startswith(report_index.EXTERNAL_LINK_PREFIXES), f"undeclared link: {url}"
    # Nothing outside an href may carry a URL either, except the repo URL shown as link text.
    remainder = re.sub(r'href="https://[^"]+"', "", markup).replace(report_index.REPO_URL, "")
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
