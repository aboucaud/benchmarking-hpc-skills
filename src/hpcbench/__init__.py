"""Harness for benchmarking HPC skills against a simulated cluster.

Layout, as it lands across the PR sequence in issue #1:

- ``hpcbench.center``    center descriptor: one YAML generating INSTRUCTIONS.md,
                         the simulator config, and the detector limits
- ``hpcbench.simslurm``  time-accelerated Slurm shims and call log
- ``hpcbench.detect``    violation detectors (controller load, filesystem, queue misuse)
- ``hpcbench.harness``   episode runner
- ``hpcbench.metrics``   scoring
- ``hpcbench.project``   campaign projection

Nothing here talks to a real cluster. See CLAUDE.md.
"""

__version__ = "0.0.1"
