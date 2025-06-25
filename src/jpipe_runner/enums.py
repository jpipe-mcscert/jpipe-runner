"""
jpipe_runner.enums
~~~~~~~~~~~~~~~~~~

This module contains the enums of Justification Diagram.
"""

from enum import Enum


class ClassType(Enum):
    """justification / pattern / composition"""
    JUSTIFICATION = "justification"
    PATTERN = "pattern"
    COMPOSITION = "composition"


class VariableType(Enum):
    """evidence / strategy / sub-conclusion / conclusion / @support"""
    EVIDENCE = "evidence"
    STRATEGY = "strategy"
    SUB_CONCLUSION = "sub-conclusion"
    CONCLUSION = "conclusion"
    SUPPORT = "@support"


class StatusType(Enum):
    """PASS / FAIL / SKIP"""
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
