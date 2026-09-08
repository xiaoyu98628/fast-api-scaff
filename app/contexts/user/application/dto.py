"""定义用户管理用例的输入命令和输出 DTO。"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import UserStatus


@dataclass(frozen=True, slots=True)
class CreateUserCommand:
    """携带创建用户所需的原始输入。"""

    username: str
    email: str
    password: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class UpdateUserCommand:
    """携带用户资料更新输入。"""

    user_id: UUID
    username: str
    email: str


@dataclass(frozen=True, slots=True)
class ChangeUserStatusCommand:
    """携带目标用户和新的账户状态。"""

    user_id: UUID
    status: UserStatus


@dataclass(frozen=True, slots=True)
class ResetUserPasswordCommand:
    """携带目标用户和待哈希的新密码。"""

    user_id: UUID
    password: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class UserDTO:
    """向入站适配器公开的用户只读快照。"""

    id: UUID
    username: str
    email: str
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, user: User) -> UserDTO:
        """把领域值对象展开为可序列化的应用层数据。"""

        return cls(
            id=user.id.value,
            username=user.username.value,
            email=user.email.value,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


@dataclass(frozen=True, slots=True)
class UserPageDTO:
    """保存一页用户结果及分页元数据。"""

    items: tuple[UserDTO, ...]
    total: int
    offset: int
    limit: int
