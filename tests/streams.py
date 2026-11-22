"""Reading a run's events (``--events``) and checking them against their schema (ADR-0030).

``events.schema.json`` refers to ``report.schema.json`` for an element and a diagnostic,
as the report writes them. ``VALIDATOR`` resolves those references with the report's
schema, whichever API the installed jsonschema has: a ``referencing`` registry from 4.18, and a
``RefResolver`` on the floor (ADR-0026).
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from jpipe_runner import events, json_report

REPORT_SCHEMA = "report.schema.json"


def _validator() -> Any:
    try:
        from referencing import Registry, Resource

        registry = Registry().with_resource(
            REPORT_SCHEMA, Resource.from_contents(json_report.SCHEMA)
        )
        return Draft202012Validator(events.SCHEMA, registry=registry)
    # Before 4.18, jsonschema takes no registry, even with referencing installed.
    except (ImportError, TypeError):
        from jsonschema import RefResolver

        # Its references are resolved against a URI: the schemas', side by side.
        directory = Path(events.__file__).parent / "schema"
        base = (directory / "events.schema.json").as_uri()
        store = {(directory / REPORT_SCHEMA).as_uri(): json_report.SCHEMA}
        resolver = RefResolver(base, events.SCHEMA, store=store)
        return Draft202012Validator(events.SCHEMA, resolver=resolver)


VALIDATOR = _validator()


def read(path: Path) -> list[dict[str, Any]]:
    """The events in ``path``, each checked against the schema."""
    lines = path.read_text(encoding="utf-8").splitlines()
    found = [json.loads(line) for line in lines]
    for event in found:
        VALIDATOR.validate(event)
    return found


def of(found: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    """The events of ``found`` whose ``event`` is ``kind``, in order."""
    return [event for event in found if event["event"] == kind]
