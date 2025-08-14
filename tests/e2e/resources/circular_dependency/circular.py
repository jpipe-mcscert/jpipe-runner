from jpipe_runner.framework.decorators.jpipe_decorator import jpipe

@jpipe(consume=["var_b"], produce=["var_a"])
def function_a(var_b: str, produce) -> bool:
    """Function A depends on B"""
    produce("var_a", f"processed_{var_b}")
    return True

@jpipe(consume=["var_a"], produce=["var_b"])
def function_b(var_a: str, produce) -> bool:
    """Function B depends on A - creates cycle"""
    produce("var_b", f"processed_{var_a}")
    return True

@jpipe(consume=["var_a", "var_b"])
def final_check(var_a: str, var_b: str) -> bool:
    """Final validation"""
    return True
