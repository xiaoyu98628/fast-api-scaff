"""code码契约：业务码枚举需实现 message/status_code。"""
from dataclasses import dataclass
from enum import Enum

from config.config import config


@dataclass(frozen=True)
class CodeDefinition:
    """码定义。"""
    code: str

    message: str

    status_code: int


class CodedEnum(Enum):
    """码表 Enum 基类：value 必须是 CodeDefinition。"""

    @property
    def code(self) -> str:
        return self.value.code

    @property
    def message(self) -> str:
        return self.value.message

    @property
    def status_code(self) -> int:
        return self.value.status_code

    def full_code(self) -> str:
        app_config = config().app

        """生成完整码。"""
        return f"{self.status_code:03d}{app_config.service_code}{self.code}"
