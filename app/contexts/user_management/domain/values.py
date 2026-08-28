import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.contexts.user_management.domain.errors import InvalidUserDataError

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{3,32}$")


@dataclass(frozen=True, slots=True)
class UserId:
    value: UUID


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


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
