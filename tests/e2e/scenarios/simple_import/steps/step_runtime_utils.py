"""A helper module in the `steps` package, imported only inside a step.

Nothing imports it at load time, so the import in the step succeeds only if the
--python-path entry is still on `sys.path` while the steps run.
"""


def get_step_number_d() -> int:
    """Number d, imported inside a step, at run time."""
    return 2
