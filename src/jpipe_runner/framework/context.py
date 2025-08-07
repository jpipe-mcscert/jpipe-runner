from typing import Any, Dict, List

from jpipe_runner.framework.logger import GLOBAL_LOGGER


class RuntimeContext:
    """
    RuntimeContext manages variables produced and consumed by pipeline functions.

    It maintains an internal mapping (`self._vars`) from function keys (names or identifiers)
    to dictionaries of produced and consumed variables. Each function key maps to a dict
    where keys RuntimeContext.PRODUCE and RuntimeContext.CONSUME map to dicts of variable names
    to their values.

    Attributes:
        _vars (dict): Main context mapping. Structure:
            {
                <function_key>: {
                    RuntimeContext.PRODUCE: { <var_name>: <value>, ... },
                    RuntimeContext.CONSUME: { <var_name>: <value>, ... },
                    RuntimeContext.SKIP: {
                        'value': <bool>,   # True if the function should be skipped
                        'reason': <str>    # Reason for skipping
                    },
                    RuntimeContext.CONTRIBUTION: {
                        RuntimeContext.POSITIVE: [<var_name>, ...], # Positive contributions
                        RuntimeContext.NEGATIVE: [<var_name>, ...], # Negative contributions
                    }
                },
                ...
            }
    """
    PRODUCE = '_produce'
    CONSUME = '_consume'
    SKIP = '_skip'
    CONTRIBUTION = '_contribution'
    POSITIVE = '_positive'
    NEGATIVE = '_negative'

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
                 If no function has this key, return an empty list.
        :rtype: Any
        """
        GLOBAL_LOGGER.debug(f"Context: {self._vars}")
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
        GLOBAL_LOGGER.info(f"Set variable '{key}' to '{value}' in function '{func}' under decorator '{decorator}'")
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
        GLOBAL_LOGGER.info(f"Setting variable '{key}' to '{value}' with decorator '{decorator}'")
        for func in self._vars:
            if decorator not in self._vars[func]:
                continue
            if key in self._vars[func][decorator]:
                self._vars[func][decorator][key] = value
                GLOBAL_LOGGER.debug(f"Set variable '{key}' to '{value}' in function '{func}'")
                GLOBAL_LOGGER.debug(f"Updated context: {self._vars[func]}")

    def set_skip(self, func, value: bool, reason: str = "Skipped by condition"):
        """
        Set the skip status for a function in the context.

        This method allows marking a function as skipped based on a condition.
        It updates the context to reflect whether the function should be skipped.

        :param func: The function name or identifier to set the skip status for.
        :type func: str
        :param value: True if the function should be skipped, False otherwise.
        :type value: bool
        :param reason: The reason for skipping the function.
        :type reason: str
        """
        if func not in self._vars:
            self._vars[func] = {}
        self._vars[func][self.SKIP] = {
            'value': value,
            'reason': reason
        }
        GLOBAL_LOGGER.debug(f"Set skip status for function '{func}' to {value} with reason: {reason}")

    def set_contribution(self, func, contribution_type: str, variables: list[str]):
        """
        Set the contribution type for a function in the context.

        This method allows marking a function's contribution as either positive or negative.
        It updates the context to reflect the contribution type and associated variables.

        :param func: The function name or identifier to set the contribution for.
        :type func: str
        :param contribution_type: Either RuntimeContext.POSITIVE or RuntimeContext.NEGATIVE,
                                 indicating the type of contribution.
        :type contribution_type: str
        :param variables: A list of variable names that contribute to this type.
        :type variables: list[str]
        """
        if func not in self._vars:
            self._vars[func] = {}
        if self.CONTRIBUTION not in self._vars[func]:
            self._vars[func][self.CONTRIBUTION] = {
                self.POSITIVE: [],
                self.NEGATIVE: []
            }
        self._vars[func][self.CONTRIBUTION][contribution_type].extend(variables)
        GLOBAL_LOGGER.debug(f"Set {contribution_type} contribution for function '{func}' with variables: {variables}")

    def get_contributions(self, func: str) -> Dict[str, List[str]]:
        """
        Retrieves positive and negative contributions for a given function.

        Args:
            func (str): Function name.

        Returns:
            dict: {'_positive': [...], '_negative': [...]} — lists may be empty.
        """
        return self._vars.get(func, {}).get(RuntimeContext.CONTRIBUTION, {
            self.POSITIVE: [],
            self.NEGATIVE: []
        })

    def __repr__(self):
        """
        String representation of the RuntimeContext, showing all registered variables.

        :return: A string representation of the context's variable mapping.
        :rtype: str
        """
        return f"RuntimeContext(vars={self._vars})"


ctx = RuntimeContext()
