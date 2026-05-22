"""
jpipe_runner.utils.syspath
~~~~~~~~~~~~~~~~~~~~~~~~~~

Temporary sys.path manipulation.
"""

import sys
from contextlib import contextmanager
from typing import Iterable


@contextmanager
def path_context(additional_paths: Iterable[str]):
    """
    Temporarily add paths to sys.path

    The paths are inserted at the beginning of sys.path, in the order of `additional_paths`.
    Any path already present in sys.path is ignored.
    Duplicates within `additional_paths` are not added.

    After the context block exits, sys.path is restored to its original state.

    :param additional_paths: Iterable of paths to add to sys.path
    :type additional_paths: Iterable[str]
    """
    original_path = sys.path.copy()
    new_paths = []
    seen = set()
    for path in additional_paths:
        if path not in sys.path and path not in seen:
            seen.add(path)
            new_paths.append(path)

    sys.path[0:0] = new_paths

    try:
        yield
    finally:
        sys.path[:] = original_path
