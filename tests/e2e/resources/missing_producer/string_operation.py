from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


# Intentionally calls produce() without declaring it in the decorator —
# processed_string is never registered in ctx, so validate_string has no producer.
@jpipe_link("S1")
@jpipe(consume=["input_string"])
def process_string(input_string: str) -> bool:
    """Process a string"""
    processed = input_string.upper()
    return len(processed) > 0


@jpipe(consume=["processed_string"])
def validate_string(processed_string: str) -> bool:
    """Validate processed string"""
    return len(processed_string) > 0
