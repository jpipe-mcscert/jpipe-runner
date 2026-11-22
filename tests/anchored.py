"""Running steps a test declares itself, as if the test's file were in the run's root.

A path an evidence observes is relative to the file that declares its step (ADR-0028). A
step declared in a test observes files the test wrote in a temporary directory: ``run``
runs it as a library in that directory would be run.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any

from jpipe_runner import engine
from jpipe_runner.engine import RunResult
from jpipe_runner.model import Justification
from jpipe_runner.steps import StepRegistry


def run(
    justification: Justification, registry: StepRegistry, *, root: Path = Path(), **options: Any
) -> RunResult:
    """``engine.run``, with every step of ``registry`` declared in ``root``."""
    declared = StepRegistry(replace(step, directory=root) for step in registry)
    return engine.run(justification, declared, root=root, **options)
