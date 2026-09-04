from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import UserStatus


@dataclass(frozen=True, slots=True)
class CreateUserCommand:
    username: str
    email: str
    display_name: str


@dataclass(frozen=True, slots=True)
class UpdateUserCommand:
    user_id: UUID
    username: str
    email: str
    display_name: str


@dataclass(frozen=True, slots=True)
class ChangeUserStatusCommand:
    user_id: UUID
    status: UserStatus


@dataclass(frozen=True, slots=True)
class UserDTO:
    id: UUID
    username: str
    email: str
    display_name: str
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, user: User) -> UserDTO:
        return cls(
            id=user.id.value,
            username=user.username.value,
            email=user.email.value,
            display_name=user.display_name,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


@dataclass(frozen=True, slots=True)
class UserPageDTO:
    items: tuple[UserDTO, ...]
    total: int
    offset: int
    limit: int
