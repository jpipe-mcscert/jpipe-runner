from jpipe_runner.framework.context import RuntimeContext

from ..logger import GLOBAL_LOGGER
from .base import BaseValidator


class OrderValidator(BaseValidator):
    """
    Validator that ensures execution order respects variable dependencies.

    Each function must run only after all the variables it consumes have been produced.
    This validator ensures that no function executes before its required inputs are available.
    """

    def validate(self) -> tuple[list[str], list[str]]:
        """
        Validate that all consumed variables are available at execution time.

        This method performs two checks:
            - Ensures functions do not self-produce/consume the same variable.
            - Validates that a variable's producer appears earlier than its consumer
              in the execution order.

        :return: A list of error messages for any violations in execution order or self-dependency.
        :rtype: list[str]
        """
        GLOBAL_LOGGER.info("Running OrderValidator...")
        order = self.pipeline.get_execution_order()
        GLOBAL_LOGGER.debug(f"Execution order: {order}")
        order_index = {k: i for i, k in enumerate(order)}

        for func_key in order:
            consume_vars = self.ctx._vars.get(func_key, {}).get(RuntimeContext.CONSUME, {})
            GLOBAL_LOGGER.debug(f"Checking order for function '{func_key}'")
            for var in consume_vars:
                producer = self.pipeline.get_producer_key(var)
                GLOBAL_LOGGER.debug(
                    f"Variable '{var}' consumed by '{func_key}' is produced by '{producer}'"
                )
                if producer is None:
                    continue
                if producer == func_key:
                    self.errors.append(
                        (
                            "[OrderValidator]\n"
                            "Pipeline validation error: function '{func}' declares variable '{var}' "
                            "as both consumed and produced by itself.\n"
                            "  • This self-dependency is likely a misconfiguration.\n"
                            "  • If '{var}' should be provided externally, remove it from the produce list of '{func}',\n"
                            "    and ensure an external producer provides an initial '{var}'.\n"
                            "  • If '{func}' is the only producer of '{var}' for downstream use, remove '{var}' from its consume list.\n"
                            "  • If you truly need to consume an initial '{var}' and then produce an updated '{var}',\n"
                            "    ensure the initial '{var}' comes from context or by another function under a different name,\n"
                            "    so that the dependency graph does not treat '{func}' as producing its own input.\n"
                            "  • Function key: '{func}', variable: '{var}'.\n"
                            "  • Current execution order (keys): {order}\n"
                            "  • Please correct the pipeline justification/configuration to resolve this."
                        ).format(func=func_key, var=var, order=" -> ".join(order))
                    )
                    continue

                if order_index[producer] >= order_index[func_key]:
                    self.errors.append(
                        (
                            "[OrderValidator]\n"
                            "Pipeline execution order violation detected:\n"
                            f"  • Function '{func_key}' (index {order_index[func_key]}) consumes variable '{var}',\n"
                            f"    but that variable is produced by function '{producer}' (index {order_index[producer]}),\n"
                            "    which is scheduled to run at or after the consumer.\n"
                            f"  • To fix this, ensure that '{producer}' runs before '{func_key}' in the pipeline justification/config.\n"
                            "  • Current execution order (keys) is:\n"
                            f"      {' -> '.join(order)}\n"
                            f"  • Suggestion: adjust dependencies/justification so that '{producer}' precedes '{func_key}'."
                        )
                    )
        GLOBAL_LOGGER.info(f"OrderValidator completed with {len(self.errors)} error(s).")
        return self.errors, self.warnings
