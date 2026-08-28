from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self

from app.contexts.user.domain.repository import UserRepository


class UserUnitOfWork(Protocol):
    """一个用户用例对应的事务边界。"""

    @property
    def users(self) -> UserRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


type UserUnitOfWorkFactory = Callable[[], UserUnitOfWork]
