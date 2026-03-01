from jpipe_runner.framework.decorators.jpipe_decorator import jpipe

@jpipe(consume=["input_string"])
def process_string(input_string: str, produce) -> bool:
    """Process a string"""
    processed = input_string.upper()
    produce("processed_string", processed)
    return True

@jpipe(consume=["processed_string"])
def validate_string(processed_string: str) -> bool:
    """Validate processed string"""
    return len(processed_string) > 0
