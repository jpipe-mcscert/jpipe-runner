import json
from pathlib import Path
from typing import Iterator

import networkx as nx
import yaml

from .context import ctx, RuntimeContext
from .logger import GLOBAL_LOGGER
from ..enums import StatusType
from ..exceptions import FunctionException
from ..runtime import PythonRuntime
from ..utils import sanitize_string


class PipelineEngine:
    """
    Orchestrates the loading, validation, and execution of a pipeline based on a justification graph.

    Responsibilities:
    - Load configuration and justification files
    - Construct and validate dependency graphs
    - Ensure proper execution order of functions
    - Execute functions using a provided runtime

    Attributes:
        execution_order (list[str]): The topologically sorted order of functions to execute.
        graph (nx.DiGraph): A directed graph representing dependencies between justification elements.
        justification_name (str): Human-readable name of the justification.
    """

    def __init__(self, config_path: str, justification_path: str) -> None:
        """
        Initialize the PipelineEngine with a configuration file and a justification file.
        Loads configuration into ctx._vars["main"] and parses justification to build
        dependency graphs.

        :param config_path: Path to the YAML configuration file.
        :type config_path: str
        :param justification_path: Path to the justification file.
        :type justification_path: str
        """
        GLOBAL_LOGGER.info("Initializing PipelineEngine...")
        self.execution_order: list[str] = []
        if config_path is None:
            GLOBAL_LOGGER.warning("No config path provided, using empty context.")
        else:
            self.load_config(config_path)
        self.graph = self.parse_justification(justification_path)
        self.justification_name = self.graph.graph.get("name", "Unnamed Justification")
        GLOBAL_LOGGER.debug("PipelineEngine initialized with context vars count: %d", len(ctx._vars))

    @staticmethod
    def load_config(path: str) -> None:
        """
        Load the YAML configuration file and set the context variables in ctx._vars.
        Each key/value in the YAML is treated as a produced variable in the context.

        Errors during file reading or YAML parsing are logged but do not raise exceptions here.

        :param path: Path to the YAML configuration file.
        :type path: Path
        """
        GLOBAL_LOGGER.info("Loading config from: %s", path)
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
                for key, value in config.items():
                    ctx.set_from_config(key, value)
        except Exception as e:
            GLOBAL_LOGGER.error("Failed to load config from %s: %s", path, e)
            return

    @staticmethod
    def parse_justification(path: str) -> nx.DiGraph:
        """
        Parse a justification JSON file into a directed graph of pipeline elements.

        Graph nodes represent justification elements (e.g., evidence, strategy).
        Graph edges represent logical dependencies between elements.

        :param path: Path to the justification JSON file.
        :type path: str
        :return: A directed graph (DiGraph) representing the justification.
        :rtype: nx.DiGraph
        """
        GLOBAL_LOGGER.info("Parsing justification JSON from: %s", path)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            GLOBAL_LOGGER.error("Failed to load JSON justification: %s", e)
            return nx.DiGraph()

        G = nx.DiGraph()

        # Add all nodes (you can store attributes if needed)
        for element in data.get("elements", []):
            G.add_node(element["id"], **element)

        # Add directed edges (dependencies)
        for rel in data.get("relations", []):
            G.add_edge(rel["source"], rel["target"])

        GLOBAL_LOGGER.info("Parsed %d nodes and %d relations into justification graph.", G.number_of_nodes(),
                           G.number_of_edges())

        return G

    @staticmethod
    def _get_producer_key(var: str) -> str | None:
        """
        Determine which function or context produces a given variable.

        :param var: Variable name to locate.
        :type var: str
        :return: Function key, or None if not found.
        :rtype: str | None
        """
        # Check other functions in ctx._vars
        for func_key, var_maps in ctx._vars.items():
            produce_vars = var_maps.get(RuntimeContext.PRODUCE, {})
            if var in produce_vars:
                return func_key
        return None

    def validate(self) -> bool:
        """
        Validate the pipeline by performing:
          1. Check that all consumed variables are available in context or produced by another function.
          2. Check that no function consumes a variable it itself produces (self-dependency) without external source.
          3. Generate execution order and check ordering constraints via is_order_valid().

        Logs detailed, multi-line error messages for missing variables or self-dependencies,
        and returns False if any validation step fails. If ordering fails, is_order_valid()
        logs detailed messages and validate returns False. On success, logs "Pipeline validation passed."

        :return: True if validation passes all checks, False otherwise.
        :rtype: bool
        """
        GLOBAL_LOGGER.info("Validating pipeline...")
        errors: list[str] = []

        # Step 1: Check availability & self-dependency
        for func_key, var_maps in ctx._vars.items():
            consume_vars = var_maps.get(RuntimeContext.CONSUME, ())
            for key, value in consume_vars.items():
                if value is not None:
                    continue
                producer_key = self._get_producer_key(key)
                # Missing entirely
                if producer_key is None:
                    errors.append(self._format_missing_var_error(func_key, key))
                # Self-dependency
                elif producer_key == func_key:
                    errors.append(self._format_self_dependency_error(func_key, key))

        if errors:
            combined = "\n".join(errors)
            order_hint = " -> ".join(
                self.execution_order) if self.execution_order else "(execution order not yet generated)"
            combined += f"\nCurrent execution order (keys): {order_hint}\nPlease correct the above issues before proceeding."
            GLOBAL_LOGGER.error(combined)
            return False

        # Step 2: Generate execution order and check ordering
        self.execution_order = self.get_execution_order()
        if not self.is_order_valid():
            GLOBAL_LOGGER.error("Pipeline validation error: execution order is invalid. See previous details.")
            return False

        GLOBAL_LOGGER.info("Pipeline validation passed.")
        return True

    def get_execution_order(self) -> list[str]:
        """
        Compute a valid execution order using topological sorting.

        :return: A list of node keys in execution order.
        :rtype: list[str]
        """
        try:
            order = list(nx.topological_sort(self.graph))
            GLOBAL_LOGGER.info("Execution order: %s", order)
            return order
        except nx.NetworkXUnfeasible as e:
            GLOBAL_LOGGER.error("Cycle detected in justification graph: %s", e)
            return []

    def is_order_valid(self) -> bool:
        """
        Check that the computed execution order satisfies variable dependency rules.

        Specifically ensures:
        - Producers appear before consumers.
        - No invalid forward references or cycles exist.

        :return: True if the order is valid, False otherwise.
        :rtype: bool
        """
        GLOBAL_LOGGER.info("Validating execution order...")
        order_index = {key: idx for idx, key in enumerate(self.execution_order)}

        for func_key in self.execution_order:
            consume_vars = ctx._vars.get(func_key, {}).get(RuntimeContext.CONSUME, ())
            for var in consume_vars:
                producer_func_key = self._get_producer_key(var)
                if producer_func_key is None:
                    continue

                if producer_func_key == func_key:
                    GLOBAL_LOGGER.error(self.format_self_dep_in_order(func_key, var, self.execution_order))
                    return False

                idx_consumer = order_index.get(func_key)
                idx_producer = order_index.get(producer_func_key)

                if idx_consumer is None or idx_producer is None:
                    GLOBAL_LOGGER.debug(
                        "Skipping ordering check for var '%s': cannot find indices for '%s' or '%s' in execution order.",
                        var, func_key, producer_func_key
                    )
                    continue

                if idx_producer >= idx_consumer:
                    GLOBAL_LOGGER.error(
                        self.format_order_violation(
                            func_key, producer_func_key, var,
                            idx_consumer, idx_producer,
                            self.execution_order
                        )
                    )
                    return False

        return True

    def justify(self, runtime: PythonRuntime, dry_run: bool = False) -> Iterator[dict]:
        """
        Execute the pipeline based on the computed execution order.

        Execution can be skipped using `dry_run=True`. Function failures result in `FAIL` status.

        Each yielded dictionary represents the result for a justification element:
            - name: element ID
            - label: human-readable name
            - var_type: type (e.g., evidence, strategy, conclusion)
            - status: execution status (PASS, FAIL, SKIP)
            - exception: error message if applicable

        :param runtime: A PythonRuntime instance to call functions from.
        :type runtime: PythonRuntime
        :param dry_run: If True, skips actual function calls and marks all as PASS.
        :type dry_run: bool
        :yield: Execution results for each node.
        :rtype: Iterator[dict]
        """
        GLOBAL_LOGGER.info("Running pipeline...")

        self.validate()

        GLOBAL_LOGGER.debug("Execution order: %s", self.execution_order)
        for node in self.execution_order:
            GLOBAL_LOGGER.debug("Processing node: %s", node)
            node_data = self.graph.nodes[node]
            node_type = node_data.get("type")
            label = node_data.get("label")
            fn_name = sanitize_string(label)
            exception = None

            # Get statuses of predecessor nodes
            pre_statuses = [self.graph.nodes[pred].get("status") for pred in self.graph.predecessors(node)]

            # If any predecessor failed or hasn't run, skip this node
            if None in pre_statuses or not all(status == StatusType.PASS for status in pre_statuses):
                status = StatusType.SKIP
            elif node_type in {"evidence", "strategy"}:
                if dry_run:
                    status = StatusType.PASS
                else:
                    try:
                        GLOBAL_LOGGER.debug("Calling function '%s' with runtime.", fn_name)
                        result = runtime.call_function(fn_name)
                        GLOBAL_LOGGER.debug("Function '%s' returned: %s", fn_name, result)
                        if not result:
                            raise FunctionException(f"Function '{fn_name}' returned false: {result}")
                        status = StatusType.PASS
                    except Exception as e:
                        status = StatusType.FAIL
                        exception = f"{type(e).__name__}: {e}"
            else:
                # conclusion or sub-conclusion
                status = StatusType.PASS

            # Store back into graph for later reference (e.g., by other justifications)
            node_data["status"] = status

            # Yield with expected format
            yield {
                "name": node,
                "label": label,
                "var_type": node_type,
                "status": status,
                "exception": exception,
            }

    @staticmethod
    def _format_missing_var_error(func_key: str, var: str) -> str:
        """
        Format a multi-line error message when a function consumes a variable that has no producer
        and is not provided in the 'main' context.

        :param func_key: The function key that consumes the missing variable.
        :type func_key: str
        :param var: The missing variable name.
        :type var: str
        :return: A formatted error message explaining the missing variable issue.
        :rtype: str
        """
        return (
            "Pipeline validation error: missing variable.\n"
            f"  • Function '{func_key}' declares that it consumes variable '{var}',\n"
            "    but no producer for this variable is found in the pipeline,\n"
            "    nor is it provided in the 'main' context.\n"
            "  • To fix:\n"
            f"    - Ensure that some earlier function produces '{var}', or\n"
            "    - Provide '{var}' via config/context,\n"
            f"    so that '{func_key}' can consume it.\n"
        )

    @staticmethod
    def _format_self_dependency_error(func_key: str, var: str) -> str:
        """
        Format a multi-line error message when a function consumes and produces the same variable,
        indicating a self-dependency misconfiguration.

        :param func_key: The function key that has the self-dependency.
        :type func_key: str
        :param var: The variable name that is both consumed and produced.
        :type var: str
        :return: A formatted error message explaining the self-dependency issue.
        :rtype: str
        """
        return (
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

    @staticmethod
    def format_self_dep_in_order(func_key: str, var: str, execution_order: list[str]) -> str:
        """
        Format an error message for a self-dependency detected in pipeline ordering.

        This is used when a function declares that it both consumes and produces the same variable,
        which is typically a misconfiguration in the pipeline dependency graph.

        :param func_key: The key/identifier of the function in the pipeline.
        :type func_key: str
        :param var: The name of the variable that is both consumed and produced by the same function.
        :type var: str
        :param execution_order: The current execution order (list of function keys) used in the pipeline.
        :type execution_order: list[str]
        :return: A multi-line formatted error message explaining the self-dependency issue,
                 showing the function key, variable name, and the current execution order.
        :rtype: str
        """
        return (
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
        ).format(func=func_key, var=var, order=" -> ".join(execution_order))

    @staticmethod
    def format_order_violation(func_key: str,
                               producer_key: str,
                               var: str,
                               idx_consumer: int,
                               idx_producer: int,
                               execution_order: list[str]) -> str:
        """
        Format an error message for an execution order violation in the pipeline.

        This occurs when a function consumes a variable that is produced by another function,
        but in the current execution order, the producer is scheduled at or after the consumer.

        :param func_key: The key/identifier of the consuming function.
        :type func_key: str
        :param producer_key: The key/identifier of the producing function.
        :type producer_key: str
        :param var: The variable name being consumed/produced.
        :type var: str
        :param idx_consumer: The index of the consuming function in the execution order.
        :type idx_consumer: int
        :param idx_producer: The index of the producing function in the execution order.
        :type idx_producer: int
        :param execution_order: The current execution order (list of function keys).
        :type execution_order: list[str]
        :return: A multi-line formatted error message explaining the ordering violation,
                 showing consumer index, producer index, variable name, and the full current order,
                 along with a suggestion to fix the ordering.
        :rtype: str
        """
        return (
            "Pipeline execution order violation detected:\n"
            "  • Function '{consumer}' (index {idx_consumer}) consumes variable '{var}',\n"
            "    but that variable is produced by function '{producer}' (index {idx_producer}),\n"
            "    which is scheduled to run at or after the consumer.\n"
            "  • To fix this, ensure that '{producer}' runs before '{consumer}' in the pipeline justification/config.\n"
            "  • Current execution order (keys) is:\n"
            "      {order}\n"
            "  • Suggestion: adjust dependencies/justification so that '{producer}' precedes '{consumer}'."
        ).format(
            consumer=func_key,
            idx_consumer=idx_consumer,
            var=var,
            producer=producer_key,
            idx_producer=idx_producer,
            order=" -> ".join(execution_order)
        )
