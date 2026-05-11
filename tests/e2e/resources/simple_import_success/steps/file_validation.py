from root_utils import root_utils_exists
from steps.step_utils import step_utils_exists

from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


@jpipe_link("E1")
@jpipe(consume=["file_path"], produce=["file_exists"])
def check_file_exists(file_path: str, produce) -> bool:
    """Check if a file exists"""
    exists = root_utils_exists(file_path) and step_utils_exists(file_path)
    produce("file_exists", exists)
    return exists


@jpipe(consume=["file_exists"])
def file_is_valid(file_exists: bool) -> bool:
    """Validate that file exists"""
    return file_exists
