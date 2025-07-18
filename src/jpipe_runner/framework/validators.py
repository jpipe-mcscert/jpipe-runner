from typing import Any, Callable

from jpipe_runner.framework.context import RuntimeContext
from .logger import GLOBAL_LOGGER
from ..GraphWorkflowVisualizer import GraphWorkflowVisualizer


class BaseValidator:
    """
    Abstract base class for all pipeline validation checks.

    Subclasses must implement the `validate()` method and append any errors
    encountered during validation to `self.errors`.

    :param pipeline: The pipeline engine to validate.
    :type pipeline: PipelineEngine
    """

    def __init__(self, pipeline: "PipelineEngine", ctx: "RuntimeContext"):
        self.pipeline = pipeline
        self.ctx = ctx
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
        for func_key, var_maps in self.ctx._vars.items():
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
        for func_key, var_maps in self.ctx._vars.items():
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
            consume_vars = self.ctx._vars.get(func_key, {}).get(RuntimeContext.CONSUME, {})
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
        GLOBAL_LOGGER.info(f"OrderValidator completed with {len(errors)} error(s).")
        return errors


class ProducedButNotConsumedValidator(BaseValidator):
    """
    Validator that checks whether variables produced by functions are actually consumed by others.

    This helps detect variables that are produced but never used downstream, which may indicate
    redundant or misconfigured pipeline steps.
    """

    def validate(self) -> list[str]:
        """
        Validate that all produced variables by functions are consumed by at least one other function.

        :return: A list of error messages for produced variables that are not consumed.
        :rtype: list[str]
        """
        GLOBAL_LOGGER.info("Running ProducedButNotConsumedValidator...")
        errors = []

        # Collect all consumed variables across the pipeline
        consumed_vars = set()
        for func_key, var_maps in self.ctx._vars.items():
            consume_vars = var_maps.get(RuntimeContext.CONSUME, {})
            consumed_vars.update(consume_vars.keys())

        # Check each produced variable to ensure it's consumed somewhere else
        for func_key, var_maps in self.ctx._vars.items():
            produce_vars = var_maps.get(RuntimeContext.PRODUCE, {})
            for var in produce_vars:
                if var not in consumed_vars:
                    errors.append(
                        (
                            f"Pipeline validation error: produced variable not consumed.\n"
                            f"  • Variable '{var}' is produced by function '{func_key}' but is never consumed by any function.\n"
                            f"  • This may indicate redundant computation or misconfiguration.\n"
                            f"  • Consider removing the production of '{var}' if unused, or verify downstream usage.\n"
                        )
                    )

        GLOBAL_LOGGER.info(f"ProducedButNotConsumedValidator completed with {len(errors)} error(s).")
        return errors


class DuplicateProducerValidator(BaseValidator):
    """
    Validator that checks that no variable is produced by more than one function.

    A variable in a pipeline must be produced by only a single function to ensure
    clear data provenance and avoid ambiguity in execution dependencies.
    """

    def validate(self) -> list[str]:
        """
        Validate that each produced variable is only produced by a single function.

        :return: A list of error messages for duplicate producers.
        :rtype: list[str]
        """
        GLOBAL_LOGGER.info("Running DuplicateProducerValidator...")
        errors = []
        variable_to_producers: dict[str, list[str]] = {}

        for func_key, var_maps in self.ctx._vars.items():
            produced_vars = var_maps.get(RuntimeContext.PRODUCE, {})
            GLOBAL_LOGGER.debug(f"Function '{func_key}' produces: {list(produced_vars)}")
            for var in produced_vars:
                variable_to_producers.setdefault(var, []).append(func_key)

        for var, producers in variable_to_producers.items():
            if len(producers) > 1:
                error_message = (
                    "Pipeline validation error: duplicate producers detected.\n"
                    f"  • Variable '{var}' is produced by multiple functions: {producers}\n"
                    "  • Each variable must have exactly one producer to maintain a valid pipeline structure.\n"
                    "  • To fix:\n"
                    f"    - Choose a single function to produce '{var}' and remove it from the others.\n"
                    "    - If multiple outputs are required, consider renaming or splitting the variables.\n"
                )
                errors.append(error_message)

        GLOBAL_LOGGER.info(f"DuplicateProducerValidator completed with {len(errors)} error(s).")
        return errors


