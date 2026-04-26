from ..logger import GLOBAL_LOGGER
from .base import BaseValidator


class UnboundElementValidator(BaseValidator):
    """
    Validates that every evidence and strategy node in the pipeline has an explicit
    @jpipe_link binding. Nodes relying on the sanitized-label fallback are rejected.
    """

    EXECUTABLE_TYPES = {"evidence", "strategy"}

    def __init__(self, pipeline: "PipelineEngine", ctx: "RuntimeContext", registry: dict[str, str]) -> None:
        """
        Initialize the validator.

        :param pipeline: The pipeline engine being validated.
        :param ctx: The runtime context.
        :param registry: Mapping of element_id → function_name produced by build_link_registry().
        """
        super().__init__(pipeline, ctx)
        self.registry = registry

    def _is_bound(self, node_id: str) -> bool:
        return (
            node_id in self.registry
            or f"{self.pipeline.justification_name}:{node_id}" in self.registry
        )

    def validate(self) -> tuple[list[str], list[str]]:
        """
        Validate that every executable node has an explicit @jpipe_link binding.

        :return: A tuple of (errors, warnings).
        :rtype: tuple[list[str], list[str]]
        """
        GLOBAL_LOGGER.info("Running UnboundElementValidator...")
        for node_id, data in self.pipeline.graph.nodes(data=True):
            if data.get("type") not in self.EXECUTABLE_TYPES:
                continue
            if not self._is_bound(node_id):
                label = data.get("label", node_id)
                node_type = data.get("type")
                self.errors.append(
                    "[UnboundElementValidator]\n"
                    "Pipeline validation error: unbound pipeline element.\n"
                    f"  • Element: {node_id} (\"{label}\") [{node_type}]\n"
                    f"  • Problem: No @jpipe_link(\"{node_id}\") decorator was found in any loaded module.\n"
                    f"  • Fix: Add @jpipe_link(\"{node_id}\") to the function that implements this element.\n"
                )
        GLOBAL_LOGGER.info(f"UnboundElementValidator completed with {len(self.errors)} error(s).")
        return self.errors, self.warnings
