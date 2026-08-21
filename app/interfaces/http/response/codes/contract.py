from dataclasses import dataclass
from enum import Enum
from typing import Protocol, cast, runtime_checkable


@dataclass(frozen=True, slots=True)
class CodeDefinition:
    """单个 HTTP 响应码的不可变定义。"""

    code: str
    message: str
    status_code: int

    def __post_init__(self) -> None:
        if len(self.code) != 4 or not self.code.isdigit():
            raise ValueError("局部响应码必须是四位数字")

        if not 100 <= self.status_code <= 599:
            raise ValueError("HTTP 状态码必须在 100 到 599 之间")


@runtime_checkable
class CodeContract(Protocol):
    """完整响应码构造所需的最小契约。"""

    @property
    def code(self) -> str: ...

    @property
    def message(self) -> str: ...

    @property
    def status_code(self) -> int: ...


class CodedEnum(Enum):
    """以 :class:`CodeDefinition` 为值的响应码枚举基类。"""

    @property
    def definition(self) -> CodeDefinition:
        return cast(CodeDefinition, self.value)

    @property
    def code(self) -> str:
        return self.definition.code

    @property
    def message(self) -> str:
        return self.definition.message

    @property
    def status_code(self) -> int:
        return self.definition.status_code
