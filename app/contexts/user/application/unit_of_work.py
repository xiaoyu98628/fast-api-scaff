"""声明用户管理与认证用例共享的事务边界。"""

from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self

from app.contexts.user.domain.repository import UserRepository
from app.contexts.user.domain.session_repository import SessionRepository


class UserUnitOfWork(Protocol):
    """一个用户用例对应的事务边界。"""

    @property
    def users(self) -> UserRepository:
        """返回绑定当前事务的用户仓储。"""

        ...

    @property
    def sessions(self) -> SessionRepository:
        """返回绑定当前事务的会话仓储。"""

        ...

    async def __aenter__(self) -> Self:
        """开启事务边界并返回工作单元。"""

        ...

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """退出事务边界，并由实现处理未提交事务。"""

        ...

    async def commit(self) -> None:
        """提交当前用户与会话变更。"""

        ...


# 工厂让每个用例显式获得独立工作单元，而不持有长生命周期 Session。
type UserUnitOfWorkFactory = Callable[[], UserUnitOfWork]
