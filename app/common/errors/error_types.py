"""错误类型枚举：AA 段取值。"""

from enum import IntEnum


class ErrorType(IntEnum):
    """错误类型（AA）。"""

    BIZ = 10
    SYSTEM = 20
    THIRD = 30
