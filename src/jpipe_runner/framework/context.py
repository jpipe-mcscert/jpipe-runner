from typing import Any

from jpipe_runner.framework.logger import GLOBAL_LOGGER


class RuntimeContext:
    """
    RuntimeContext manages variables produced and consumed by pipeline functions.

    It maintains an internal mapping (`self._vars`) from function keys (names or identifiers)
    to dictionaries of produced and consumed variables. Each function key maps to a dict
    where keys RuntimeContext.PRODUCE and RuntimeContext.CONSUME map to dicts of variable names
    to their values.

    Attributes:
        _vars (dict): Mapping from function keys to another dict:
            {
                RuntimeContext.PRODUCE: { var_name: value, ... },
                RuntimeContext.CONSUME: { var_name: value, ... }
            }
    """
    PRODUCE = '_produce'
    CONSUME = '_consume'

    def __init__(self):
        """
        Initialize a new RuntimeContext with an empty variable mapping.
        """
        self._vars = {}

    def get(self, key) -> Any:
        """
        Retrieve the values of a given variable across all functions that have it in their context.

        Scans through all registered function entries in self._vars, and for each function
        where `key` exists (either in its PRODUCE or CONSUME dict), collects the corresponding value.

        :param key: The variable name to retrieve.
        :type key: str
        :return: A list of values associated with `key` across functions that have it.
                 If no function has this key, returns an empty list.
        :rtype: Any
        """
        GLOBAL_LOGGER.debug(f"Context: %s", self._vars)
        for func in self._vars:
            for decorator in (self.PRODUCE, self.CONSUME):
                if key in self._vars[func].get(decorator, {}):
                    value = self._vars[func][decorator][key]
                    GLOBAL_LOGGER.debug(f"Retrieved variable '{key}' with value '{value}' from function '{func}'")
                    return value
        return None

    def _set(self, func, key, value, decorator):
        """
        Register or update a variable in the context for a specific function.

        If the function key does not exist in self._vars, initializes its entry.
        Then, under the given decorator type (RuntimeContext.PRODUCE or CONSUME),
        sets the variable `key` to `value`.

        This is typically called by the Consume/Produce decorators to initialize
        variables with None before actual runtime assignment.

        :param func: Function name or identifier under which to register the variable.
        :type func: str
        :param key: Variable name to set.
        :type key: str
        :param value: Initial value for the variable (often None when first declared).
        :type value: object
        :param decorator: Either RuntimeContext.PRODUCE or RuntimeContext.CONSUME,
                          indicating whether this variable is produced or consumed.
        :type decorator: str
        """
        if func not in self._vars:
            self._vars[func] = {}
        if decorator not in self._vars[func]:
            self._vars[func][decorator] = {}
        self._vars[func][decorator][key] = value
        GLOBAL_LOGGER.debug(f"Set variable '{key}' to '{value}' in function '{func}' under decorator '{decorator}'")
        GLOBAL_LOGGER.debug(f"Updated context: {self._vars[func]}")

    def set(self, key, value):
        """
        Set the value of a variable in the context for the first function that has declared it.

        Iterates through all function entries in self._vars; if a function context contains
        `key` (in either its PRODUCE or CONSUME map), sets that entry to `value` and returns.
        If multiple functions declare the same key, only the first encountered is updated.

        :param key: The variable name to set.
        :type key: str
        :param value: The value to assign to the variable.
        :type value: object
        """
        for func in self._vars:
            for decorator in (self.PRODUCE, self.CONSUME):
                if key in self._vars[func].get(decorator, {}):
                    self._vars[func][decorator][key] = value
                    GLOBAL_LOGGER.debug(f"Set variable '{key}' to '{value}' in function '{func}'")
                    GLOBAL_LOGGER.debug(f"Updated context: {self._vars[func]}")
                    return

    def has(self, func, key):
        """
        Check if a variable exists in the context for any registered function.

        Returns True if any function's context (either PRODUCE or CONSUME) contains `key`.

        :param func: Function name or identifier to check.
        :type func: Any
        :param key: Variable name to check.
        :type key: str
        :return: True if the variable is declared in any function's context, False otherwise.
        :rtype: bool
        """
        if func not in self._vars:
            return False
        return key in self._vars[func].get(self.PRODUCE, {}) or key in self._vars[func].get(self.CONSUME, {})

    def set_from_config(self, key, value, decorator=CONSUME):
        """
        Set a variable in the context for the first function that has declared it.

        This is a convenience method to set a variable without specifying the function name.
        It will find the first function that has declared this variable and set its value.

        :param key: The variable name to set.
        :type key: str
        :param value: The value to assign to the variable.
        :type value: object
        :param decorator: Either RuntimeContext.PRODUCE or RuntimeContext.CONSUME,
                          indicating whether this variable is produced or consumed.
        :type decorator: str
        """
        for func in self._vars:
            if key in self._vars[func][decorator]:
                self._vars[func][decorator][key] = value
                GLOBAL_LOGGER.debug(f"Set variable '{key}' to '{value}' in function '{func}'")
                GLOBAL_LOGGER.debug(f"Updated context: {self._vars[func]}")
                return

    def __repr__(self):
        """
        String representation of the RuntimeContext, showing all registered variables.

        :return: A string representation of the context's variable mapping.
        :rtype: str
        """
        return f"RuntimeContext(vars={self._vars})"


ctx = RuntimeContext()
