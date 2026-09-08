"""定义响应码值、最小协议和枚举适配基类。"""

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
        """确保局部码和 HTTP 状态可安全参与完整码构造。"""

        if len(self.code) != 4 or not self.code.isdigit():
            raise ValueError("局部响应码必须是四位数字")

        if not 100 <= self.status_code <= 599:
            raise ValueError("HTTP 状态码必须在 100 到 599 之间")


@runtime_checkable
class CodeContract(Protocol):
    """完整响应码构造所需的最小契约。"""

    @property
    def code(self) -> str:
        """返回四位局部响应码。"""

        ...

    @property
    def message(self) -> str:
        """返回默认用户可见消息。"""

        ...

    @property
    def status_code(self) -> int:
        """返回对应 HTTP 状态码。"""

        ...


class CodedEnum(Enum):
    """以 :class:`CodeDefinition` 为值的响应码枚举基类。"""

    @property
    def definition(self) -> CodeDefinition:
        """返回枚举成员持有的不可变码定义。"""

        return cast(CodeDefinition, self.value)

    @property
    def code(self) -> str:
        """代理局部响应码。"""

        return self.definition.code

    @property
    def message(self) -> str:
        """代理默认响应消息。"""

        return self.definition.message

    @property
    def status_code(self) -> int:
        """代理 HTTP 状态码。"""

        return self.definition.status_code
