from jpipe_runner.framework.decorators.jpipe_decorator import jpipe

@jpipe(produce=["number_a"])
def generate_number_a(produce) -> bool:
    """Generate first number"""
    produce("number_a", 10)
    return True

@jpipe(produce=["number_b"])
def generate_number_b(produce) -> bool:
    """Generate second number"""
    produce("number_b", 5)
    return True

# Missing consume for number_a and number_b
@jpipe(consume=["missing_var"])
def add_numbers(missing_var: int) -> bool:
    """Add two numbers - should fail due to missing consumer"""
    return True
