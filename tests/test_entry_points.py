#!/usr/bin/env python3
"""Every entry point must run as a script in an environment where nothing is installed.

    uv run --with pyyaml --with pytest pytest tests/test_entry_points.py -q

This file exists because the layout move broke all five bootstraps at once and nothing noticed.
Each entry point starts with

    if __package__ in (None, ""):
        sys.path.insert(0, str(Path(__file__).resolve().parents[N]))

and every N was off by one: they inserted the repository root, which contains no `hpcbench`
package, so the import on the very next line raised. It was invisible in every environment anyone
had tried, because `uv run` leaves an editable install whose `.pth` already puts `src` on the path
and pytest gets `src` from `pythonpath`. The bootstrap was dead code, and "I ran all four entry
points and they worked" was true and meaningless.

So these tests strip both mechanisms — a subprocess with `-E -s`, `PYTHONPATH` cleared, and a cwd
outside the repo — and assert the bootstrap alone carries the import.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

ENTRY_POINTS = (
    "hpcbench/render.py",
    "hpcbench/validate_cases.py",
    "hpcbench/controller_calibration.py",
    "hpcbench/review_packet.py",
    "hpcbench/harness/episode.py",
    "hpcbench/harness/judge.py",
    "hpcbench/stubs/install_stubs.py",
)


def bare_environment(tmp_path: Path) -> dict[str, str]:
    """No PYTHONPATH, and a HOME that cannot supply a user site-packages."""
    environment = {
        key: value for key, value in os.environ.items()
        if key not in ("PYTHONPATH", "PYTHONHOME")
    }
    environment["HOME"] = str(tmp_path)
    return environment


@pytest.mark.parametrize("entry", ENTRY_POINTS)
def test_bootstrap_alone_resolves_the_package(entry, tmp_path):
    """`--help` is enough: argparse only runs after every module-level import has succeeded.

    Skips rather than passes when `hpcbench` is importable from the ambient environment. It very
    often is — `uv run` builds an editable install into the venv it creates — and then this test
    proves nothing about the bootstrap, because the import it is watching would succeed with the
    bootstrap deleted entirely. Mutation-checked: with the off-by-one restored, this test still
    passed and only `test_bootstrap_targets_src_not_the_repo_root` caught it. A test that cannot
    fail should say so out loud rather than contribute a green tick.
    """
    ambient = subprocess.run(
        [sys.executable, "-s", "-c", "import hpcbench"],
        capture_output=True, text=True, cwd=tmp_path, env=bare_environment(tmp_path),
        timeout=60, check=False,
    )
    if ambient.returncode == 0:
        pytest.skip(
            "hpcbench is installed in this interpreter, so a successful import here says nothing "
            "about the bootstrap — test_bootstrap_targets_src_not_the_repo_root is the guard"
        )

    result = subprocess.run(
        [sys.executable, "-s", str(SRC / entry), "--help"],
        capture_output=True, text=True, cwd=tmp_path, env=bare_environment(tmp_path),
        timeout=120, check=False,
    )
    assert "ModuleNotFoundError" not in result.stderr, (
        f"{entry} cannot import its own package when run as a script:\n{result.stderr}"
    )
    assert result.returncode == 0, f"{entry} --help exited {result.returncode}: {result.stderr}"


@pytest.mark.parametrize("entry", ENTRY_POINTS)
def test_bootstrap_targets_src_not_the_repo_root(entry):
    """The arithmetic, checked directly — a second reading of the same fact.

    The subprocess test above is the real one, but it can be satisfied by an ambient install
    sneaking back in. This one cannot: it resolves the index the file actually uses and asserts
    the directory it names contains the package.
    """
    source = (SRC / entry).read_text()
    marker = "sys.path.insert(0, str(Path(__file__).resolve().parents["
    assert marker in source, f"{entry} has no bootstrap"
    index = int(source.split(marker, 1)[1].split("]", 1)[0])
    target = (SRC / entry).resolve().parents[index]
    assert (target / "hpcbench").is_dir(), (
        f"{entry} bootstraps to {target}, which holds no `hpcbench` package"
    )
