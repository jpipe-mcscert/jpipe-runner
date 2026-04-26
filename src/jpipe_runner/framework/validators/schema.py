import importlib.resources
import json
from typing import Any

import jsonschema

from ..logger import GLOBAL_LOGGER

_schema_file = importlib.resources.files("jpipe_runner.schema").joinpath("justification.schema.json")
JUSTIFICATION_JSON_SCHEMA = json.loads(_schema_file.read_text(encoding="utf-8"))


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

    def __init__(self, data: dict[str, Any]) -> None:
        """
        Initialize the validator with parsed justification JSON data.

        :param data: Dictionary representing the justification JSON content.
        :type data: dict[str, Any]
        """
        self.data = data
        self.element_ids = set()

    def validate(self) -> None:
        """
        Executes the full validation pipeline on the justification structure.

        Structural validation (required fields, types, enums) is delegated to
        ``JUSTIFICATION_JSON_SCHEMA`` via ``jsonschema``. Semantic checks that
        go beyond what JSON Schema can express (ID uniqueness, cross-references)
        are handled by the private helper methods below.

        :raises ValueError: If any structural or semantic check fails.
        """
        GLOBAL_LOGGER.debug("Starting justification schema validation")

        try:
            jsonschema.validate(instance=self.data, schema=JUSTIFICATION_JSON_SCHEMA)
        except jsonschema.ValidationError as e:
            raise ValueError(e.message) from e

        GLOBAL_LOGGER.info("Top-level keys and structural constraints validated via JSON Schema")

        self._validate_elements()
        self._validate_relations()

        GLOBAL_LOGGER.info("Justification schema validation completed successfully")

    def _validate_elements(self) -> None:
        """
        Checks that all element IDs are unique (semantic check not expressible in JSON Schema).

        :raises ValueError: If duplicate element IDs are found.
        """
        for element in self.data.get("elements", []):
            if element["id"] in self.element_ids:
                raise ValueError(f"Duplicate element id: '{element['id']}'")
            self.element_ids.add(element["id"])

        GLOBAL_LOGGER.debug("All element IDs validated for uniqueness: %s", self.element_ids)

    def _validate_relations(self) -> None:
        """
        Checks that every relation source/target references an existing element ID.

        :raises ValueError: If a relation references an unknown element ID.
        """
        relations = self.data.get("relations", [])
        for i, rel in enumerate(relations):
            for key in ["source", "target"]:
                if rel[key] not in self.element_ids:
                    raise ValueError(f"Relation {i} refers to unknown {key} id '{rel[key]}'")

        GLOBAL_LOGGER.debug("All relations validated: %d total", len(relations))
