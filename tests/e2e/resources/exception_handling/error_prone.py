from jpipe_runner.framework.decorators.jpipe_decorator import jpipe

@jpipe(consume=["denominator"], produce=["result"])
def divide_by_number(denominator: int, produce) -> bool:
    """Divide 100 by denominator - may raise exception"""
    if denominator == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    result = 100 / denominator
    produce("result", result)
    return True

@jpipe(consume=["result"])
def validate_division_result(result: float) -> bool:
    """Validate division result"""
    return result > 0
