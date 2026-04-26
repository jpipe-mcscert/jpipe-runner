from jpipe_runner.framework.context import RuntimeContext

from ..logger import GLOBAL_LOGGER
from .base import BaseValidator


class DuplicateProducerValidator(BaseValidator):
    """
    Validator that checks that no variable is produced by more than one function.

    A variable in a pipeline must be produced by only a single function to ensure
    clear data provenance and avoid ambiguity in execution dependencies.
    """

    def validate(self) -> tuple[list[str], list[str]]:
        """
        Validate that each produced variable is only produced by a single function.

        :return: A list of error messages for duplicate producers.
        :rtype: list[str]
        """
        GLOBAL_LOGGER.info("Running DuplicateProducerValidator...")
        variable_to_producers: dict[str, list[str]] = {}

        for func_key, var_maps in self.ctx._vars.items():
            produced_vars = var_maps.get(RuntimeContext.PRODUCE, {})
            GLOBAL_LOGGER.debug(f"Function '{func_key}' produces: {list(produced_vars)}")
            for var in produced_vars:
                variable_to_producers.setdefault(var, []).append(func_key)

        for var, producers in variable_to_producers.items():
            if len(producers) > 1:
                error_message = (
                    "[DuplicateProducerValidator]\n"
                    "Pipeline validation error: duplicate producers detected.\n"
                    f"  • Variable '{var}' is produced by multiple functions: {producers}\n"
                    "  • Each variable must have exactly one producer to maintain a valid pipeline structure.\n"
                    "  • To fix:\n"
                    f"    - Choose a single function to produce '{var}' and remove it from the others.\n"
                    "    - If multiple outputs are required, consider renaming or splitting the variables.\n"
                )
                self.errors.append(error_message)

        GLOBAL_LOGGER.info(
            f"DuplicateProducerValidator completed with {len(self.errors)} error(s)."
        )
        return self.errors, self.warnings
