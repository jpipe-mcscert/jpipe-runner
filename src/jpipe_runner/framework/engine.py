import json
import logging
from pathlib import Path
from typing import Iterator

import networkx as nx
import yaml

from .context import ctx, RuntimeContext
from .logger import GLOBAL_LOGGER
from .validators import MissingVariableValidator, OrderValidator, SelfDependencyValidator, JustificationSchemaValidator, \
    ProducedButNotConsumedValidator, DuplicateProducerValidator
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
        self.justification_name = "Unknown Justification"
        if config_path is None:
            GLOBAL_LOGGER.warning("No config path provided, using empty context.")
        else:
            self.load_config(config_path)
        self.graph = self.parse_justification(justification_path)
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
        except Exception as e:
            GLOBAL_LOGGER.error("Failed to load config from %s: %s", path, e)
            return
        try:
            for key, value in config.items():
                ctx.set_from_config(key, value)
        except Exception as e:
            GLOBAL_LOGGER.error("Failed to load config from %s: %s", path, e)
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
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            GLOBAL_LOGGER.error("Failed to load JSON justification: %s", e)
            return nx.DiGraph()

        # Validate the structure
        try:
            GLOBAL_LOGGER.debug("Validating justification schema...")
            JustificationSchemaValidator(data).validate()
        except ValueError as e:
            GLOBAL_LOGGER.error("Justification validation failed: %s", e)
            return nx.DiGraph()

        # Check if the justification has a name
        if "name" in data:
            self.justification_name = data["name"]
            GLOBAL_LOGGER.info("Justification name set to: %s", self.justification_name)

        G = nx.DiGraph()

        # Add all nodes
        for element in data.get("elements", []):
            G.add_node(element["id"], **element)

        # Add directed edges (dependencies)
        for rel in data.get("relations", []):
            G.add_edge(rel["source"], rel["target"])

        GLOBAL_LOGGER.info("Parsed %d nodes and %d relations into justification graph.", G.number_of_nodes(),
                           G.number_of_edges())

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
          2. Check that no function consumes a variable it itself produces (self-dependency) without external source.
          3. Generate execution order and check ordering constraints via is_order_valid().

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
        ]

        all_passed = True
        all_errors = []

        for validator in validators:
            errors = validator.validate()
            if errors:
                all_passed = False
                all_errors.extend(errors)

        if not all_passed:
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

        GLOBAL_LOGGER.debug("Execution order: %s", self.get_execution_order())
        for node in self.get_execution_order():
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
                        # if the result is something else than True or False, raise an exception
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

    def export_to_format(self, status_dict: dict[str, str], output_path: str, format: str) -> None:
        """
        Export the justification graph to SVG, styling nodes by VariableType and edges by status.

        :param status_dict: Mapping node id -> status ("PASS", "FAIL", "SKIP")
        :param output_path: Path to save SVG file.
        """

        try:
            from networkx.drawing.nx_agraph import to_agraph
        except ImportError as e:
            raise ImportError("pygraphviz is required to enable this feature") from e

        # Mapping from VariableType to node attributes
        node_attr_map = {
            "conclusion": dict(fillcolor="lightgrey", shape="rect", style="filled"),
            "strategy": dict(fillcolor="palegreen", shape="parallelogram", style="filled"),
            "sub-conclusion": dict(color="dodgerblue", shape="rect"),
            "evidence": dict(fillcolor="lightskyblue2", shape="rect", style="filled"),
            "support": dict(fillcolor="lightcoral", shape="rect", style="filled"),
        }

        G = self.graph.copy()
        A = to_agraph(G)

        A.graph_attr.update(
            dpi="100",
            rankdir="BT",  # bottom-to-top layout
            splines="spline",
            margin="0.2,0.2",
            size="15,15",
        )

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

        A.draw(output_path, format=format, prog="dot")
