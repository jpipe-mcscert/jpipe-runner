"""A helper module at the root of the scenario, imported only inside a step.

Nothing imports it at load time, so the import in the step succeeds only if the
--python-path entry is still on `sys.path` while the steps run.
"""


def get_root_number_c() -> int:
    """Number c, imported inside a step, at run time."""
    return 20
