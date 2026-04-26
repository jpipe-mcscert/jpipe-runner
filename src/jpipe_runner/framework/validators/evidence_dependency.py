import networkx as nx

from jpipe_runner.framework.context import RuntimeContext

from ..logger import GLOBAL_LOGGER
from .base import BaseValidator


class EvidenceDependencyValidator(BaseValidator):
    """
    Validates the dependency relationship between leaf nodes and strategy nodes.

    Specifically, it ensures that:
    1. Every evidence node produces at least one output variable.
    2. Every strategy node directly connected above a leaf node (evidence or bound
       sub-conclusion) consumes all variables produced by that leaf.
    """

    def __init__(
        self, pipeline: "PipelineEngine", ctx: "RuntimeContext", graph: nx.DiGraph
    ) -> None:
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
        Perform the validation of leaf-to-strategy variable dependencies.

        :return: A tuple of (errors, warnings).
        :rtype: tuple[list[str], list[str]]
        """
        GLOBAL_LOGGER.info("Running EvidenceDependencyValidator...")
        errors: list[str] = []
        warnings: list[str] = []

        leaf_strategy_edges = self._get_leaf_to_strategy_edges()

        for node_id, data in self.graph.nodes(data=True):
            node_type = data.get("type")
            fn_name = data.get("function_name")
            label = data.get("label", node_id)

            if node_type == "evidence":
                produced_vars = self._get_produced_variables(fn_name)
                if not produced_vars:
                    errors.append(self._create_no_variables_error(node_id, label))
                    continue
                connected = self._get_connected_strategies(fn_name, leaf_strategy_edges)
                errors.extend(
                    self._validate_strategy_consumption(node_id, label, produced_vars, connected)
                )

            elif node_type == "sub-conclusion" and self.ctx._vars.get(fn_name):
                produced_vars = self._get_produced_variables(fn_name)
                if produced_vars:
                    connected = self._get_connected_strategies(fn_name, leaf_strategy_edges)
                    errors.extend(
                        self._validate_strategy_consumption(node_id, label, produced_vars, connected)
                    )

        GLOBAL_LOGGER.info(
            f"EvidenceDependencyValidator completed with {len(errors)} error(s) and {len(warnings)} warning(s)."
        )
        return errors, warnings

    def _get_leaf_to_strategy_edges(self) -> list[tuple[str, str]]:
        """
        Return (leaf_fn_name, strategy_fn_name) for every direct edge where the predecessor
        is evidence or a bound sub-conclusion and the successor is a strategy.
        """
        LEAF_TYPES = {"evidence", "sub-conclusion"}
        edges = []
        for u, v in self.graph.edges():
            u_type = self.graph.nodes[u].get("type")
            v_type = self.graph.nodes[v].get("type")
            if u_type not in LEAF_TYPES or v_type != "strategy":
                continue
            u_fn = self.graph.nodes[u].get("function_name")
            # Sub-conclusions without a bound function (no ctx entry) are skipped
            if u_type == "sub-conclusion" and not self.ctx._vars.get(u_fn):
                continue
            edges.append((u_fn, self.graph.nodes[v].get("function_name")))
        return edges

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
    def _get_connected_strategies(
        leaf_fn: str, leaf_strategy_edges: list[tuple[str, str]]
    ) -> list[str]:
        """
        Get all strategy function names directly connected to a given leaf node.

        :param leaf_fn: The leaf function name.
        :param leaf_strategy_edges: All leaf-to-strategy edges.
        :return: List of strategy function names.
        :rtype: list[str]
        """
        return [strategy for lf, strategy in leaf_strategy_edges if lf == leaf_fn]

    def _validate_strategy_consumption(
        self, node_id: str, label: str, produced_vars: list[str], connected_strategies: list[str]
    ) -> list[str]:
        """
        Check that all connected strategies consume every variable produced by the leaf node.

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
            errors.append(
                self._create_consumption_error(node_id, label, produced_vars, non_consuming_strategies)
            )

        return errors

    @staticmethod
    def _create_no_variables_error(node_id: str, label: str) -> str:
        """
        Generate an error message for an evidence node that produces no variables.
        """
        return (
            "[EvidenceDependencyValidator]\n"
            "Pipeline validation error: evidence node does not produce any variables.\n"
            f"  • Element: {node_id} (\"{label}\") [evidence]\n"
            f"  • Problem: This evidence node produces no output variables.\n"
            f"  • Impact: Connected strategies will receive no inputs from this evidence.\n"
            f"  • Fix: Ensure the function bound to {node_id} calls produce(...) at least once.\n"
        )

    @staticmethod
    def _create_consumption_error(
        node_id: str, label: str, produced_vars: list[str], strategies: list[str]
    ) -> str:
        """
        Generate an error message when strategy nodes do not consume all variables
        produced by a leaf node.
        """
        strategy_list = "', '".join(strategies)
        return (
            "[EvidenceDependencyValidator]\n"
            "Pipeline validation error: leaf node variables not consumed by connected strategies.\n"
            f"  • Element: {node_id} (\"{label}\")\n"
            f"  • Produced variables: {produced_vars}\n"
            f"  • Affected strategies: ['{strategy_list}']\n"
            f"  • Problem: These strategies do not consume all variables produced by {node_id}.\n"
            f"  • Fix: Verify that the strategies listed above declare consume=[...] for all outputs of {node_id}.\n"
        )
