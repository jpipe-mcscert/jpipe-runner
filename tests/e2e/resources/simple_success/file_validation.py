import os
from jpipe_runner.framework.decorators.jpipe_decorator import jpipe

@jpipe(consume=["file_path"], produce=["file_exists"])
def check_file_exists(file_path: str, produce) -> bool:
    """Check if a file exists"""
    exists = os.path.exists(file_path)
    produce("file_exists", exists)
    return exists

@jpipe(consume=["file_exists"])
def file_is_valid(file_exists: bool) -> bool:
    """Validate that file exists"""
    return file_exists
