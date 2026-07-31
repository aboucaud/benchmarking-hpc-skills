"""Bounded workload files for monitored Docker Slurm sessions."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
QUALIFICATION = FIXTURES / "qualification"


def _read_tree(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def agent_fixture_files(case_id: str) -> dict[str, bytes]:
    """Return neutral, laptop-bounded replacements visible in an episode."""
    return _read_tree(FIXTURES / case_id)


def qualification_fixture_files(case_id: str) -> dict[str, bytes]:
    """Return support files used only for scripted reference qualification."""
    return _read_tree(QUALIFICATION / case_id)
