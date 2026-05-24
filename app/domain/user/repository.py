from typing import Protocol

from app.domain.user.entity import User
from app.domain.user.enums import UserStatus


class UserRepository(Protocol):
    """用户仓储接口。"""

    async def get_by_id(self, user_id: str) -> User | None:
        """按 ID 查询未删除用户。"""

    async def get_by_username(self, username: str) -> User | None:
        """按用户名查询未删除用户。"""

    async def create(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        nickname: str,
        status: UserStatus,
    ) -> User:
        """创建用户。"""

    async def update(
        self,
        user_id: str,
        *,
        nickname: str | None = None,
        password_hash: str | None = None,
        status: UserStatus | None = None,
    ) -> User | None:
        """更新用户，返回 None 表示用户不存在或已删除。"""

    async def soft_delete(self, user_id: str) -> bool:
        """软删除用户，返回是否成功。"""

    async def page(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
    ) -> tuple[list[User], int]:
        """分页列表，返回 (items, total)。"""
