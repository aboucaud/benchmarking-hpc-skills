"""Harness for benchmarking whether HPC skills make coding agents better cluster citizens.

Layout, as it actually stands:

- ``hpcbench.paths``             where the data half of the repo lives
- ``hpcbench.render``            center.yaml -> INSTRUCTIONS.md, detector limits, cluster config
- ``hpcbench.validate_cases``    coherence check over the case set
- ``hpcbench.stubs``             echo-stub Slurm commands; nothing they answer reaches a scheduler
- ``hpcbench.harness``           episode orchestration, L1 detectors, L2/L3 judge, reporting

The data — ``benchmark/center.yaml``, ``benchmark/cases/``, ``benchmark/generated/`` — is
deliberately not part of this package. See ``hpcbench.paths``.

Nothing here talks to a real cluster. See CLAUDE.md.
"""

__version__ = "0.0.1"
