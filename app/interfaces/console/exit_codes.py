from enum import IntEnum


class ConsoleExitCode(IntEnum):
    """Console 进程退出码。"""

    SUCCESS = 0
    FAILURE = 1
    USAGE = 2
