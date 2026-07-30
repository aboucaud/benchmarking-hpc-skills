"""Docker-backed Slurm benchmark substrate.

This package deliberately lives beside, rather than inside, the existing
benchmark harness.  It imports the benchmark's public data and detectors but
does not require changes to the stub substrate.
"""

from .episode import Condition, DockerEpisode
from .runner import CodexExecRunner, RunResult
from .substrate import DockerSlurmSubstrate

__all__ = [
    "CodexExecRunner",
    "Condition",
    "DockerEpisode",
    "DockerSlurmSubstrate",
    "RunResult",
]
