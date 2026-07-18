"""
Pipeline for the python_path_test integration test.

This pipeline verifies that the `python_exec_path` action parameter correctly
overrides the Python interpreter used to run jpipe-runner.
"""

import sys

from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


@jpipe_link("E1")
@jpipe(produce=["python_version_ok"])
def check_python_version(produce) -> bool:
    """
    Verify that the Python interpreter is version 3.12.x.
    """
    version = sys.version_info
    python_version_ok = version.major == 3 and version.minor == 12
    produce("python_version_ok", python_version_ok)
    return python_version_ok


@jpipe_link("S1")
@jpipe(consume=["python_version_ok"])
def python_version_is_correct(python_version_ok: bool) -> bool:
    """Strategy — the Python version check must pass for success."""
    return python_version_ok
