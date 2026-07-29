"""Smoke test: the package imports and the toolchain is wired up.

Replaced by real tests as the components in issue #1 land.
"""

import hpcbench


def test_package_imports_and_reports_a_version():
    assert hpcbench.__version__
