"""Step library for simple_import.

Each evidence obtains its number through a different import: a root module or a module
of the `steps` package, at load time or at run time. The run-time imports name modules
that nothing imports at load time, so they are not already in `sys.modules`: they succeed
only if the --python-path entry is still on `sys.path` while the steps run. Each evidence
observes the module it takes its number from.
"""

from pathlib import Path

from root_utils import get_root_number_a
from steps.step_utils import get_step_number_b

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy

EXPECTED_SUM = 37


@evidence("E1", observes={"module": "root_utils.py"}, produces=["number_a"])
def generate_number_a(module: Path) -> Outcome:
    """Number a comes from a root module imported at load time."""
    return Pass(number_a=get_root_number_a())


@evidence("E2", observes={"module": "steps/step_utils.py"}, produces=["number_b"])
def generate_number_b(module: Path) -> Outcome:
    """Number b comes from a package module imported at load time."""
    return Pass(number_b=get_step_number_b())


@evidence("E3", observes={"module": "root_runtime_utils.py"}, produces=["number_c"])
def generate_number_c(module: Path) -> Outcome:
    """Number c comes from a root module imported at run time."""
    from root_runtime_utils import get_root_number_c

    return Pass(number_c=get_root_number_c())


@evidence("E4", observes={"module": "steps/step_runtime_utils.py"}, produces=["number_d"])
def generate_number_d(module: Path) -> Outcome:
    """Number d comes from a package module imported at run time."""
    from steps.step_runtime_utils import get_step_number_d

    return Pass(number_d=get_step_number_d())


@strategy("S1", consumes=["number_a", "number_b", "number_c", "number_d"])
def add_numbers(number_a: int, number_b: int, number_c: int, number_d: int) -> Outcome:
    """The four numbers add up to the expected sum."""
    total = number_a + number_b + number_c + number_d
    if total == EXPECTED_SUM:
        return Pass()
    return Fail(f"the numbers add up to {total}, not {EXPECTED_SUM}")
