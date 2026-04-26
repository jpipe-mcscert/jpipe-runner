import json
import logging
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Tuple

import networkx as nx
import yaml

from ..enums import StatusType
from ..exceptions import FunctionException
from ..runtime import PythonRuntime
from ..utils import normalize_structure, parse_value, sanitize_string
from .context import RuntimeContext, ctx
from .logger import GLOBAL_LOGGER
from .validators import (
    DuplicateProducerValidator,
    EvidenceDependencyValidator,
    JustificationSchemaValidator,
    MissingVariableValidator,
    OrderValidator,
    ProducedButNotConsumedValidator,
    SelfDependencyValidator,
    UnboundElementValidator,
)


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

    def __init__(
        self,
        config_path: Optional[str],
        justification_path: Optional[str],
        variables: Optional[Iterable[str]] = None,
    ) -> None:
        """
        Initialize the PipelineEngine with a configuration file and a justification file.
        Loads configuration into ctx._vars["main"] and parses justification to build
        dependency graphs.

        :param config_path: Path to the YAML configuration file.
        :type config_path: Optional[str]
        :param justification_path: Path to the justification file.
        :type justification_path: Optional[str]
        :param variables: Optional iterable of (name, value) pairs to set as context variables.
        :type variables: Optional[Iterable[Tuple[str, Any]]]
        """
        GLOBAL_LOGGER.info("Initializing PipelineEngine...")
        self.justification_name = "Unknown Justification"
        self._link_registry: dict[str, str] = {}
        self.load_config(config_path, variables)
        if justification_path:
            self.graph = self.parse_justification(justification_path)
        else:
            self.graph = nx.DiGraph()
        GLOBAL_LOGGER.debug(
            "PipelineEngine initialized with context vars count: %d", len(ctx._vars)
        )

    @staticmethod
    def _parse_config(config: dict) -> dict:
        """Normalize YAML config values recursively."""
        return normalize_structure(config)

    @staticmethod
    def __parse_variables(
        variables: Optional[Iterable[str]],
    ) -> Optional[Iterable[Tuple[str, Any]]]:
        """Parse CLI variables (key:value) into native Python types."""
        parsed_variables = []
        for item in variables or []:
            if ":" in item:
                key, raw_value = item.split(":", maxsplit=1)
                value = parse_value(raw_value)
                parsed_variables.append((key, value))
        return parsed_variables

    def load_config(self, path: str, variables: Optional[Iterable[str]] = None) -> None:
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

        # Load YAML config if a path is provided
        if path:
            try:
                GLOBAL_LOGGER.info(f"Attempting to load configuration from {path}")
                with open(path, "r") as f:
                    config = yaml.safe_load(f) or {}
                config = self._parse_config(config)
                GLOBAL_LOGGER.info(f"Configuration loaded from {path}")
            except Exception as e:
                GLOBAL_LOGGER.error("Failed to load config from %s: %s", path, e)
                return

        if variables:
            variables = self.__parse_variables(variables)

        # Override/add with CLI variables
        for key, value in variables or []:
            if key in config:
                GLOBAL_LOGGER.warning(
                    "Overriding config key '%s' with variable value '%s'", key, value
                )
            config[key] = value

        # Set context variables
        try:
            GLOBAL_LOGGER.info("Loading configuration into context variables...")
            for key, value in config.items():
                ctx.set_from_config(key, value)
            GLOBAL_LOGGER.info("Context variables set successfully.")
        except Exception as e:
            GLOBAL_LOGGER.error("Failed to set context variables: %s", e)
            return

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

        data = self._load_justification_json(path)
        if data is None:
            return nx.DiGraph()

        try:
            GLOBAL_LOGGER.debug("Validating justification schema...")
            JustificationSchemaValidator(data).validate()
        except ValueError as e:
            GLOBAL_LOGGER.error("Justification validation failed: %s", e)
            return nx.DiGraph()

        if "name" in data:
            self.justification_name = data["name"]
            GLOBAL_LOGGER.info("Justification name set to: %s", self.justification_name)

        G = nx.DiGraph()

        if not self._add_nodes_to_graph(G, data):
            return nx.DiGraph()

        if not self._add_edges_to_graph(G, data):
            return nx.DiGraph()

        GLOBAL_LOGGER.info(
            "Parsed %d nodes and %d relations into justification graph.",
            G.number_of_nodes(),
            G.number_of_edges(),
        )
        return G

    def _load_justification_json(self, path: str) -> dict | None:
        """
        Load and parse the justification JSON file.

        :param path: Path to the JSON file.
        :return: Parsed JSON data as a dict, or None on failure.
        """
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return data
        except Exception as e:
            GLOBAL_LOGGER.error("Failed to load JSON justification: %s", e)
            return None

    def _add_nodes_to_graph(self, G: nx.DiGraph, data: dict) -> bool:
        """
        Add element nodes to the justification graph.

        :param G: The graph to populate.
        :param data: Parsed justification JSON.
        :return: True on success, False on KeyError.
        """
        try:
            for element in data.get("elements", []):
                G.add_node(element["id"], **element)
                G.nodes[element["id"]]["function_name"] = sanitize_string(
                    element.get("label", "")
                )
            return True
        except KeyError as e:
            GLOBAL_LOGGER.error("Missing required key in justification elements: %s", e)
            return False

    def _add_edges_to_graph(self, G: nx.DiGraph, data: dict) -> bool:
        """
        Add dependency edges to the justification graph.

        :param G: The graph to populate.
        :param data: Parsed justification JSON.
        :return: True on success, False on KeyError.
        """
        try:
            for rel in data.get("relations", []):
                G.add_edge(rel["source"], rel["target"])
            return True
        except KeyError as e:
            GLOBAL_LOGGER.error("Missing required key in justification relations: %s", e)
            return False

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

        validators = [
            MissingVariableValidator(self, ctx),
            SelfDependencyValidator(self, ctx),
            OrderValidator(self, ctx),
            ProducedButNotConsumedValidator(self, ctx),
            DuplicateProducerValidator(self, ctx),
            EvidenceDependencyValidator(self, ctx, self.graph),
            UnboundElementValidator(self, ctx, self._link_registry),
        ]

        all_passed = True
        all_errors = []
        all_warnings = []

        for validator in validators:
            errors, warnings = validator.validate()
            if errors or warnings:
                all_passed = False
                all_errors.extend(errors)
                all_warnings.extend(warnings)

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
        except nx.NetworkXUnfeasible:
            # Try to find the cycle for a more precise error message
            try:
                cycle = next(nx.simple_cycles(self.graph))
            except Exception:
                cycle = None

            if cycle:
                cycle_labels = [
                    f"{label} ({self._qualified_id(n)})"
                    if (label := self.graph.nodes[n].get("label"))
                    else self._qualified_id(n)
                    for n in cycle
                ]
                error_msg = (
                    "[ExecutionOrder]\n"
                    "Pipeline validation error: cycle detected in justification graph.\n"
                    f"  • The following elements form a cycle: {' -> '.join(cycle_labels)}\n"
                    "  • Problem: Cyclic dependencies prevent determining a valid execution order.\n"
                    "  • To fix:\n"
                    "    - Review the justification file and remove or break the cycle between these elements.\n"
                    "    - Ensure that dependencies flow in one direction only (no circular references).\n"
                    "  • After correcting the cycle, re-run the pipeline validation."
                )
            else:
                error_msg = (
                    "[ExecutionOrder]\n"
                    "Pipeline validation error: cycle detected in justification graph.\n"
                    "  • Problem: Cyclic dependencies prevent determining a valid execution order.\n"
                    "  • To fix: Review the justification file for circular dependencies and remove them."
                )
            GLOBAL_LOGGER.error(error_msg)
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

        self._apply_link_registry(runtime.build_link_registry())

        if not self._validate_pipeline():
            return

        execution_order = self._get_and_mark_execution_order()
        if not execution_order:
            return

        for node in execution_order:
            yield self._process_node(node, runtime, dry_run)

    def _apply_link_registry(self, registry: dict[str, str]) -> None:
        """
        Override the stored function_name for nodes that have an explicit @jpipe_link binding.

        Called before validation so that all downstream lookups (skip checks, contribution
        lookups, function dispatch) use the correct function name instead of the sanitized label.

        Supports two id formats:
        - Plain element id:              ``"e1"``
        - Qualified id with justification name: ``"performant:e1"``

        :param registry: Mapping of link_id → attr_name produced by runtime.build_link_registry().
        :type registry: dict[str, str]
        """
        self._link_registry = registry
        for link_id, attr_name in registry.items():
            node_id = self._resolve_node_id(link_id)
            if node_id is not None:
                GLOBAL_LOGGER.debug(
                    "Linking node '%s' to function '%s' via @jpipe_link.", node_id, attr_name
                )
                self.graph.nodes[node_id]["function_name"] = attr_name

    def _qualified_id(self, node_id: str) -> str:
        """Return the fully qualified node id (``justification_name:node_id``)."""
        return f"{self.justification_name}:{node_id}"

    def _resolve_node_id(self, link_id: str) -> str | None:
        """
        Resolve a @jpipe_link id to a graph node id.

        Accepts plain ids (``"e1"``) or qualified ids (``"justification_name:e1"``).
        For qualified ids the justification-name prefix must match this pipeline's name.

        :param link_id: The id value passed to @jpipe_link.
        :type link_id: str
        :return: The matching graph node id, or None if not found.
        :rtype: str | None
        """
        if link_id in self.graph.nodes:
            return link_id
        if ":" in link_id:
            qualifier, element_id = link_id.rsplit(":", 1)
            if qualifier == self.justification_name and element_id in self.graph.nodes:
                return element_id
        return None

    def _validate_pipeline(self) -> bool:
        """
        Validates the justification graph and updates visualization markers accordingly.

        Marks the validation step as DONE or FAIL based on the result of `self.validate()`.

        Returns:
            bool: True if validation passes, False otherwise.
        """
        return self.validate()

    def _get_and_mark_execution_order(self) -> Optional[list]:
        """
        Retrieves and logs the execution order of nodes in the justification graph.

        Also marks visualization steps indicating whether the execution order retrieval succeeded or failed.

        Returns:
            list or None: Ordered list of node identifiers if successful, None if retrieval fails.
        """
        execution_order = self.get_execution_order()
        GLOBAL_LOGGER.debug("Execution order: %s", execution_order)

        if not execution_order:
            GLOBAL_LOGGER.error(
                "No valid execution order found. Cannot proceed with justification."
            )
            return None

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
        fn_name = node_data.get("function_name")
        exception = None

        GLOBAL_LOGGER.debug("Processing node: %s", node)

        # --- Check if this node should be skipped based on context ---
        skip_config = ctx._vars.get(fn_name, {}).get(RuntimeContext.SKIP, {})
        if skip_config.get("value", False):
            status = StatusType.SKIP
            exception = skip_config.get("reason", "Skipped by context")
            GLOBAL_LOGGER.info(
                f"Skipping function '{fn_name}' for node '{self._qualified_id(node)}' due to context: {exception}"
            )

        # --- Check if predecessor failure or implicit skip should block execution ---
        elif self._should_skip_due_to_predecessors(node):
            status = StatusType.SKIP

        # --- Attempt function execution (or dry-run) ---
        elif node_type in {"evidence", "strategy"} or (
            node_type == "sub-conclusion" and node in self._link_registry
        ):
            status, exception = self._execute_justification_fn(
                label, fn_name, runtime, dry_run, node
            )

        # --- Default handling for conclusion and unbound sub-conclusion nodes ---
        else:
            status = StatusType.PASS

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
            fn_name = pred_data.get("function_name")

            if status is None or status == StatusType.FAIL:
                return True

            if status == StatusType.SKIP:
                skip_meta = ctx._vars.get(fn_name, {}).get(RuntimeContext.SKIP, {})
                if not skip_meta.get("value", False):  # not skipped via annotation
                    return True

        return False

    def _execute_justification_fn(
        self, label: str, fn_name: str, runtime: PythonRuntime, dry_run: bool, node: str
    ) -> tuple:
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
            return StatusType.PASS, None

        try:
            GLOBAL_LOGGER.debug("Calling function '%s' with runtime.", fn_name)
            result = runtime.call_function(fn_name)

            if not isinstance(result, bool):
                raise FunctionException(
                    f"Function '{fn_name}' returned an unexpected type: {type(result).__name__}.\n"
                    f"  - The function associated with node '{self._qualified_id(node)}' (label: '{label}') must return either True or False.\n"
                    f"  - Received: {result!r} ({type(result).__name__})\n"
                    f"  - Please ensure the function implementation returns a boolean to indicate pass/fail status correctly."
                )
            if not result:
                raise FunctionException(
                    f"\nFunction '{fn_name}' returned False, indicating failure.\n"
                    f"  - The function associated with node '{self._qualified_id(node)}' (label: '{label}') executed but did not pass its check.\n"
                    f"  - Please review the implementation and input data for this function.\n"
                    f"  - Returned value: {result!r}\n"
                    f"  - The function must return True to indicate a successful check."
                )

            return StatusType.PASS, None

        except Exception as e:
            return StatusType.FAIL, f"{type(e).__name__}: {e}"

    def _finalize_node_execution(self, node: str, label: str, status: str):
        """
        Finalizes the execution status of a node and updates visualization markers.

        Args:
            node (str): Node identifier.
            label (str): Human-readable label.
            status (str): Final execution status (PASS, FAIL, SKIP).
        """
        self.graph.nodes[node]["status"] = status

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

    def export_to_format(
        self, status_dict: dict[str, str], output_path: str, filename: str, format: str
    ) -> None:
        """
        Export the justification graph to any image format (png, svg, pdf etc),
        styling nodes by VariableType and edges by status.

        :param status_dict: Mapping node id -> status ("PASS", "FAIL", "SKIP")
        :param output_path: Directory path to save the exported graph image.
        :param filename: Output filename (without extension).
        :param format: Image format string (e.g. "png", "svg", "pdf").
        """
        import graphviz as gv

        resolved_path = self._resolve_output_path(output_path, filename)

        G = self.graph.copy()
        dot = gv.Digraph()
        dot.attr(rankdir="BT")

        self._style_nodes(dot, G, status_dict)
        self._style_edges(dot, G, status_dict)

        dot.render(
            str(resolved_path),
            format=format,
            engine="dot",
            cleanup=True,
            outfile=str(resolved_path.with_suffix(f".{format}")),
        )

    @staticmethod
    def _resolve_output_path(output_path: str, filename: str) -> Path:
        """
        Resolve and prepare the output file path, creating the directory if needed.

        :param output_path: Directory path for the output file.
        :param filename: Output filename (without extension).
        :return: Full Path object pointing to the output file location.
        """
        path = Path(output_path)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
        return path / filename

    @staticmethod
    def _style_nodes(dot: Any, G: nx.DiGraph, status_dict: dict[str, str]) -> None:
        """
        Apply visual styles to graph nodes based on their type and execution status.

        :param dot: graphviz.Digraph instance to add nodes to.
        :param G: NetworkX DiGraph with node attribute data.
        :param status_dict: Mapping of node id -> status string ("PASS", "FAIL", "SKIP").
        """
        node_attr_map = {
            "conclusion":     {"shape": "rect",    "style": "filled,rounded", "fillcolor": "lightgrey"},
            "sub-conclusion": {"shape": "rect",    "color": "#0072B2"},
            "strategy":       {"shape": "hexagon", "style": "filled",         "fillcolor": "#F0C27F"},
            "evidence":       {"shape": "note",    "style": "filled",         "fillcolor": "#9ECAE1"},
            "support":        {"shape": "rect",    "style": "dotted"},
        }
        for node_id, attrs in G.nodes(data=True):
            var_type = attrs.get("type", "").lower()
            style = dict(node_attr_map.get(
                var_type, dict(fillcolor="white", shape="ellipse", style="filled")
            ))

            status = status_dict.get(node_id, "UNKNOWN")
            logging.info("Setting node color for %s with status %s", node_id, status)
            if status == StatusType.FAIL.name:
                style.update(style="filled", fillcolor="red", fontcolor="white", fontname="Helvetica-Bold")
            elif status == StatusType.SKIP.name:
                style.update(style="filled", fillcolor="#cccccc", opacity="1", fontcolor="white", fontname="Helvetica-Bold")

            label = attrs.get("label", node_id)
            dot.node(node_id, label=label, **style)

    @staticmethod
    def _style_edges(dot: Any, G: nx.DiGraph, status_dict: dict[str, str]) -> None:
        """
        Apply visual styles to graph edges based on the execution status of their source node.

        :param dot: graphviz.Digraph instance to add edges to.
        :param G: NetworkX DiGraph with edge data.
        :param status_dict: Mapping of node id -> status string ("PASS", "FAIL", "SKIP").
        """
        for source, target in G.edges():
            status = status_dict.get(source, "UNKNOWN")
            logging.info("Setting edge color for %s -> %s with status %s", source, target, status)
            if status == StatusType.PASS.name:
                dot.edge(source, target, color="black")
            elif status == StatusType.FAIL.name:
                dot.edge(source, target, color="red")
            elif status == StatusType.SKIP.name:
                dot.edge(source, target, color="#cccccc", opacity="1")
            else:
                dot.edge(source, target, color="gray")