class JustificationSchemaValidator:
    """
    Validates the structure and contents of a justification JSON definition.

    This validator checks that:
    - All required top-level keys are present (`name`, `type`, `elements`, `relations`).
    - The `elements` list contains objects with the required fields (`id`, `label`, `type`).
    - Element types are among the allowed types: `evidence`, `strategy`, `conclusion`, `sub-conclusion`.
    - Element IDs are unique.
    - The `relations` list contains valid `source` and `target` keys.
    - Each `source` and `target` ID in `relations` must refer to an existing element ID.

    This class is intended to be used before constructing the justification graph,
    ensuring that the input JSON is well-structured and logically valid.

    Raises:
        ValueError: If any structural validation check fails.
    """

    REQUIRED_TOP_KEYS = {"name", "type", "elements", "relations"}
    VALID_TYPES = {"evidence", "strategy", "conclusion", "sub-conclusion"}

    def __init__(self, data: dict[str, Any], mark_substep: Callable[[str, str, str], None]) -> None:
        """
         Initialize the validator with parsed justification JSON data.

         :param data: Dictionary representing the justification JSON content.
         :type data: dict[str, Any]
         :param mark_substep: Function to mark validation steps in the workflow visualizer.
         :type mark_substep: Callable[[str, str, str], None]
        """
        self.data = data
        self.mark_substep = mark_substep
        self.element_ids = set()

    def validate(self) -> None:
        """
         Executes the full validation pipeline on the justification structure.

         Steps:
         - Verifies the presence of top-level keys.
         - Validates individual elements for required structure and valid types.
         - Validates that relations correctly reference existing element IDs.

         :raises ValueError: If any of the structural checks fail.
         """
        GLOBAL_LOGGER.debug("Starting justification schema validation")

        self.mark_substep(
            GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
            "Checking Top-level keys",
            GraphWorkflowVisualizer.CURRENT
        )

        # Check top-level keys
        missing = self.REQUIRED_TOP_KEYS - self.data.keys()
        if missing:
            self.mark_substep(
                GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
                "Checking Top-level keys",
                GraphWorkflowVisualizer.FAIL
            )
            raise ValueError(f"Missing top-level key(s): {missing}")
        GLOBAL_LOGGER.info("Top-level keys validated")
        self.mark_substep(
            GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
            "Checking Top-level keys",
            GraphWorkflowVisualizer.DONE
        )

        # Validate elements
        self._validate_elements()

        # Validate relations
        self._validate_relations()

        GLOBAL_LOGGER.info("Justification schema validation completed successfully")

    def _validate_elements(self):
        """
        Validates the structure of each element in the justification.

        Each element must:
        - Be a dictionary with `id`, `label`, and `type` keys.
        - Have a `type` that is among the allowed VALID_TYPES.
        - Use a unique `id` across all elements.

        :raises ValueError: If any element is invalid or duplicates are found.
        """
        self.mark_substep(
            GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
            GraphWorkflowVisualizer.VALIDATE_STRUCTURE_ELEMENTS,
            GraphWorkflowVisualizer.CURRENT
        )
        elements = self.data.get("elements", [])
        if not isinstance(elements, list):
            self.mark_substep(
                GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
                GraphWorkflowVisualizer.VALIDATE_STRUCTURE_ELEMENTS,
                GraphWorkflowVisualizer.FAIL
            )
            raise ValueError("'elements' must be a list")

        for i, element in enumerate(elements):
            for key in ["id", "label", "type"]:
                if key not in element:
                    self.mark_substep(
                        GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
                        GraphWorkflowVisualizer.VALIDATE_STRUCTURE_ELEMENTS,
                        GraphWorkflowVisualizer.FAIL
                    )
                    raise ValueError(f"Element {i} is missing required key '{key}'")

            if element["type"] not in self.VALID_TYPES:
                self.mark_substep(
                    GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
                    GraphWorkflowVisualizer.VALIDATE_STRUCTURE_ELEMENTS,
                    GraphWorkflowVisualizer.FAIL
                )
                raise ValueError(f"Invalid type '{element['type']}' in element '{element['id']}'")

            if element["id"] in self.element_ids:
                self.mark_substep(
                    GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
                    GraphWorkflowVisualizer.VALIDATE_STRUCTURE_ELEMENTS,
                    GraphWorkflowVisualizer.FAIL
                )
                raise ValueError(f"Duplicate element id: '{element['id']}'")

            self.element_ids.add(element["id"])

        GLOBAL_LOGGER.debug("All elements validated: %s", self.element_ids)
        self.mark_substep(
            GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
            GraphWorkflowVisualizer.VALIDATE_STRUCTURE_ELEMENTS,
            GraphWorkflowVisualizer.DONE
        )

    def _validate_relations(self):
        """
        Validates the structure and references of each relation in the justification.

        Each relation must:
        - Be a dictionary with `source` and `target` keys.
        - Reference only valid element IDs defined in the `elements` section.

        :raises ValueError: If relations are malformed or refer to unknown elements.
        """
        self.mark_substep(
            GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
            GraphWorkflowVisualizer.VALIDATE_RELATIONS_STRUCTURES,
            GraphWorkflowVisualizer.CURRENT
        )
        relations = self.data.get("relations", [])
        if not isinstance(relations, list):
            self.mark_substep(
                GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
                GraphWorkflowVisualizer.VALIDATE_RELATIONS_STRUCTURES,
                GraphWorkflowVisualizer.FAIL
            )
            raise ValueError("'relations' must be a list")

        for i, rel in enumerate(relations):
            for key in ["source", "target"]:
                if key not in rel:
                    self.mark_substep(
                        GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
                        GraphWorkflowVisualizer.VALIDATE_RELATIONS_STRUCTURES,
                        GraphWorkflowVisualizer.FAIL
                    )
                    raise ValueError(f"Relation {i} is missing required key '{key}'")

                if rel[key] not in self.element_ids:
                    self.mark_substep(
                        GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
                        GraphWorkflowVisualizer.VALIDATE_RELATIONS_STRUCTURES,
                        GraphWorkflowVisualizer.FAIL
                    )
                    raise ValueError(f"Relation {i} refers to unknown {key} id '{rel[key]}'")

        GLOBAL_LOGGER.debug("All relations validated: %d total", len(relations))
        self.mark_substep(
            GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE,
            GraphWorkflowVisualizer.VALIDATE_RELATIONS_STRUCTURES,
            GraphWorkflowVisualizer.DONE
        )
