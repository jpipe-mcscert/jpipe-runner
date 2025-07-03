import json
import logging
from pathlib import Path
from typing import Iterator, Callable, Any, Optional, Iterable, Tuple

import networkx as nx
import yaml

from .context import ctx, RuntimeContext
from .logger import GLOBAL_LOGGER
from .validators import MissingVariableValidator, OrderValidator, SelfDependencyValidator, JustificationSchemaValidator, \
    ProducedButNotConsumedValidator, DuplicateProducerValidator
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
                 variables: Optional[Iterable[Tuple[str, str]]] = None
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
        :param variables: Optional iterable of (key, value) pairs to set in ctx._vars["main"].
        :type variables: Optional[Iterable[Tuple[str, str]]]
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

    def load_config(self, path: str, variables: Optional[Iterable[Tuple[str, str]]] = None) -> None:
        """
        Load the YAML configuration file and set the context variables in ctx._vars.
        Each key/value in the YAML is treated as a produced variable in the context.

        Errors during file reading or YAML parsing are logged but do not raise exceptions here.

        :param path: Path to the YAML configuration file.
        :type path: Path
        """
        GLOBAL_LOGGER.info("Loading config from: %s", path)
        config = {}
        if path is not None:
            try:
                self.mark_substep(GraphWorkflowVisualizer.LOAD_CONFIGURATION,
                                  "Loading configuration file",
                                  GraphWorkflowVisualizer.CURRENT)
                with open(path, 'r') as f:
                    config = yaml.safe_load(f)
            except Exception as e:
                GLOBAL_LOGGER.error("Failed to load config from %s: %s", path, e)
                self.mark_substep(GraphWorkflowVisualizer.LOAD_CONFIGURATION, "Loading configuration file",
                                  GraphWorkflowVisualizer.FAIL)
                return
        else:
            GLOBAL_LOGGER.warning("No config path provided, using empty context.")

        self.mark_substep(GraphWorkflowVisualizer.LOAD_CONFIGURATION,
                          "Adding variables to context.",
                          GraphWorkflowVisualizer.CURRENT)
        # If variables are provided, use them to set context variables
        for k, v in (variables or []):
            config[k] = v

        self.mark_substep(GraphWorkflowVisualizer.LOAD_CONFIGURATION,
                          "Adding variables to context.",
                          GraphWorkflowVisualizer.DONE)

        try:
            self.mark_substep(GraphWorkflowVisualizer.LOAD_CONFIGURATION, "Set context variables",
                              GraphWorkflowVisualizer.CURRENT)
            for key, value in config.items():
                ctx.set_from_config(key, value)
        except Exception as e:
            GLOBAL_LOGGER.error("Failed to load config from %s: %s", path, e)
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
          2. Check that no function consumes a variable it itself produces (self-dependency) without external source.
          3. Generate execution order and check ordering constraints via is_order_valid().

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
        ]

        all_passed = True
        all_errors = []

        for validator, label in validators:
            self.mark_substep(node, label, GraphWorkflowVisualizer.CURRENT)
            errors = validator.validate()
            if errors:
                all_passed = False
                all_errors.extend(errors)
                self.mark_substep(node, label, GraphWorkflowVisualizer.FAIL)
            else:
                self.mark_substep(node, label, GraphWorkflowVisualizer.DONE)

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

        self.mark_step(GraphWorkflowVisualizer.VALIDATE_PIPELINE, GraphWorkflowVisualizer.CURRENT)
        validate_status = self.validate()
        if validate_status:
            self.mark_step(GraphWorkflowVisualizer.VALIDATE_PIPELINE, GraphWorkflowVisualizer.DONE)
        else:
            self.mark_step(GraphWorkflowVisualizer.VALIDATE_PIPELINE, GraphWorkflowVisualizer.FAIL)

        self.mark_step(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION, GraphWorkflowVisualizer.CURRENT)
        self.mark_substep(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION, GraphWorkflowVisualizer.FETCH_EXECUTION_ORDER,
                          GraphWorkflowVisualizer.CURRENT)
        execution_order = self.get_execution_order()
        GLOBAL_LOGGER.debug("Execution order: %s", execution_order)
        if not execution_order:
            GLOBAL_LOGGER.error("No valid execution order found. Cannot proceed with justification.")
            self.mark_substep(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION,
                              GraphWorkflowVisualizer.FETCH_EXECUTION_ORDER, GraphWorkflowVisualizer.FAIL)
        else:
            self.mark_substep(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION,
                              GraphWorkflowVisualizer.FETCH_EXECUTION_ORDER, GraphWorkflowVisualizer.DONE)

        for node in execution_order:
            GLOBAL_LOGGER.debug("Processing node: %s", node)
            node_data = self.graph.nodes[node]
            node_type = node_data.get("type")
            label = node_data.get("label")
            fn_name = sanitize_string(label)
            exception = None

            # Create a subgraph for the node
            self.mark_substep(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION, label, GraphWorkflowVisualizer.CURRENT)
            self.mark_node_as_graph(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION, label)

            # Create internal steps for this justification node
            self.mark_substep(label, "status", GraphWorkflowVisualizer.CURRENT)

            # Get statuses of predecessor nodes
            pre_statuses = [self.graph.nodes[pred].get("status") for pred in self.graph.predecessors(node)]

            # If any predecessor failed or hasn't run, skip this node
            if None in pre_statuses or not all(status == StatusType.PASS for status in pre_statuses):
                status = StatusType.SKIP
                self.mark_substep(label, "status", GraphWorkflowVisualizer.SKIP)
            elif node_type in {"evidence", "strategy"}:
                if dry_run:
                    status = StatusType.PASS
                    self.mark_substep(label, "status", GraphWorkflowVisualizer.DONE)
                else:
                    try:
                        GLOBAL_LOGGER.debug("Calling function '%s' with runtime.", fn_name)
                        self.mark_substep(label, GraphWorkflowVisualizer.CALL_FUNCTION, GraphWorkflowVisualizer.CURRENT)
                        result = runtime.call_function(fn_name)
                        GLOBAL_LOGGER.debug("Function '%s' returned: %s", fn_name, result)
                        self.mark_substep(label, GraphWorkflowVisualizer.CALL_FUNCTION, GraphWorkflowVisualizer.DONE)

                        self.mark_substep(label, GraphWorkflowVisualizer.CHECK_RETURN_TYPE,
                                          GraphWorkflowVisualizer.CURRENT)

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
                        self.mark_substep(label, GraphWorkflowVisualizer.CHECK_RETURN_TYPE,
                                          GraphWorkflowVisualizer.DONE)
                    except Exception as e:
                        status = StatusType.FAIL
                        exception = f"{type(e).__name__}: {e}"
                        self.mark_substep(label, GraphWorkflowVisualizer.CALL_FUNCTION, GraphWorkflowVisualizer.FAIL)
                        self.mark_substep(label, GraphWorkflowVisualizer.CHECK_RETURN_TYPE,
                                          GraphWorkflowVisualizer.FAIL)
            else:
                # conclusion or sub-conclusion
                status = StatusType.PASS
                self.mark_substep(label, "status", GraphWorkflowVisualizer.DONE)

            # Handle final result
            self.mark_substep(label, GraphWorkflowVisualizer.HANDLE_RESULT_STATUS, GraphWorkflowVisualizer.CURRENT)
            node_data["status"] = status
            self.mark_substep(label, GraphWorkflowVisualizer.HANDLE_RESULT_STATUS,
                              GraphWorkflowVisualizer.DONE if status == StatusType.PASS else
                              GraphWorkflowVisualizer.SKIP if status == StatusType.SKIP else GraphWorkflowVisualizer.FAIL)

            self.mark_substep(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION, label,
                              GraphWorkflowVisualizer.DONE if status == StatusType.PASS else
                              GraphWorkflowVisualizer.SKIP if status == StatusType.SKIP else GraphWorkflowVisualizer.FAIL)

            if status == StatusType.FAIL:
                self.mark_step(GraphWorkflowVisualizer.EXECUTE_JUSTIFICATION, GraphWorkflowVisualizer.FAIL)

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
            dpi="100",
            rankdir="BT",  # bottom-to-top layout
            splines="spline",
            margin="0.2,0.2",
            size="15,15",
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
        A.draw(output_path, format=format, prog="dot")
        self.mark_substep(GraphWorkflowVisualizer.EXPORT_OUTPUT, GraphWorkflowVisualizer.DRAW_GRAPH,
                          GraphWorkflowVisualizer.DONE)
