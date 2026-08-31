from contextlib import AbstractAsyncContextManager
from types import TracebackType

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.user.application.errors import UserConflictError
from app.contexts.user.domain.repository import UserRepository
from app.contexts.user.infrastructure.persistence.repository import SqlAlchemyUserRepository
from app.infrastructure.database.manager import DatabaseManager


class SqlAlchemyUserUnitOfWork:
    """以一个 SQLAlchemy Session 实现用户用例事务。"""

    def __init__(self, databases: DatabaseManager, connection_name: str) -> None:
        self._databases = databases
        self._connection_name = connection_name
        self._session_context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._users: UserRepository | None = None

    @property
    def users(self) -> UserRepository:
        if self._users is None:
            raise RuntimeError("UserUnitOfWork 尚未进入事务上下文")

        return self._users

    async def __aenter__(self) -> SqlAlchemyUserUnitOfWork:
        self._session_context = self._databases.session(self._connection_name)
        self._session = await self._session_context.__aenter__()
        self._users = SqlAlchemyUserRepository(self._session)
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is not None and exception is not None:
            await self._session.rollback()

        if self._session_context is not None:
            await self._session_context.__aexit__(exception_type, exception, traceback)

        self._session_context = None
        self._session = None
        self._users = None

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("UserUnitOfWork 尚未进入事务上下文")

        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise UserConflictError("identity") from error
