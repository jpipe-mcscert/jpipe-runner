from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)


def jpipe_link(element_id: str) -> Callable[[F], F]:
    """
    Decorator to explicitly bind a Python function to a JSON pipeline element by its id.

    This removes the fragile label-to-function-name mapping: instead of requiring
    the function name to match the sanitized form of the JSON label, the decorator
    records the element id directly on the function.

    Compatible with @jpipe, @skip, and @contribution in any stacking order, because
    all three use @wraps which propagates __dict__ attributes to their wrappers.

    :param element_id: The id of the JSON element this function implements (e.g. "E1").
    :type element_id: str

    Example::

        @jpipe_link("E1")
        @jpipe(consume=["file_path"], produce=["file_exists"])
        def check_file(file_path, produce):
            produce("file_exists", os.path.isfile(file_path))
            return True
    """

    def decorator(func: F) -> F:
        func.__jpipe_link_id__ = element_id
        return func

    return decorator
