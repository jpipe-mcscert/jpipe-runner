from jpipe_runner.framework.context import RuntimeContext

from ..logger import GLOBAL_LOGGER
from .base import BaseValidator


class SelfDependencyValidator(BaseValidator):
    """
    Validator that checks for self-dependency errors in functions.

    A self-dependency occurs when a function both consumes and produces the same variable.
    This typically results in an ill-defined dependency graph and should be avoided.

    Valid configuration alternatives are suggested in the error message.
    """

    def validate(self) -> tuple[list[str], list[str]]:
        """
        Validate that no function is both the producer and consumer of the same variable.

        :return: A list of error messages for each self-dependency found.
        :rtype: list[str]
        """
        GLOBAL_LOGGER.info("Running SelfDependencyValidator...")
        for func_key, var_maps in self.ctx._vars.items():
            consume_vars = var_maps.get(RuntimeContext.CONSUME, {})
            GLOBAL_LOGGER.debug(f"Checking function '{func_key}' for self-dependencies.")
            for var in consume_vars:
                producer_key = self.pipeline.get_producer_key(var)
                GLOBAL_LOGGER.debug(
                    f"Variable '{var}' consumed by '{func_key}' is produced by '{producer_key}'"
                )
                if producer_key == func_key:
                    self.errors.append(
                        "[SelfDependencyValidator]\n"
                        "Pipeline validation error: self-dependency detected.\n"
                        f"  • Function '{func_key}' declares variable '{var}' as both consumed and produced by itself.\n"
                        "    This is likely a misconfiguration:\n"
                        f"      - If '{var}' should come from outside, remove it from this function's produce list\n"
                        "        and ensure an external provider supplies it.\n"
                        f"      - If this function is the sole producer for downstream use, remove '{var}' from its consume list.\n"
                        f"      - If you truly need to consume an initial '{var}' and then produce an updated '{var}',\n"
                        f"        ensure that initial '{var}' is provided in context or by another function under a distinct name,\n"
                        f"        so the dependency graph does not treat the same function as its own producer.\n"
                    )
        GLOBAL_LOGGER.info(f"SelfDependencyValidator completed with {len(self.errors)} error(s).")
        return self.errors, self.warnings
