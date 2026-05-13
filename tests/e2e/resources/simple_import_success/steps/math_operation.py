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


@jpipe_link("E3")
@jpipe(produce=["number_c"])
def generate_number_c(produce) -> bool:
    """
    Verify that a function from a root directory can be imported at runtime.
    (e.g., local import 'from root_utils import get_root_number_c' inside the function).

    get_root_number_c is defined in a file located in the root directory and just returns 20.
    """
    from root_utils import get_root_number_c

    value = get_root_number_c()
    produce("number_c", value)
    return True


@jpipe_link("E4")
@jpipe(produce=["number_d"])
def generate_number_d(produce) -> bool:
    """
    Verify that a function from a nested package can be imported at runtime.
    (e.g., local import 'from steps.step_utils import get_step_number_d' inside the function).

    get_step_number_d is defined in a file located in the same directory and just returns 2.
    """
    from steps.step_utils import get_step_number_d

    value = get_step_number_d()
    produce("number_d", value)
    return True


@jpipe_link("S1")
@jpipe(consume=["number_a", "number_b", "number_c", "number_d"])
def add_numbers(number_a: int, number_b: int, number_c: int, number_d: int) -> bool:
    """Add numbers - expects sum 10+5+20+2=37"""
    return number_a + number_b + number_c + number_d == 37
