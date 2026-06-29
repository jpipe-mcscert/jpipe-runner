"""
Simple success scenario — tests basic action parameters.
"""

from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


@jpipe_link("E1")
@jpipe(consume=["expected_value"], produce=["config_ok"])
def check_config_value(expected_value: int, produce) -> bool:
    """
    Verify that a configuration value can be loaded from config.yaml.

    This step consumes `expected_value` from config.yaml
    (e.g., 'expected_value: 43') and returns it as a boolean.
    """
    config_ok = expected_value == 43
    produce("config_ok", config_ok)
    return config_ok


@jpipe_link("E3")
@jpipe(consume=["user_name"], produce=["variable_ok"])
def check_user_variable(user_name: str, produce) -> bool:
    """
    Verify that a variable can be injected at runtime via the `variable` input.

    This step consumes `user_name` passed through `variable: 'user_name:Alice'`
    and asserts it equals "Alice".
    """
    variable_ok = user_name == "Alice"
    produce("variable_ok", variable_ok)
    return variable_ok


@jpipe_link("S1")
@jpipe(consume=["config_ok", "variable_ok"])
def all_conditions_are_met(config_ok: bool, variable_ok: bool) -> bool:
    """Strategy that aggregates individual checks — expects all to succeed."""
    return config_ok and variable_ok
