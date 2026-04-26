from jpipe_runner.framework.context import RuntimeContext

from ..logger import GLOBAL_LOGGER
from .base import BaseValidator


class MissingVariableValidator(BaseValidator):
    """
    Validator that checks for missing variables in the pipeline context.

    Ensures that every consumed variable is either:
    - Produced by a preceding function in the pipeline, or
    - Provided explicitly in the pipeline's external context (e.g., main config).

    Variables that are declared as consumed but have no known source will raise an error.
    """

    def validate(self) -> tuple[list[str], list[str]]:
        """
        Validate that all consumed variables are available in the context or produced upstream.

        :return: A list of error messages describing any missing variables.
        :rtype: list[str]
        """
        GLOBAL_LOGGER.info("Running MissingVariableValidator...")
        for func_key, var_maps in self.ctx._vars.items():
            consume_vars = var_maps.get(RuntimeContext.CONSUME, {})
            GLOBAL_LOGGER.debug(
                f"Checking function '{func_key}' with consumed variables: {list(consume_vars)}"
            )
            for var in consume_vars:
                if consume_vars[var] is not None:
                    GLOBAL_LOGGER.debug(
                        f"Variable '{var}' already resolved in context for '{func_key}'. Skipping."
                    )
                    continue
                producer_key = self.pipeline.get_producer_key(var)
                GLOBAL_LOGGER.debug(f"Producer for variable '{var}' is: {producer_key}")
                if producer_key is None:
                    self.errors.append(
                        (
                            "[MissingVariableValidator]\n"
                            "Pipeline validation error: missing variable.\n"
                            f"  • Function '{func_key}' declares that it consumes variable '{var}',\n"
                            "    but no producer for this variable is found in the pipeline,\n"
                            "    nor is it provided in the 'main' context.\n"
                            "  • To fix:\n"
                            f"    - Ensure that some earlier function produces '{var}', or\n"
                            "    - Provide '{var}' via config/context,\n"
                            f"    so that '{func_key}' can consume it.\n"
                        )
                    )
        GLOBAL_LOGGER.info(f"MissingVariableValidator completed with {len(self.errors)} error(s).")
        return self.errors, self.warnings
