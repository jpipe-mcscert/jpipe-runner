from jpipe_runner.framework.context import RuntimeContext, ctx
from .logger import GLOBAL_LOGGER


class BaseValidator:
    """
    Abstract base class for all pipeline validation checks.

    Subclasses must implement the `validate()` method and append any errors
    encountered during validation to `self.errors`.

    :param pipeline: The pipeline engine to validate.
    :type pipeline: PipelineEngine
    """

    def __init__(self, pipeline: "PipelineEngine"):
        self.pipeline = pipeline
        self.errors: list[str] = []

    def validate(self) -> bool:
        """
        Abstract method for performing validation.

        Subclasses must override this method to implement specific validation logic. This method
        should populate `self.errors` with detailed error messages and return them.

        :raises NotImplementedError: If called on the abstract base class.
        :return: A list of error messages (if any).
        :rtype: list[str]
        """
        raise NotImplementedError("Subclasses must implement the `validate()` method.")


class MissingVariableValidator(BaseValidator):
    """
    Validator that checks for missing variables in the pipeline context.

    Ensures that every consumed variable is either:
    - Produced by a preceding function in the pipeline, or
    - Provided explicitly in the pipeline's external context (e.g., main config).

    Variables that are declared as consumed but have no known source will raise an error.
    """

    def validate(self) -> list[str]:
        """
        Validate that all consumed variables are available in the context or produced upstream.

        :return: A list of error messages describing any missing variables.
        :rtype: list[str]
        """
        GLOBAL_LOGGER.info("Running MissingVariableValidator...")
        errors = []
        for func_key, var_maps in ctx._vars.items():
            consume_vars = var_maps.get(RuntimeContext.CONSUME, {})
            GLOBAL_LOGGER.debug(f"Checking function '{func_key}' with consumed variables: {list(consume_vars)}")
            for var in consume_vars:
                if consume_vars[var] is not None:
                    GLOBAL_LOGGER.debug(f"Variable '{var}' already resolved in context for '{func_key}'. Skipping.")
                    continue
                producer_key = self.pipeline.get_producer_key(var)
                GLOBAL_LOGGER.debug(f"Producer for variable '{var}' is: {producer_key}")
                if producer_key is None:
                    errors.append(
                        (
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
                    GLOBAL_LOGGER.warning(f"Missing variable detected: '{var}' required by '{func_key}'")
        GLOBAL_LOGGER.info(f"MissingVariableValidator completed with {len(errors)} error(s).")
        return errors


class SelfDependencyValidator(BaseValidator):
    """
    Validator that checks for self-dependency errors in functions.

    A self-dependency occurs when a function both consumes and produces the same variable.
    This typically results in an ill-defined dependency graph and should be avoided.

    Valid configuration alternatives are suggested in the error message.
    """

    def validate(self) -> list[str]:
        """
        Validate that no function is both the producer and consumer of the same variable.

        :return: A list of error messages for each self-dependency found.
        :rtype: list[str]
        """
        GLOBAL_LOGGER.info("Running SelfDependencyValidator...")
        errors = []
        for func_key, var_maps in ctx._vars.items():
            consume_vars = var_maps.get(RuntimeContext.CONSUME, {})
            GLOBAL_LOGGER.debug(f"Checking function '{func_key}' for self-dependencies.")
            for var in consume_vars:
                producer_key = self.pipeline.get_producer_key(var)
                GLOBAL_LOGGER.debug(f"Variable '{var}' consumed by '{func_key}' is produced by '{producer_key}'")
                if producer_key == func_key:
                    errors.append(
                        (
                            "Pipeline validation error: self-dependency detected.\n"
                            f"  • Function '{func_key}' declares variable '{var}' as both consumed and produced by itself.\n"
                            "    This is likely a misconfiguration:\n"
                            "      - If '{var}' should come from outside, remove it from this function's produce list\n"
                            "        and ensure an external provider supplies it.\n"
                            "      - If this function is the sole producer for downstream use, remove '{var}' from its consume list.\n"
                            "      - If you truly need to consume an initial '{var}' and then produce an updated '{var}',\n"
                            "        ensure that initial '{var}' is provided in context or by another function under a distinct name,\n"
                            "        so the dependency graph does not treat the same function as its own producer.\n"
                        ).replace("{var}", var).replace("{func_key}", func_key)
                    )
                    GLOBAL_LOGGER.warning(f"Self-dependency detected in '{func_key}' for variable '{var}'")
        GLOBAL_LOGGER.info(f"SelfDependencyValidator completed with {len(errors)} error(s).")
        return errors


class OrderValidator(BaseValidator):
    """
    Validator that ensures execution order respects variable dependencies.

    Each function must run only after all the variables it consumes have been produced.
    This validator ensures that no function executes before its required inputs are available.
    """

    def validate(self) -> list[str]:
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
        errors = []
        order = self.pipeline.get_execution_order()
        GLOBAL_LOGGER.debug(f"Execution order: {order}")
        order_index = {k: i for i, k in enumerate(order)}

        for func_key in order:
            consume_vars = ctx._vars.get(func_key, {}).get(RuntimeContext.CONSUME, {})
            GLOBAL_LOGGER.debug(f"Checking order for function '{func_key}'")
            for var in consume_vars:
                producer = self.pipeline.get_producer_key(var)
                GLOBAL_LOGGER.debug(f"Variable '{var}' consumed by '{func_key}' is produced by '{producer}'")
                if producer is None:
                    continue
                if producer == func_key:
                    errors.append(
                        (
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
                    GLOBAL_LOGGER.warning(f"Self-dependency (order-level) in '{func_key}' for variable '{var}'")
                    continue

                if order_index[producer] >= order_index[func_key]:
                    errors.append(
                        (
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
                    GLOBAL_LOGGER.warning(
                        f"Order violation: '{func_key}' consumes '{var}' before '{producer}' has produced it."
                    )
        GLOBAL_LOGGER.info(f"OrderValidator completed with {len(errors)} error(s).")
        return errors
