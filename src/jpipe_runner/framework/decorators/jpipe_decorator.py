import ast
import inspect
import textwrap
from functools import wraps
from typing import Callable, List, Optional, Any

from jpipe_runner.framework.context import ctx, RuntimeContext
from jpipe_runner.framework.logger import GLOBAL_LOGGER


def jpipe(consume: Optional[List[str]] = None, produce: Optional[List[str]] = None) -> Callable:
    """
    Unified decorator to declare variables a function consumes and/or produces from/to the pipeline context.

    :param consume: List of variable names to consume.
    :param produce: List of variable names to produce.
    :return: A function decorator.
    """
    consume = consume or []
    produce = produce or []

    def decorator(func: Callable) -> Callable:
        consume_checker = _init_checker(ConsumedVariableChecker, func, consume)
        produce_checker = _init_checker(ProducedVariableChecker, func, produce)

        @wraps(func)
        def wrapper(*args, **kwargs):
            if consume_checker:
                kwargs = consume_checker.inject_arguments(kwargs)
            if produce_checker:
                kwargs['produce'] = produce_checker.produce

            result = func(*args, **kwargs)

            if produce_checker:
                produce_checker.validate_produced()

            return result

        return wrapper

    return decorator

def _init_checker(CheckerClass, func: Callable, params: List[str]):
    if not params:
        return None
    checker = CheckerClass(func, params)
    checker.register_variables()
    return checker

class ConsumedVariableChecker:
    """
    Validates and manages variables declared as consumed by a function.

    Responsibilities:
    - Registers consumed variables in the pipeline context.
    - Checks that declared variables are actually used in the function.
    - Injects values from the context into the function call.

    Raises:
        ValueError: If a required variable is missing in context at runtime.
    """

    def __init__(self, func: Callable, declared_params: tuple[str, ...]):
        """
        Initialize the checker.

        :param func: The function to analyze and wrap.
        :param declared_params: A tuple of variable names the function consumes.
        """
        self.func = func
        self.func_name = func.__name__
        self.declared_params = declared_params
        GLOBAL_LOGGER.debug(f"[{self.func_name}] Initializing ConsumedVariableChecker with: {self.declared_params}")
        self.used_params = self._get_used_variables()

    def register_variables(self):
        """
        Registers declared variables as consumed in the global context (`ctx`).
        """
        GLOBAL_LOGGER.info(f"[{self.func_name}] Registering consumed variables: {self.declared_params}")
        for param in self.declared_params:
            if not ctx.has(self.func, param):
                ctx._set(self.func_name, param, None, RuntimeContext.CONSUME)
                GLOBAL_LOGGER.debug(f"[{self.func_name}] Variable '{param}' registered as CONSUME")

    def inject_arguments(self, kwargs: dict) -> dict:
        """
        Injects variable values from the context into the function’s keyword arguments.

        :param kwargs: Existing keyword arguments to the function.
        :return: Updated keyword arguments with consumed context values added.
        :raises ValueError: If a declared variable is missing from the context.
        """
        for param in self.declared_params:
            if param not in self.used_params:
                GLOBAL_LOGGER.warning(
                    f"Consumed variable '{param}' is declared but not used in function '{self.func_name}'."
                )
            value = ctx.get(param)
            GLOBAL_LOGGER.debug(f"[{self.func_name}] Injecting consumed variable '{param}' = {value}")
            if value is None:
                GLOBAL_LOGGER.error(
                    f"Consumed variable '{param}' has not been set in context before calling '{self.func_name}'."
                )
            kwargs[param] = value
        return kwargs

    def _get_used_variables(self) -> set:
        """
        Extracts all variable names used inside the body of the given function using AST parsing.

        This utility is used to validate that variables declared in the @Consume decorator are
        actually referenced in the function source code.

        :return: A set of variable names used in the function body.
        :rtype: set
        """
        source = inspect.getsource(self.func)
        source = textwrap.dedent(source)
        tree = ast.parse(source)

        class VarVisitor(ast.NodeVisitor):
            def __init__(self):
                self.used_vars = set()

            def visit_Name(self, node):
                self.used_vars.add(node.id)

        visitor = VarVisitor()
        visitor.visit(tree)
        GLOBAL_LOGGER.debug(f"[{self.func_name}] AST detected used variables: {visitor.used_vars}")
        return visitor.used_vars


class ProducedVariableChecker:
    """
    Validates and manages variables declared as produced by a function.

    Responsibilities:
    - Registers produced variables in the global context.
    - Provides a produce() method for the function to set variable values.
    - Validates that all declared variables are actually produced.

    Raises:
        RuntimeError: If undeclared variables are produced, or declared ones are not.
    """

    def __init__(self, func: Callable, declared_params: tuple[str, ...]):
        """
        Initialize the checker.

        :param func: The function to analyze and wrap.
        :param declared_params: A tuple of variable names the function is expected to produce.
        """
        self.func = func
        self.func_name = func.__name__
        self.declared_params = set(declared_params)
        self.produced_set = set()
        GLOBAL_LOGGER.debug(f"[{self.func_name}] Initializing ProducedVariableChecker with: {self.declared_params}")

    def register_variables(self):
        """
        Registers declared variables as produced in the global context (`ctx`).
        """
        GLOBAL_LOGGER.info(f"[{self.func_name}] Registering produced variables: {self.declared_params}")
        for param in self.declared_params:
            if not ctx.has(self.func, param):
                ctx._set(self.func_name, param, None, RuntimeContext.PRODUCE)
                GLOBAL_LOGGER.debug(f"[{self.func_name}] Variable '{param}' registered as PRODUCE")

    def produce(self, param: str, value: Any):
        """
        Produces a variable by setting it in the context.

        :param param: The name of the variable being produced.
        :param value: The value to assign to the variable in the context.
        :raises RuntimeError: If the variable was not declared as produced.
        """
        if param not in self.declared_params:
            GLOBAL_LOGGER.error(
                f"Function '{self.func_name}' attempted to produce undeclared variable '{param}'. "
                f"Expected one of: {self.declared_params}"
            )
        self.produced_set.add(param)
        ctx.set(param, value)
        GLOBAL_LOGGER.info(f"[{self.func_name}] Produced variable '{param}' with value: {value}")

    def validate_produced(self):
        """
        Ensures all declared variables were actually produced during execution.

        :raises RuntimeError: If any declared variable was not produced.
        """
        missing = self.declared_params - self.produced_set
        if missing:
            GLOBAL_LOGGER.error(
                f"Function '{self.func_name}' did not produce the following declared variable(s): {missing}"
            )
        GLOBAL_LOGGER.debug(f"[{self.func_name}] All declared produced variables were set: {self.produced_set}")
