from ..logger import GLOBAL_LOGGER
from .base import BaseValidator


class UnboundElementValidator(BaseValidator):
    """
    Validates that every evidence and strategy node in the pipeline has an explicit
    @jpipe_link binding. Nodes relying on the sanitized-label fallback are rejected.
    """

    EXECUTABLE_TYPES = {"evidence", "strategy"}

    def validate(self) -> tuple[list[str], list[str]]:
        """
        Validate that every executable node has an explicit @jpipe_link binding.

        Binding is decided by the pipeline's alias-aware ``_bound_node_ids()`` — a
        node counts as bound whether the @jpipe_link used its canonical id, a
        qualified id, or one of its aliases.

        :return: A tuple of (errors, warnings).
        :rtype: tuple[list[str], list[str]]
        """
        GLOBAL_LOGGER.info("Running UnboundElementValidator...")
        bound = self.pipeline._bound_node_ids()
        for node_id, data in self.pipeline.graph.nodes(data=True):
            if data.get("type") not in self.EXECUTABLE_TYPES:
                continue
            if node_id not in bound:
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
