from root_utils import get_root_number_a
from steps.step_utils import get_step_number_b

from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


@jpipe_link("E1")
@jpipe(produce=["number_a"])
def generate_number_a(produce) -> bool:
    """
    Verify that a function from a root directory can be imported and used.
    (e.g., 'from root_utils import get_root_number_a')

    get_root_number_a is defined in a file located in the root directory and just returns 10.
    """
    value = get_root_number_a()
    produce("number_a", value)
    return True


@jpipe_link("E2")
@jpipe(produce=["number_b"])
def generate_number_b(produce) -> bool:
    """
    Verify that a function from a module can be imported and used.
    (e.g., 'from steps.step_utils import get_step_number_b')

    get_step_number_b is defined in a file located in the same directory and just returns 5.
    """
    value = get_step_number_b()
    produce("number_b", value)
    return True


@jpipe_link("S1")
@jpipe(consume=["number_a", "number_b"])
def add_numbers(number_a: int, number_b: int) -> bool:
    """Add two numbers - expects sum 10+5=15"""
    return number_a + number_b == 15
