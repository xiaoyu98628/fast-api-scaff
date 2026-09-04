import re
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from app.contexts.user.domain.errors import InvalidUserDataError

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{3,32}$")
_PASSWORD_MIN_LENGTH = 8
_PASSWORD_MAX_LENGTH = 128
_PASSWORD_HASH_MAX_LENGTH = 255


@dataclass(frozen=True, slots=True)
class UserId:
    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise InvalidUserDataError("用户 ID 必须是 UUID")


@dataclass(frozen=True, slots=True)
class Username:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()

        if not _USERNAME_PATTERN.fullmatch(normalized):
            raise InvalidUserDataError("用户名必须由 3 到 32 位小写字母、数字或下划线组成")

        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class EmailAddress:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()

        if len(normalized) > 254 or not _EMAIL_PATTERN.fullmatch(normalized):
            raise InvalidUserDataError("邮箱地址格式不正确")

        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class Password:
    """只在创建用户等输入边界短暂存在的明文密码。"""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidUserDataError("密码必须是字符串")

        if not _PASSWORD_MIN_LENGTH <= len(self.value) <= _PASSWORD_MAX_LENGTH:
            raise InvalidUserDataError("密码长度必须在 8 到 128 个字符之间")


@dataclass(frozen=True, slots=True)
class PasswordHash:
    """可持久化的密码哈希，不暴露具体哈希算法。"""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidUserDataError("密码哈希必须是字符串")

        if not 1 <= len(self.value) <= _PASSWORD_HASH_MAX_LENGTH:
            raise InvalidUserDataError("密码哈希长度必须在 1 到 255 个字符之间")


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
