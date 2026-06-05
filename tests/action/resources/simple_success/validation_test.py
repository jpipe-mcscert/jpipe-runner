from lib.lib_utils import get_magic_number

from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


@jpipe_link("E1")
@jpipe(consume=["expected_value"], produce=["config_ok"])
def check_config_value(expected_value: int, produce) -> bool:
    """
    Verify that a configuration value can be loaded from config.yaml.

    This step consumes `expected_value` from config.yaml
    (e.g., 'expected_value: 43') and returns it as a boolean.

    get_magic_number is NOT called here — the library import is tested separately in E2.
    """
    config_ok = expected_value == 43
    produce("config_ok", config_ok)
    return config_ok


@jpipe_link("E2")
@jpipe(produce=["library_ok"])
def check_library_import(produce) -> bool:
    """
    Verify that a function from a nested package can be imported and used.

    This step calls get_magic_number() from lib/lib_utils.py
    (e.g., 'from lib.lib_utils import get_magic_number').

    get_magic_number is defined in lib/lib_utils.py and just returns 42.
    """
    library_ok = get_magic_number() == 42
    produce("library_ok", library_ok)
    return library_ok


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
@jpipe(consume=["config_ok", "library_ok", "variable_ok"])
def all_conditions_are_met(config_ok: bool, library_ok: bool, variable_ok: bool) -> bool:
    """Strategy that aggregates individual checks — expects all to succeed."""
    return config_ok and library_ok and variable_ok
