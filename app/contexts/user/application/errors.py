"""定义用户管理用例对外公开的应用层异常。"""

from typing import Literal
from uuid import UUID

type UserConflictField = Literal["username", "email"]


class UserApplicationError(Exception):
    """用户应用用例异常基类。"""


class UserNotFoundError(UserApplicationError):
    """表示目标用户在执行期间不存在。"""

    def __init__(self, user_id: UUID) -> None:
        """保留目标 ID，供 HTTP 或 Console 适配器生成响应。"""

        self.user_id = user_id
        super().__init__(f"用户 {user_id} 不存在")


class UserConflictError(UserApplicationError):
    """表示用户名或邮箱违反唯一性约束。"""

    def __init__(self, field: UserConflictField) -> None:
        """保留冲突字段，避免上层解析异常文本。"""

        self.field = field
        super().__init__(f"用户唯一标识 {field} 已存在")


class ConcurrentUserUpdateError(UserApplicationError):
    """表示目标用户已被另一个事务更新。"""

    def __init__(self, user_id: UUID) -> None:
        """保留冲突用户 ID，供入站适配器生成稳定响应。"""

        self.user_id = user_id
        super().__init__(f"用户 {user_id} 已被并发修改")
