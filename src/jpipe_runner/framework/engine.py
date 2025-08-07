import json
import logging
from pathlib import Path
from typing import Iterator, Callable, Any, Optional, Iterable, Tuple

import networkx as nx
import yaml

from .context import ctx, RuntimeContext
from .logger import GLOBAL_LOGGER
from .validators import MissingVariableValidator, OrderValidator, SelfDependencyValidator, JustificationSchemaValidator, \
    ProducedButNotConsumedValidator, DuplicateProducerValidator, EvidenceDependencyValidator
from ..GraphWorkflowVisualizer import GraphWorkflowVisualizer
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
        graph (nx.DiGraph): A directed graph representing dependencies between justification elements.
        justification_name (str): Human-readable name of the justification.
    """

    def __init__(self,
                 config_path: str,
                 justification_path: str,
                 mark_step: Callable[[Any, Any], None],
                 mark_substep: Callable[[str, str, str], None],
                 mark_node_as_graph: Callable[[str, str], None],
                 variables: Optional[Iterable[Tuple[str, Any]]] = None
                 ) -> None:
        """
        Initialize the PipelineEngine with a configuration file and a justification file.
        Loads configuration into ctx._vars["main"] and parses justification to build
        dependency graphs.

        :param config_path: Path to the YAML configuration file.
        :type config_path: str
        :param justification_path: Path to the justification file.
        :type justification_path: str
        :param mark_step: Function to mark workflow steps in the UI.
        :type mark_step: Callable[[Any, Any], None]
        :param mark_substep: Function to mark substeps in the UI.
        :type mark_substep: Callable[[str, str, str], None]
        :param mark_node_as_graph: Function to mark a node as a graph in the UI.
        :type mark_node_as_graph: Callable[[str, str], None]
        :param variables: Optional iterable of (name, value) pairs to set as context variables.
        :type variables: Optional[Iterable[Tuple[str, Any]]]
        """
        GLOBAL_LOGGER.info("Initializing PipelineEngine...")
        self.justification_name = "Unknown Justification"
        self.mark_step = mark_step
        self.mark_substep = mark_substep
        self.mark_node_as_graph = mark_node_as_graph
        self.mark_step(GraphWorkflowVisualizer.LOAD_CONFIGURATION, GraphWorkflowVisualizer.CURRENT)
        self.load_config(config_path, variables)
        self.mark_step(GraphWorkflowVisualizer.LOAD_CONFIGURATION, GraphWorkflowVisualizer.DONE)
        self.graph = self.parse_justification(justification_path)
        GLOBAL_LOGGER.debug("PipelineEngine initialized with context vars count: %d", len(ctx._vars))

    def load_config(self, path: str, variables: Optional[Iterable[Tuple[str, Any]]] = None) -> None:
        """
        Load the YAML configuration file and set the context variables in ctx._vars.
        Each key/value in the YAML is treated as a produced variable in the context.

        Errors during file reading or YAML parsing are logged but do not raise exceptions here.

        :param path: Path to the YAML configuration file.
        :type path: Path
        :param variables: Optional iterable of (name, value) pairs to override config values.
        :type variables: Optional[Iterable[Tuple[str, Any]]]
        """
        GLOBAL_LOGGER.info("Loading config from: %s", path)
        config = {}

        self.mark_substep(GraphWorkflowVisualizer.LOAD_CONFIGURATION, "Loading configuration file",
                          GraphWorkflowVisualizer.CURRENT)
        # Load YAML config if a path is provided
        if path:
            try:
                GLOBAL_LOGGER.info(f"Attempting to load configuration from {path}")
                with open(path, 'r') as f:
                    config = yaml.safe_load(f) or {}
                GLOBAL_LOGGER.info(f"Configuration loaded from {path}")
            except Exception as e:
                GLOBAL_LOGGER.error("Failed to load config from %s: %s", path, e)
                self.mark_substep(GraphWorkflowVisualizer.LOAD_CONFIGURATION, "Loading configuration file",
                                  GraphWorkflowVisualizer.FAIL)
                return

        # Override/add with CLI variables
        for key, value in (variables or []):
            if key in config:
                GLOBAL_LOGGER.warning("Overriding config key '%s' with variable value '%s'", key, value)
            config[key] = value

        # Set context variables
        try:
            GLOBAL_LOGGER.info("Loading configuration into context variables...")
            for key, value in config.items():
                ctx.set_from_config(key, value)
            GLOBAL_LOGGER.info("Context variables set successfully.")
        except Exception as e:
            GLOBAL_LOGGER.error("Failed to set context variables: %s", e)
            self.mark_substep(GraphWorkflowVisualizer.LOAD_CONFIGURATION, "Set context variables",
                              GraphWorkflowVisualizer.FAIL)
            return
        self.mark_substep(GraphWorkflowVisualizer.LOAD_CONFIGURATION, "Set context variables",
                          GraphWorkflowVisualizer.DONE)

    def parse_justification(self, path: str) -> nx.DiGraph:
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
            self.mark_step(GraphWorkflowVisualizer.LOAD_JUSTIFICATION_FILE, GraphWorkflowVisualizer.CURRENT)
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            GLOBAL_LOGGER.error("Failed to load JSON justification: %s", e)
            self.mark_step(GraphWorkflowVisualizer.LOAD_JUSTIFICATION_FILE, GraphWorkflowVisualizer.FAIL)
            return nx.DiGraph()

        self.mark_step(GraphWorkflowVisualizer.LOAD_JUSTIFICATION_FILE, GraphWorkflowVisualizer.DONE)

        # Validate the structure
        self.mark_step(GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE, GraphWorkflowVisualizer.CURRENT)
        try:
            GLOBAL_LOGGER.debug("Validating justification schema...")
            JustificationSchemaValidator(data, self.mark_substep).validate()
        except ValueError as e:
            GLOBAL_LOGGER.error("Justification validation failed: %s", e)
            self.mark_step(GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE, GraphWorkflowVisualizer.FAIL)
            return nx.DiGraph()

        self.mark_step(GraphWorkflowVisualizer.VALIDATE_JUSTIFICATION_FILE, GraphWorkflowVisualizer.DONE)
        self.mark_step(GraphWorkflowVisualizer.PARSE_JUSTIFICATION_GRAPH, GraphWorkflowVisualizer.CURRENT)

        # Check if the justification has a name
        self.mark_substep(
            GraphWorkflowVisualizer.PARSE_JUSTIFICATION_GRAPH,
            GraphWorkflowVisualizer.EXTRACTING_JUSTIFICATION_NAME,
            GraphWorkflowVisualizer.CURRENT
        )
        if "name" in data:
            self.justification_name = data["name"]
            GLOBAL_LOGGER.info("Justification name set to: %s", self.justification_name)

        self.mark_substep(
            GraphWorkflowVisualizer.PARSE_JUSTIFICATION_GRAPH,
            GraphWorkflowVisualizer.EXTRACTING_JUSTIFICATION_NAME,
            GraphWorkflowVisualizer.DONE
        )

        G = nx.DiGraph()

        # Add all nodes
        try:
            self.mark_substep(
                GraphWorkflowVisualizer.PARSE_JUSTIFICATION_GRAPH,
                GraphWorkflowVisualizer.ADDING_NODE_TO_GRAPH,
                GraphWorkflowVisualizer.CURRENT
            )
            for element in data.get("elements", []):
                G.add_node(element["id"], **element)
                fn_name = sanitize_string(element.get("label", ""))
                G.nodes[element["id"]]["function_name"] = fn_name

            self.mark_substep(
                GraphWorkflowVisualizer.PARSE_JUSTIFICATION_GRAPH,
                GraphWorkflowVisualizer.ADDING_NODE_TO_GRAPH,
                GraphWorkflowVisualizer.DONE
            )
        except KeyError as e:
            GLOBAL_LOGGER.error("Missing required key in justification elements: %s", e)
            self.mark_substep(
                GraphWorkflowVisualizer.PARSE_JUSTIFICATION_GRAPH,
                GraphWorkflowVisualizer.ADDING_NODE_TO_GRAPH,
                GraphWorkflowVisualizer.FAIL
            )
            return nx.DiGraph()

        try:
            # Add directed edges (dependencies)
            self.mark_substep(
                GraphWorkflowVisualizer.PARSE_JUSTIFICATION_GRAPH,
                GraphWorkflowVisualizer.ADDING_EDGES_TO_GRAPH,
                GraphWorkflowVisualizer.CURRENT
            )
            for rel in data.get("relations", []):
                G.add_edge(rel["source"], rel["target"])
            self.mark_substep(
                GraphWorkflowVisualizer.PARSE_JUSTIFICATION_GRAPH,
                GraphWorkflowVisualizer.ADDING_EDGES_TO_GRAPH,
                GraphWorkflowVisualizer.DONE
            )
        except KeyError as e:
            GLOBAL_LOGGER.error("Missing required key in justification relations: %s", e)
            self.mark_substep(
                GraphWorkflowVisualizer.PARSE_JUSTIFICATION_GRAPH,
                GraphWorkflowVisualizer.ADDING_EDGES_TO_GRAPH,
                GraphWorkflowVisualizer.FAIL
            )
            return nx.DiGraph()

        GLOBAL_LOGGER.info("Parsed %d nodes and %d relations into justification graph.", G.number_of_nodes(),
                           G.number_of_edges())

        self.mark_step(GraphWorkflowVisualizer.PARSE_JUSTIFICATION_GRAPH, GraphWorkflowVisualizer.DONE)
        return G

    @staticmethod
    def get_producer_key(var: str) -> str | None:
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
          2. Check that no function consumes a variable it itself produces (self-dependency) without an external source.
          3. Generate execution order and check ordering constraints via is_order_valid().
          4. Check that all produced variables are consumed by at least one function.
          5. Detect duplicate producers for the same variable.

        Logs detailed, multi-line error messages for missing variables or self-dependencies,
        and returns False if any validation step fails. If ordering fails, is_order_valid()
        logs detailed messages and validate returns False. On success, logs "Pipeline validation passed."

        :return: True if validation passes all checks, False otherwise.
        :rtype: bool
        """

        GLOBAL_LOGGER.info("Validating pipeline...")
        node = GraphWorkflowVisualizer.VALIDATE_PIPELINE

        validators = [
            (MissingVariableValidator(self, ctx), "Check for missing variables"),
            (SelfDependencyValidator(self, ctx), "Check for self-dependencies"),
            (OrderValidator(self, ctx), "Validate execution order"),
            (ProducedButNotConsumedValidator(self, ctx), "Check unused produced variables"),
            (DuplicateProducerValidator(self, ctx), "Detect duplicate producers"),
            (EvidenceDependencyValidator(self, ctx, self.graph), "Check evidence dependencies")
        ]

        all_passed = True
        all_errors = []
        all_warnings = []

        for validator, label in validators:
            self.mark_substep(node, label, GraphWorkflowVisualizer.CURRENT)
            errors, warnings = validator.validate()
            if errors or warnings:
                all_passed = False
                all_errors.extend(errors)
                all_warnings.extend(warnings)
                self.mark_substep(node, label, GraphWorkflowVisualizer.FAIL)
            else:
                self.mark_substep(node, label, GraphWorkflowVisualizer.DONE)

        if not all_passed:
            if all_warnings:
                GLOBAL_LOGGER.warning("\n".join(all_warnings))
            if all_errors:
                GLOBAL_LOGGER.error("\n".join(all_errors))
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

    # ------------ Start of Justification Pipeline Execution ------------

    def justify(self, runtime: PythonRuntime, dry_run: bool = False) -> Iterator[dict]:
        """
        Executes the justification pipeline based on a computed execution order of graph nodes.

        This method validates the graph, determines execution order, and processes each node
        based on its type and predecessors. Supports dry-run mode for simulation purposes.

        Each yielded result contains:
            - name: Node identifier in the graph.
            - label: Human-readable label of the node.
            - var_type: Node type (evidence, strategy, conclusion).
            - status: Execution status (PASS, FAIL, SKIP).
            - exception: Error message if the execution failed.

        Args:
            runtime (PythonRuntime): An instance used to dynamically call Python functions.
            dry_run (bool, optional): If True, skips actual function execution and marks as PASS. Defaults to False.

        Yields:
            dict: Execution result for each processed node.
        """
        GLOBAL_LOGGER.info("Running pipeline...")

        if not self._validate_pipeline():
            return

        execution_order = self._get_and_mark_execution_order()
        if not execution_order:
            return

        for node in execution_order:
            yield self._process_node(node, runtime, dry_run)

    def _validate_pipeline(self) -> bool:
        """
        Validates the justification graph and updates visualization markers accordingly.

        Marks the validation step as DONE or FAIL based on the result of `self.validate()`.

        Returns:
            bool: True if validation passes, False otherwise.
        """
        self.mark_step(GraphWorkflowVisualizer.VALIDATE_PIPELINE, GraphWorkflowVisualizer.CURRENT)
        if self.validate():
            self.mark_step(GraphWorkflowVisualizer.VALIDATE_PIPELINE, GraphWorkflowVisualizer.DONE)
            return True
        self.mark_step(GraphWorkflowVisualizer.VALIDATE_PIPELINE, GraphWorkflowVisualizer.FAIL)
        return False

    def _get_and_mark_execution_order(self) -> Optional[list]:
        """
        Retrieves and logs the execution order of nodes in the justification graph.

        Also marks visualization steps indicating whether the execution order retrieval succeeded or failed.

        Returns:
            list or None: Ordered list of node identifiers if successful, None if retrieval fails.
        """
        self.mark_step(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION, GraphWorkflowVisualizer.CURRENT)
        self.mark_substep(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION,
                          GraphWorkflowVisualizer.FETCH_EXECUTION_ORDER,
                          GraphWorkflowVisualizer.CURRENT)

        execution_order = self.get_execution_order()
        GLOBAL_LOGGER.debug("Execution order: %s", execution_order)

        if not execution_order:
            GLOBAL_LOGGER.error("No valid execution order found. Cannot proceed with justification.")
            self.mark_substep(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION,
                              GraphWorkflowVisualizer.FETCH_EXECUTION_ORDER,
                              GraphWorkflowVisualizer.FAIL)
            return None

        self.mark_substep(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION,
                          GraphWorkflowVisualizer.FETCH_EXECUTION_ORDER,
                          GraphWorkflowVisualizer.DONE)
        return execution_order

    def _process_node(self, node: str, runtime: PythonRuntime, dry_run: bool) -> dict:
        """
        Processes a single node in the justification graph according to its type and status.

        Evaluates predecessor node statuses to determine whether to execute, skip, or mark as failed.
        Calls a corresponding Python function using the provided runtime if applicable.

        Args:
            node (str): Node identifier.
            runtime (PythonRuntime): Runtime used to call functions dynamically.
            dry_run (bool): If True, function execution is skipped and marked as PASS.

        Returns:
            dict: Execution result with keys (name, label, var_type, status, exception).
        """
        node_data = self.graph.nodes[node]
        node_type = node_data.get("type")
        label = node_data.get("label")
        fn_name = sanitize_string(label)
        exception = None

        GLOBAL_LOGGER.debug("Processing node: %s", node)
        self._init_node_execution(label)

        # --- Check if this node should be skipped based on context ---
        skip_config = ctx._vars.get(fn_name, {}).get(RuntimeContext.SKIP, {})
        if skip_config.get("value", False):
            status = StatusType.SKIP
            exception = skip_config.get("reason", "Skipped by context")
            GLOBAL_LOGGER.info(f"Skipping function '{fn_name}' for node '{node}' due to context: {exception}")
            self.mark_substep(label, "status", GraphWorkflowVisualizer.SKIP)

        # --- Check if predecessor failure or implicit skip should block execution ---
        elif self._should_skip_due_to_predecessors(node):
            status = StatusType.SKIP
            self.mark_substep(label, "status", GraphWorkflowVisualizer.SKIP)


        # --- Attempt function execution (or dry-run) ---
        elif node_type in {"evidence", "strategy"}:
            status, exception = self._execute_justification_fn(label, fn_name, runtime, dry_run, node)


        # --- Default handling for conclusion nodes ---
        else:
            status = StatusType.PASS
            self.mark_substep(label, "status", GraphWorkflowVisualizer.DONE)

        # --- Append contribution loss message for skips or failures ---
        if status in {StatusType.SKIP, StatusType.FAIL}:
            contrib_msg = self._format_lost_contributions(fn_name)
            if contrib_msg:
                if exception:
                    exception += f" {contrib_msg}"
                else:
                    exception = contrib_msg

        # --- Finalize and mark execution status ---
        self._finalize_node_execution(node, label, status)

        return {
            "name": node,
            "label": label,
            "var_type": node_type,
            "status": status,
            "exception": exception,
        }

    def _should_skip_due_to_predecessors(self, node: str) -> bool:
        """
        Determines whether the current node should be skipped due to the status of its predecessors.

        A node will be skipped if any predecessor has:
            - status None (i.e., not executed),
            - status FAIL,
            - status SKIP not caused by an explicit skip (via ctx._vars).

        Args:
            node (str): The current node identifier.

        Returns:
            bool: True if the node should be skipped, False otherwise.
        """
        for pred in self.graph.predecessors(node):
            pred_data = self.graph.nodes[pred]
            status = pred_data.get("status")
            pred_label = pred_data.get("label")
            fn_name = sanitize_string(pred_label)

            if status is None or status == StatusType.FAIL:
                return True

            if status == StatusType.SKIP:
                skip_meta = ctx._vars.get(fn_name, {}).get(RuntimeContext.SKIP, {})
                if not skip_meta.get("value", False):  # not skipped via annotation
                    return True

        return False

    def _init_node_execution(self, label: str):
        """
        Initializes visualization markers and tracking for a node before execution.

        Args:
            label (str): Human-readable label of the node.
        """
        self.mark_substep(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION, label, GraphWorkflowVisualizer.CURRENT)
        self.mark_node_as_graph(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION, label)
        self.mark_substep(label, "status", GraphWorkflowVisualizer.CURRENT)

    def _execute_justification_fn(self, label: str, fn_name: str, runtime: PythonRuntime, dry_run: bool,
                                  node: str) -> tuple:
        """
        Executes the function corresponding to the justification node.

        Handles dry run logic, exception catching, result validation, and visualization step marking.

        Args:
            label (str): Human-readable node label.
            fn_name (str): Sanitized name of the function to call.
            runtime (PythonRuntime): Runtime used to invoke the function.
            dry_run (bool): Whether to simulate the run without executing the function.
            node (str): Node identifier in the graph.

        Returns:
            tuple: (status, exception) where status is a StatusType and exception is a string or None.
        """
        if dry_run:
            self.mark_substep(label, "status", GraphWorkflowVisualizer.DONE)
            return StatusType.PASS, None

        try:
            GLOBAL_LOGGER.debug("Calling function '%s' with runtime.", fn_name)
            self.mark_substep(label, GraphWorkflowVisualizer.CALL_FUNCTION, GraphWorkflowVisualizer.CURRENT)
            result = runtime.call_function(fn_name)
            self.mark_substep(label, GraphWorkflowVisualizer.CALL_FUNCTION, GraphWorkflowVisualizer.DONE)

            self.mark_substep(label, GraphWorkflowVisualizer.CHECK_RETURN_TYPE, GraphWorkflowVisualizer.CURRENT)

            if not isinstance(result, bool):
                raise FunctionException(
                    f"Function '{fn_name}' returned an unexpected type: {type(result).__name__}.\n"
                    f"  - The function associated with node '{node}' (label: '{label}') must return either True or False.\n"
                    f"  - Received: {result!r} ({type(result).__name__})\n"
                    f"  - Please ensure the function implementation returns a boolean to indicate pass/fail status correctly."
                )
            if not result:
                raise FunctionException(
                    f"\nFunction '{fn_name}' returned False, indicating failure.\n"
                    f"  - The function associated with node '{node}' (label: '{label}') executed but did not pass its check.\n"
                    f"  - Please review the implementation and input data for this function.\n"
                    f"  - Returned value: {result!r}\n"
                    f"  - The function must return True to indicate a successful check."
                )

            self.mark_substep(label, GraphWorkflowVisualizer.CHECK_RETURN_TYPE, GraphWorkflowVisualizer.DONE)
            return StatusType.PASS, None

        except Exception as e:
            self.mark_substep(label, GraphWorkflowVisualizer.CALL_FUNCTION, GraphWorkflowVisualizer.FAIL)
            self.mark_substep(label, GraphWorkflowVisualizer.CHECK_RETURN_TYPE, GraphWorkflowVisualizer.FAIL)
            return StatusType.FAIL, f"{type(e).__name__}: {e}"

    def _finalize_node_execution(self, node: str, label: str, status: str):
        """
        Finalizes the execution status of a node and updates visualization markers.

        Args:
            node (str): Node identifier.
            label (str): Human-readable label.
            status (str): Final execution status (PASS, FAIL, SKIP).
        """
        self.mark_substep(label, GraphWorkflowVisualizer.HANDLE_RESULT_STATUS, GraphWorkflowVisualizer.CURRENT)
        self.graph.nodes[node]["status"] = status

        visual_status = {
            StatusType.PASS: GraphWorkflowVisualizer.DONE,
            StatusType.SKIP: GraphWorkflowVisualizer.SKIP,
            StatusType.FAIL: GraphWorkflowVisualizer.FAIL,
        }[status]

        self.mark_substep(label, GraphWorkflowVisualizer.HANDLE_RESULT_STATUS, visual_status)
        self.mark_substep(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION, label, visual_status)

        if status == StatusType.FAIL:
            self.mark_step(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION, GraphWorkflowVisualizer.FAIL)

    @staticmethod
    def _format_lost_contributions(fn_name: str) -> Optional[str]:
        """
        Generates a message describing lost contributions due to skip/fail.

        Args:
            fn_name (str): Function name.

        Returns:
            str or None: A formatted warning message, or None if no contributions were declared.
        """
        contributions = ctx.get_contributions(fn_name)
        positive = contributions.get(RuntimeContext.POSITIVE, [])
        negative = contributions.get(RuntimeContext.NEGATIVE, [])

        if not positive and not negative:
            return None

        msg = []
        if positive:
            msg.append(f"Losing positive contribution to: {', '.join(positive)}.")
        if negative:
            msg.append(f"Losing negative contribution to: {', '.join(negative)}.")
        return " ".join(msg)

    # ------------ End of Justification Pipeline Execution ------------

    def export_to_format(self, status_dict: dict[str, str], output_path: str, filename: str, format: str) -> None:
        """
        Export the justification graph to any image format (png, svg, pdf etc), styling nodes by VariableType and edges by status.

        :param status_dict: Mapping node id -> status ("PASS", "FAIL", "SKIP")
        :param output_path: Path to save the exported graph image.
        """

        try:
            self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT,
                              GraphWorkflowVisualizer.IMPORTING_PYGRAPHVIZ,
                              GraphWorkflowVisualizer.CURRENT)
            from networkx.drawing.nx_agraph import to_agraph
            self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT,
                              GraphWorkflowVisualizer.IMPORTING_PYGRAPHVIZ,
                              GraphWorkflowVisualizer.DONE)
        except ImportError as e:
            self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT,
                              GraphWorkflowVisualizer.IMPORTING_PYGRAPHVIZ,
                              GraphWorkflowVisualizer.FAIL)
            raise ImportError("pygraphviz is required to enable this feature") from e

        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT,
                          GraphWorkflowVisualizer.PREPARE_OUTPUT_PATH,
                          GraphWorkflowVisualizer.CURRENT)

        # Prepare an output path
        output_path = Path(output_path)

        if output_path.exists():
            output_path = output_path / filename
        else:
            output_path.mkdir(parents=True, exist_ok=True)
            output_path = output_path / filename

        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT,
                          GraphWorkflowVisualizer.PREPARE_OUTPUT_PATH,
                          GraphWorkflowVisualizer.DONE)

        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT, GraphWorkflowVisualizer.PREPARE_STYLES,
                          GraphWorkflowVisualizer.CURRENT)
        # Mapping from VariableType to node attributes
        node_attr_map = {
            "conclusion": dict(fillcolor="lightgrey", shape="rect", style="filled"),
            "strategy": dict(fillcolor="palegreen", shape="parallelogram", style="filled"),
            "sub-conclusion": dict(color="dodgerblue", shape="rect"),
            "evidence": dict(fillcolor="lightskyblue2", shape="rect", style="filled"),
            "support": dict(fillcolor="lightcoral", shape="rect", style="filled"),
        }
        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT, GraphWorkflowVisualizer.PREPARE_STYLES,
                          GraphWorkflowVisualizer.DONE)

        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT, GraphWorkflowVisualizer.CREATE_GRAPH,
                          GraphWorkflowVisualizer.CURRENT)
        G = self.graph.copy()
        A = to_agraph(G)

        A.graph_attr.update(
            rankdir="BT",  # bottom-to-top layout
        )
        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT, GraphWorkflowVisualizer.CREATE_GRAPH,
                          GraphWorkflowVisualizer.DONE)

        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT, GraphWorkflowVisualizer.STYLE_NODES,
                          GraphWorkflowVisualizer.CURRENT)
        for node in G.nodes(data=True):
            node_id, attrs = node
            var_type = attrs.get("type", "").lower()

            # Apply node style based on VariableType
            style = node_attr_map.get(var_type, dict(fillcolor="white", shape="ellipse", style="filled"))
            n = A.get_node(node_id)
            for k, v in style.items():
                n.attr[k] = v

            # Add node border color based on status
            status = status_dict.get(node_id, "UNKNOWN")
            logging.info("Setting node color for %s with status %s", node_id, status)
            if status == StatusType.FAIL.name:
                n.attr["style"] = "filled"
                n.attr["fillcolor"] = "red"
                n.attr["fontcolor"] = "white"
                n.attr["fontname"] = "Helvetica-Bold"
            elif status == StatusType.SKIP.name:
                n.attr["style"] = "filled"
                n.attr["fillcolor"] = "#ff7d08"
                n.attr["fontcolor"] = "white"
                n.attr["fontname"] = "Helvetica-Bold"

        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT, GraphWorkflowVisualizer.STYLE_NODES,
                          GraphWorkflowVisualizer.DONE)
        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT, GraphWorkflowVisualizer.STYLE_EDGES,
                          GraphWorkflowVisualizer.CURRENT)
        # Color edges based on source node status
        for source, target in G.edges():
            status = status_dict.get(source, "UNKNOWN")
            logging.info("Setting edge color for %s -> %s with status %s", source, target, status)
            e = A.get_edge(source, target)

            if status == StatusType.PASS.name:
                e.attr['color'] = "black"
            elif status == StatusType.FAIL.name:
                e.attr['color'] = "red"
            elif status == StatusType.SKIP.name:
                e.attr['color'] = "#ff7d08"
            else:
                e.attr['color'] = "gray"
        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT, GraphWorkflowVisualizer.STYLE_EDGES,
                          GraphWorkflowVisualizer.DONE)

        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT, GraphWorkflowVisualizer.DRAW_GRAPH,
                          GraphWorkflowVisualizer.CURRENT)
        A.draw(output_path.with_suffix(f".{format}"), format=format, prog="dot")
        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT, GraphWorkflowVisualizer.DRAW_GRAPH,
                          GraphWorkflowVisualizer.DONE)
