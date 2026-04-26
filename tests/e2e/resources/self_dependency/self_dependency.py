from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


@jpipe_link("S1")
@jpipe(consume=["var_a"], produce=["var_a"])
def function_a(var_a: str, produce) -> bool:
    """
    Function A processes var_a and produces var_a.
    This function has a self-dependency because it consumes and produces the same variable.
    """
    produce("var_a", f"processed_{var_a}")
    return True


@jpipe_link("S2")
@jpipe(consume=["var_a"], produce=["var_b"])
def function_b(var_a: str, produce) -> bool:
    produce("var_b", f"processed_{var_a}")
    return True


@jpipe(consume=["var_a", "var_b"])
def final_check(var_a: str, var_b: str) -> bool:
    """Final validation"""
    return var_a and var_b
