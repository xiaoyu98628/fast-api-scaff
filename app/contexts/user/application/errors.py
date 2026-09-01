from typing import Literal
from uuid import UUID

type UserConflictField = Literal["username", "email"]


class UserApplicationError(Exception):
    """用户应用用例异常基类。"""


class UserNotFoundError(UserApplicationError):
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        super().__init__(f"用户 {user_id} 不存在")


class UserConflictError(UserApplicationError):
    def __init__(self, field: UserConflictField) -> None:
        self.field = field
        super().__init__(f"用户唯一标识 {field} 已存在")
