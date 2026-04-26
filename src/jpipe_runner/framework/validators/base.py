from jpipe_runner.framework.context import RuntimeContext

from ..logger import GLOBAL_LOGGER  # noqa: F401 — re-exported for submodule use


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

    def validate(self) -> tuple[list[str], list[str]]:
        """
        Abstract method for performing validation.

        Subclasses must override this method to implement specific validation logic. This method
        should populate `self.errors` with detailed error messages and return them.

        :raises NotImplementedError: If called on the abstract base class.
        :return: A list of error messages (if any).
        :rtype: list[str]
        """
        raise NotImplementedError("Subclasses must implement the `validate()` method.")

    def _find_element_context(self, fn_name: str) -> tuple[str, str, str] | None:
        """Return (node_id, label, element_type) for the graph node bound to fn_name, or None."""
        for node_id, data in self.pipeline.graph.nodes(data=True):
            if data.get("function_name") == fn_name:
                return node_id, data.get("label", node_id), data.get("type", "unknown")
        return None
