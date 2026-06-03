from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


@jpipe_link("E1")
@jpipe(produce=["number_a"])
def generate_number_a(produce) -> bool:
    """Generate first number"""
    produce("number_a", 10)
    return True


@jpipe_link("E2")
@jpipe(produce=["number_b"])
def generate_number_b(produce) -> bool:
    """Generate second number"""
    produce("number_b", 5)
    return True


@jpipe_link("S1")
@jpipe(consume=["number_a", "number_b"])
def add_numbers(number_a, number_b) -> bool:
    """Add two numbers"""
    result = number_a + number_b
    print(f"Result of addition: {result}")
    return True
