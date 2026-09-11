"""声明用户聚合在 Domain 层需要的持久化能力。"""

from typing import Protocol

from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import EmailAddress, UserId, Username


class UserRepository(Protocol):
    """用户聚合持久化契约。"""

    async def find(self, user_id: UserId) -> User | None:
        """按领域 ID 查找用户聚合。"""

        ...

    async def find_by_username(self, username: Username) -> User | None:
        """按已规范化的用户名查找用户聚合。"""

        ...

    async def exists_by_username(self, username: Username, *, excluding: UserId | None = None) -> bool:
        """检查用户名占用情况，并可排除正在更新的用户。"""

        ...

    async def exists_by_email(self, email: EmailAddress, *, excluding: UserId | None = None) -> bool:
        """检查邮箱占用情况，并可排除正在更新的用户。"""

        ...

    async def find_page(self, *, offset: int, limit: int) -> tuple[list[User], int]:
        """返回当前页聚合及未分页的记录总数。"""

        ...

    async def add(self, user: User) -> None:
        """把新聚合加入当前事务。"""

        ...

    async def update_profile(self, user: User) -> bool:
        """只持久化现有聚合的用户名、邮箱和更新时间。"""

        ...

    async def change_status(self, user: User) -> bool:
        """只持久化现有聚合的账户状态和更新时间。"""

        ...

    async def reset_password(self, user: User) -> bool:
        """只持久化现有聚合的密码哈希和更新时间。"""

        ...

    async def remove(self, user_id: UserId) -> bool:
        """删除指定聚合，并返回是否删除了记录。"""

        ...
