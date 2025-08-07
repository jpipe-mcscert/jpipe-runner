from typing import Any, Callable

import networkx as nx

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

    def __init__(self, pipeline: "PipelineEngine", ctx: "RuntimeContext") -> None:
        self.pipeline = pipeline
        self.ctx = ctx
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate(self) -> tuple[list[Any], list[Any]]:
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

    def validate(self) -> tuple[list[Any], list[Any]]:
        """
        Validate that all consumed variables are available in the context or produced upstream.

        :return: A list of error messages describing any missing variables.
        :rtype: list[str]
        """
        GLOBAL_LOGGER.info("Running MissingVariableValidator...")
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


class SelfDependencyValidator(BaseValidator):
    """
    Validator that checks for self-dependency errors in functions.

    A self-dependency occurs when a function both consumes and produces the same variable.
    This typically results in an ill-defined dependency graph and should be avoided.

    Valid configuration alternatives are suggested in the error message.
    """

    def validate(self) -> tuple[list[Any], list[Any]]:
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
                GLOBAL_LOGGER.debug(f"Variable '{var}' consumed by '{func_key}' is produced by '{producer_key}'")
                if producer_key == func_key:
                    self.errors.append(
                        (
                            "[SelfDependencyValidator]\n"
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
        GLOBAL_LOGGER.info(f"SelfDependencyValidator completed with {len(self.errors)} error(s).")
        return self.errors, self.warnings


class OrderValidator(BaseValidator):
    """
    Validator that ensures execution order respects variable dependencies.

    Each function must run only after all the variables it consumes have been produced.
    This validator ensures that no function executes before its required inputs are available.
    """

    def validate(self) -> tuple[list[Any], list[Any]]:
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
                GLOBAL_LOGGER.debug(f"Variable '{var}' consumed by '{func_key}' is produced by '{producer}'")
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


class ProducedButNotConsumedValidator(BaseValidator):
    """
    Validator that checks whether variables produced by functions are actually consumed by others.

    This helps detect variables that are produced but never used downstream, which may indicate
    redundant or misconfigured pipeline steps.
    """

    def validate(self) -> tuple[list[Any], list[Any]]:
        """
        Validate that all produced variables by functions are consumed by at least one other function.

        :return: A list of error messages for produced variables that are not consumed.
        :rtype: list[str]
        """
        GLOBAL_LOGGER.info("Running ProducedButNotConsumedValidator...")

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
                    self.warnings.append(
                        (
                            "[ProducedButNotConsumedValidator]\n"
                            f"Pipeline validation error: produced variable not consumed.\n"
                            f"  • Variable '{var}' is produced by function '{func_key}' but is never consumed by any function.\n"
                            f"  • This may indicate redundant computation or misconfiguration.\n"
                            f"  • Consider removing the production of '{var}' if unused, or verify downstream usage.\n"
                        )
                    )

        GLOBAL_LOGGER.info(f"ProducedButNotConsumedValidator completed with {len(self.errors)} error(s).")
        return self.errors, self.warnings


class DuplicateProducerValidator(BaseValidator):
    """
    Validator that checks that no variable is produced by more than one function.

    A variable in a pipeline must be produced by only a single function to ensure
    clear data provenance and avoid ambiguity in execution dependencies.
    """

    def validate(self) -> tuple[list[Any], list[Any]]:
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
                self.warnings.append(error_message)

        GLOBAL_LOGGER.info(f"DuplicateProducerValidator completed with {len(self.errors)} error(s).")
        return self.errors, self.warnings


class EvidenceDependencyValidator(BaseValidator):
    """
    Validates the dependency relationship between evidence and strategy nodes in a justification graph.

    Specifically, it ensures that:
    1. Every evidence node produces at least one output variable.
    2. Every strategy node directly connected above an evidence node consumes all variables produced by that evidence.
    """

    def __init__(self, pipeline: "PipelineEngine", ctx: "RuntimeContext", graph: nx.DiGraph) -> None:
        """
        Initialize the EvidenceDependencyValidator.

        :param pipeline: The pipeline engine being validated.
        :type pipeline: PipelineEngine
        :param ctx: The runtime context containing mappings of variables produced and consumed.
        :type ctx: RuntimeContext
        :param graph: The justification graph representing function dependencies.
        :type graph: nx.DiGraph
        """
        super().__init__(pipeline, ctx)
        self.graph = graph

    def validate(self) -> tuple[list[str], list[str]]:
        """
        Perform the validation of evidence-to-strategy variable dependencies.

        The following checks are performed:
        - Each evidence node must produce at least one variable.
        - All strategy nodes directly above an evidence node must consume every variable that evidence produces.

        :return: A tuple containing:
            - A list of error messages describing invalid dependencies.
            - A list of warnings (currently unused).
        :rtype: tuple[list[str], list[str]]
        """
        GLOBAL_LOGGER.info("Running EvidenceDependencyValidator...")
        errors = []
        warnings = []

        evidence_nodes = self._get_nodes_by_type('evidence')
        evidence_strategy_edges = self._get_evidence_strategy_edges()

        for evidence in evidence_nodes:
            produced_vars = self._get_produced_variables(evidence)

            if not produced_vars:
                errors.append(self._create_no_variables_error(evidence))
                continue

            connected_strategies = self._get_connected_strategies(evidence, evidence_strategy_edges)
            errors.extend(
                self._validate_strategy_consumption(evidence, produced_vars, connected_strategies)
            )

        GLOBAL_LOGGER.info(
            f"EvidenceDependencyValidator completed with {len(errors)} error(s) and {len(warnings)} warning(s)."
        )
        return errors, warnings

    def _get_nodes_by_type(self, node_type: str) -> list[str]:
        """
        Retrieve all function names for nodes of a given type.

        :param node_type: Type of node to search for ('evidence' or 'strategy').
        :type node_type: str
        :return: List of function names for matching nodes.
        :rtype: list[str]
        """
        return [
            self.graph.nodes[n].get('function_name')
            for n, d in self.graph.nodes(data=True)
            if d.get('type') == node_type
        ]

    def _get_evidence_strategy_edges(self) -> list[tuple[str, str]]:
        """
        Extract edges connecting evidence nodes to strategy nodes.

        :return: A list of (evidence_function_name, strategy_function_name) tuples.
        :rtype: list[tuple[str, str]]
        """
        return [
            (self.graph.nodes[u].get('function_name'), self.graph.nodes[v].get('function_name'))
            for u, v, d in self.graph.edges(data=True)
            if (self.graph.nodes[u].get('type') == 'evidence' and
                self.graph.nodes[v].get('type') == 'strategy')
        ]

    def _get_produced_variables(self, function_name: str) -> list[str]:
        """
        Retrieve variables produced by the given function.

        :param function_name: Name of the function.
        :type function_name: str
        :return: List of variable names the function produces.
        :rtype: list[str]
        """
        return list(self.ctx._vars.get(function_name, {}).get(RuntimeContext.PRODUCE, {}).keys())

    def _get_consumed_variables(self, function_name: str) -> list[str]:
        """
        Retrieve variables consumed by the given function.

        :param function_name: Name of the function.
        :type function_name: str
        :return: List of variable names the function consumes.
        :rtype: list[str]
        """
        return list(self.ctx._vars.get(function_name, {}).get(RuntimeContext.CONSUME, {}).keys())

    @staticmethod
    def _get_connected_strategies(evidence: str, evidence_strategy_edges: list[tuple[str, str]]) -> list[str]:
        """
        Get all strategy function names that are directly connected to a given evidence node.

        :param evidence: The evidence function name.
        :type evidence: str
        :param evidence_strategy_edges: List of edges from evidence to strategy nodes.
        :type evidence_strategy_edges: list[tuple[str, str]]
        :return: List of strategy function names.
        :rtype: list[str]
        """
        return [
            strategy for ev, strategy in evidence_strategy_edges
            if ev == evidence
        ]

    def _validate_strategy_consumption(
            self,
            evidence: str,
            produced_vars: list[str],
            connected_strategies: list[str]
    ) -> list[str]:
        """
        Check that all connected strategies consume every variable produced by the evidence.

        :param evidence: Function name of the evidence node.
        :type evidence: str
        :param produced_vars: Variables produced by the evidence node.
        :type produced_vars: list[str]
        :param connected_strategies: Strategies connected to this evidence node.
        :type connected_strategies: list[str]
        :return: List of formatted error messages (if any).
        :rtype: list[str]
        """
        errors = []
        non_consuming_strategies = []

        for strategy in connected_strategies:
            consumed_vars = self._get_consumed_variables(strategy)
            if not all(var in consumed_vars for var in produced_vars):
                non_consuming_strategies.append(strategy)

        if non_consuming_strategies:
            errors.append(self._create_consumption_error(
                evidence, produced_vars, non_consuming_strategies
            ))

        return errors

    @staticmethod
    def _create_no_variables_error(evidence: str) -> str:
        """
        Generate an error message for an evidence node that produces no variables.

        :param evidence: Function name of the evidence node.
        :type evidence: str
        :return: A formatted error message.
        :rtype: str
        """
        return (
            "[EvidenceDependencyValidator]\n"
            f"Pipeline validation error: evidence node does not produce any variables.\n"
            f"  • Evidence: '{evidence}'\n"
            f"  • Problem: This evidence does not produce any output variables.\n"
            f"  • Impact: Strategies connected above this evidence will not receive required inputs.\n"
            f"  • Recommendation: Ensure that the function associated with evidence '{evidence}' is correctly producing at least one variable.\n"
        )

    @staticmethod
    def _create_consumption_error(evidence: str, produced_vars: list[str], strategies: list[str]) -> str:
        """
        Generate an error message when strategy nodes do not consume all variables produced by an evidence node.

        :param evidence: Function name of the evidence node.
        :type evidence: str
        :param produced_vars: List of variables produced by the evidence.
        :type produced_vars: list[str]
        :param strategies: List of strategy function names not consuming the variables.
        :type strategies: list[str]
        :return: A formatted error message.
        :rtype: str
        """
        strategy_list = "', '".join(strategies)
        return (
            "[EvidenceDependencyValidator]\n"
            f"Pipeline validation error: evidence variables not consumed by strategies.\n"
            f"  • Evidence: '{evidence}'\n"
            f"  • Produced Variables: {produced_vars}\n"
            f"  • Affected Strategies: ['{strategy_list}']\n"
            f"  • Problem: These strategies do not consume all variables produced by the evidence directly below them.\n"
            f"  • Recommendation: Verify that the strategies listed above are configured to consume all outputs from evidence '{evidence}'.\n"
        )


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
