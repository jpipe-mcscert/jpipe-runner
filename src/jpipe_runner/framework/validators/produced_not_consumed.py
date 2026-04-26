from jpipe_runner.framework.context import RuntimeContext

from ..logger import GLOBAL_LOGGER
from .base import BaseValidator


class ProducedButNotConsumedValidator(BaseValidator):
    """
    Validator that checks whether variables produced by functions are actually consumed by others.

    This helps detect variables that are produced but never used downstream, which may indicate
    redundant or misconfigured pipeline steps.
    """

    def validate(self) -> tuple[list[str], list[str]]:
        """
        Validate that all produced variables by functions are consumed by at least one other function.

        :return: A list of error messages for produced variables that are not consumed.
        :rtype: list[str]
        """
        GLOBAL_LOGGER.info("Running ProducedButNotConsumedValidator...")

        consumed_vars = set()
        for func_key, var_maps in self.ctx._vars.items():
            consume_vars = var_maps.get(RuntimeContext.CONSUME, {})
            consumed_vars.update(consume_vars.keys())

        for func_key, var_maps in self.ctx._vars.items():
            produce_vars = var_maps.get(RuntimeContext.PRODUCE, {})
            for var in produce_vars:
                if var not in consumed_vars:
                    self.warnings.append(
                        (
                            "[ProducedButNotConsumedValidator]\n"
                            f"Pipeline validation error: produced variable not consumed.\n"
                            f"  • Variable '{var}' is produced by function '{func_key}' but is never consumed by any function.\n"
                            f"  • This may indicate redundant computation or misconfiguration.\n"
                            f"  • Consider removing the production of '{var}' if unused, or verify downstream usage.\n"
                        )
                    )

        GLOBAL_LOGGER.info(
            f"ProducedButNotConsumedValidator completed with {len(self.errors)} error(s)."
        )
        return self.errors, self.warnings
