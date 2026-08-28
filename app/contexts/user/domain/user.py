from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid7

from app.contexts.user.domain.errors import InvalidUserDataError
from app.contexts.user.domain.values import EmailAddress, UserId, Username, UserStatus


@dataclass(slots=True)
class User:
    """用户限界上下文中的用户聚合根。"""

    id: UserId
    username: Username
    email: EmailAddress
    display_name: str
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        username: str,
        email: str,
        display_name: str,
        now: datetime,
        user_id: UUID | None = None,
    ) -> User:
        return cls(
            id=UserId(user_id if user_id is not None else uuid7()),
            username=Username(username),
            email=EmailAddress(email),
            display_name=_validate_display_name(display_name),
            status=UserStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )

    def update_profile(
        self,
        *,
        username: str,
        email: str,
        display_name: str,
        status: UserStatus,
        now: datetime,
    ) -> None:
        resolved_username = Username(username)
        resolved_email = EmailAddress(email)
        resolved_display_name = _validate_display_name(display_name)

        self.username = resolved_username
        self.email = resolved_email
        self.display_name = resolved_display_name
        self.status = status
        self.updated_at = now


def _validate_display_name(value: str) -> str:
    normalized = value.strip()

    if not 1 <= len(normalized) <= 80:
        raise InvalidUserDataError("显示名称长度必须在 1 到 80 个字符之间")

    return normalized
