from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)


def jpipe_link(element_id: str) -> Callable[[F], F]:
    """
    Decorator to explicitly bind a Python function to a JSON pipeline element by its id.

    This removes the fragile label-to-function-name mapping: instead of requiring
    the function name to match the sanitized form of the JSON label, the decorator
    records the element id directly on the function.

    The decorator may be stacked multiple times to bind one function to several
    names — all expected to be aliases of the same unified node. Each application
    appends to the ``__jpipe_link_ids__`` list rather than overwriting, so no
    binding is silently lost.

    Compatible with @jpipe, @skip, and @contribution in any stacking order, because
    all three use @wraps which propagates __dict__ attributes to their wrappers.

    :param element_id: The id (or alias) of the JSON element this function implements
        (e.g. "E1" or "rigor:r17:e_metric").
    :type element_id: str

    Example::

        @jpipe_link("rigor:r17:e_metric")
        @jpipe_link("rigor:r18:e")
        @jpipe(consume=["file_path"], produce=["file_exists"])
        def check_file(file_path, produce):
            produce("file_exists", os.path.isfile(file_path))
            return True
    """

    def decorator(func: F) -> F:
        ids = getattr(func, "__jpipe_link_ids__", None)
        if ids is None:
            ids = []
            func.__jpipe_link_ids__ = ids
        ids.append(element_id)
        return func

    return decorator
