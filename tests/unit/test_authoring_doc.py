"""The examples of docs/authoring.md run as written, and the output it quotes is real.

Every ``python`` block of the page is executed, in order, in one namespace, so a later
example may use what an earlier one declared. A block that stops working with the API it
documents fails here. The diagnostics the page quotes are recomputed by running the
examples' steps.
"""

import json
import re
from pathlib import Path
from typing import Any

from jpipe_runner import loader
from jpipe_runner.engine import Status, run
from jpipe_runner.steps import StepRegistry, step_of
from tests.conftest import REPO_ROOT

PAGE = (REPO_ROOT / "docs" / "authoring.md").read_text(encoding="utf-8")
BLOCKS = re.findall(r"^```python\n(.*?)^```", PAGE, re.MULTILINE | re.DOTALL)

# The module name the page shows for its examples' steps.
MODULE = "steps"


def _examples() -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": MODULE}
    for block in BLOCKS:
        exec(compile(block, "docs/authoring.md", "exec"), namespace)
    return namespace


def test_the_page_has_examples() -> None:
    assert len(BLOCKS) >= 5


def test_every_example_runs() -> None:
    assert _examples()


def test_the_page_quotes_what_a_pass_without_a_declared_value_reports(tmp_path: Path) -> None:
    examples = _examples()
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "junit.xml").write_text(
        '<testsuite tests="3" failures="0"/>', encoding="utf-8"
    )
    model = {
        "name": "release",
        "type": "justification",
        "elements": [
            {"id": "release:c", "type": "conclusion", "label": "Ready"},
            {"id": "release:s", "type": "strategy", "label": "Every test passed"},
            {"id": "release:e1", "type": "evidence", "label": "The test suite ran"},
        ],
        "relations": [
            {"source": "release:s", "target": "release:c"},
            {"source": "release:e1", "target": "release:s"},
        ],
    }
    functions = (examples["the_test_suite_ran"], examples["every_test_passed"])
    registry = StepRegistry(step for step in map(step_of, functions) if step is not None)

    result = run(loader.loads(json.dumps(model)), registry, root=tmp_path)

    assert result.result("release:s").status is Status.SKIP
    (diagnostic,) = result.diagnostics
    assert f"```\n{diagnostic}\n  fix: {diagnostic.fix}\n```" in PAGE
