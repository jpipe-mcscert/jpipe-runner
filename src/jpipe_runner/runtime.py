"""
jpipe_runner.runtime
~~~~~~~~~~~~~~~~~~~~

This module contains the runtimes that can be used by jPipe Runner.
"""

import importlib.util
import os
from ast import literal_eval
from typing import Any, Iterable, Optional, Tuple

from jpipe_runner.exceptions import RuntimeException
from jpipe_runner.utils import group_github_logs


class PythonRuntime:
    """
    The default lightweight built-in Python runtime for jPipe Runner.

    This runtime supports:
    - Dynamic import of user-specified Python files
    - Calling functions by name
    - Setting variables across loaded modules
    """

    def __init__(self,
                 libraries: Optional[Iterable[str]] = None,
                 variables: Optional[Iterable[Tuple[str, str]]] = None,
                 ):
        """
        Initialize the runtime with optional libraries and variables.

        :param libraries: Paths to Python files to import as modules.
        :type libraries: Optional[Iterable[str]]
        :param variables: Iterable of (name, value) string pairs to set as variables.
        :type variables: Optional[Iterable[Tuple[str, str]]]
        """
        self._modules = []
        self.load_files(libraries or [])

        for k, v in variables or []:
            self.set_variable(k, v)

    def load_files(self, file_paths: Iterable[str]):
        """
        Import Python files as modules and store them internally.

        :param file_paths: List of file paths to import.
        :type file_paths: Iterable[str]
        :raises FileNotFoundError: If any file does not exist.
        """
        for file_path in file_paths:
            self._import_file(file_path)

    def _import_file(self, file_path: str) -> None:
        """
        Dynamically import a single Python file as a module.

        :param file_path: Path to the Python file.
        :type file_path: str
        :raises FileNotFoundError: If the file does not exist.
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        module_name, _ = os.path.splitext(
            os.path.basename(file_path))
        spec = importlib.util. \
            spec_from_file_location(module_name, file_path)
        module = importlib.util. \
            module_from_spec(spec)
        spec.loader.exec_module(module)

        self._modules.append(module)

    def _find_modules_by_attr(self, name: str) -> list[Any]:
        """
        Find all loaded modules that contain a given attribute.

        :param name: Attribute name to search for.
        :type name: str
        :return: List of modules that contain the attribute.
        :rtype: list[Any]
        :raises RuntimeException: If no module contains the attribute.
        """
        if modules := [module for module in self._modules if name in dir(module)]:
            return modules
        raise RuntimeException(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __getattr__(self, name):
        """
        Override default attribute access to resolve variables/functions
        from imported modules dynamically.

        :param name: Attribute or function name.
        :type name: str
        :return: The resolved attribute or function.
        :raises RuntimeException: If the name cannot be resolved.
        """
        modules = self._find_modules_by_attr(name)
        return getattr(modules[0], name)

    def call_function(self, name: str, *args, **kwargs) -> Any:
        """
        Call a function by name with the given arguments.

        Execution is wrapped in a context manager for GitHub Actions grouping.

        :param name: Name of the function to call.
        :type name: str
        :param args: Positional arguments to the function.
        :param kwargs: Keyword arguments to the function.
        :return: Result of the function call.
        :rtype: Any
        """
        with group_github_logs():
            return self.__getattr__(name)(*args, **kwargs)

    def set_variable(self, name: str, value: Any) -> None:
        """
        Set a variable with the given name and value in all modules where it exists.

        :param name: Name of the variable.
        :type name: str
        :param value: Value to assign.
        :type value: Any
        """
        modules = self._find_modules_by_attr(name)
        for module in modules:
            setattr(module, name, value)

    def set_variable_literal(self, name: str, literal: str) -> None:
        """
        Set a variable using a literal string that is safely evaluated.

        :param name: Name of the variable.
        :type name: str
        :param literal: Python-literal string to evaluate and assign.
        :type literal: str
        """
        self.set_variable(name, literal_eval(literal))
