import ast
import inspect
import textwrap
from functools import wraps
from typing import Callable, Any

from .context import RuntimeContext, ctx
from .logger import GLOBAL_LOGGER


def Consume(*params: str) -> Callable:
    """
    Decorator that declares context variables consumed by a function.

    This decorator performs the following:
    1. Registers the consumed variable names in the global context (`ctx`) under the function's name.
    2. Ensures all declared consumed variables are actually used in the function body (via AST analysis).
    3. Injects the consumed variable values as keyword arguments from the context at call time.

    If any declared variable:
    - is not found in the function body → a RuntimeError is raised.
    - is missing from the context (`ctx`) at runtime → a ValueError is raised.

    Example:
        @Consume('config_path', 'model_id')
        def load_model(config_path, model_id):
            ...

    :param params: One or more names of context variables the function consumes.
    :type params: str
    :return: The decorated function with context-injected arguments.
    :rtype: Callable[[Callable], Callable]
    """

    def decorator(func: Callable) -> Callable:
        GLOBAL_LOGGER.debug(f"Registering consumed variables {params} for function '{func.__name__}'")
        func_name = func.__name__
        used_params = _get_used_variables(func)

        for param in params:
            if not ctx.has(func, param):
                ctx._set(func_name, param, None, RuntimeContext.CONSUME)

        @wraps(func)
        def wrapper(*args, **kwargs):
            for param in params:
                if param not in used_params:
                    GLOBAL_LOGGER.warning(
                        f"Consumed variable '{param}' is declared but not used in function '{func_name}'."
                    )
                value = ctx.get(param)
                if value is None:
                    raise ValueError(
                        f"Consumed variable '{param}' has not been set in context before calling '{func_name}'."
                    )
                kwargs[param] = value
            return func(*args, **kwargs)

        return wrapper

    return decorator


def Produce(*params: str) -> Callable:
    """
    Decorator that declares context variables produced by a function.

    This decorator performs the following:
    1. Registers the produced variable names in the global context (`ctx`) under the function's name.
    2. Injects a `produce(param: str, value: Any)` function into the decorated function's arguments.
    3. Ensures all declared variables are explicitly produced at runtime using the injected function.

    If the function:
    - attempts to produce a variable not listed in `params` → a RuntimeError is raised.
    - fails to produce one or more declared variables → a RuntimeError is raised after execution.

    Example:
        @Produce('model')
        def train_model(produce):
            model = ...  # train logic
            produce('model', model)

    :param params: One or more names of context variables the function produces.
    :type params: str
    :return: The decorated function with a `produce()` function injected.
    :rtype: Callable[[Callable], Callable]
    """

    def decorator(func: Callable) -> Callable:
        func_name = func.__name__
        for param in params:
            if not ctx.has(func, param):
                ctx._set(func_name, param, None, RuntimeContext.PRODUCE)

        @wraps(func)
        def wrapper(*args, **kwargs):
            produced_set = set()

            def inner_produce(param: str, value: Any):
                if param not in params:
                    raise RuntimeError(
                        f"Function '{func_name}' attempted to produce undeclared variable '{param}'. "
                        f"Expected one of: {params}"
                    )
                produced_set.add(param)
                ctx.set(param, value)

            kwargs['produce'] = inner_produce
            result = func(*args, **kwargs)

            missing = set(params) - produced_set
            if missing:
                raise RuntimeError(
                    f"Function '{func_name}' did not produce the following declared variable(s): {missing}"
                )

            return result

        return wrapper

    return decorator


def _get_used_variables(func: Callable) -> set:
    """
    Extracts all variable names used inside the body of the given function using AST parsing.

    This utility is used to validate that variables declared in the @Consume decorator are
    actually referenced in the function source code.

    :param func: The function to analyze.
    :type func: Callable
    :return: A set of variable names used in the function body.
    :rtype: set
    """
    source = inspect.getsource(func)
    source = textwrap.dedent(source)
    tree = ast.parse(source)

    class VarVisitor(ast.NodeVisitor):
        def __init__(self):
            self.used_vars = set()

        def visit_Name(self, node):
            self.used_vars.add(node.id)

    visitor = VarVisitor()
    visitor.visit(tree)
    return visitor.used_vars
