import re
import sqlite3
from contextlib import AbstractAsyncContextManager
from types import TracebackType

from anyio import CancelScope
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.user.application.errors import UserConflictError, UserConflictField
from app.contexts.user.domain.repository import UserRepository
from app.contexts.user.infrastructure.persistence.repository import SqlAlchemyUserRepository
from app.infrastructure.database.manager import DatabaseManager

_USER_UNIQUE_CONSTRAINTS: dict[str, UserConflictField] = {
    "uq_users_username": "username",
    "users_username_key": "username",
    "uq_users_email": "email",
    "users_email_key": "email",
}
_SQLITE_UNIQUE_COLUMNS: dict[str, UserConflictField] = {
    "UNIQUE constraint failed: users.username": "username",
    "UNIQUE constraint failed: users.email": "email",
}
_MYSQL_DUPLICATE_KEY = re.compile(r"Duplicate entry .* for key ['`](?P<key>[^'`]+)['`]", re.DOTALL)


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
        cleanup_errors: list[BaseException] = []

        try:
            with CancelScope(shield=True):
                if self._session is not None and exception is not None:
                    try:
                        await self._session.rollback()
                    except BaseException as error:
                        cleanup_errors.append(error)

                if self._session_context is not None:
                    try:
                        await self._session_context.__aexit__(exception_type, exception, traceback)
                    except BaseException as error:
                        cleanup_errors.append(error)
        finally:
            self._session_context = None
            self._session = None
            self._users = None

        if cleanup_errors:
            errors = ([exception] if exception is not None else []) + cleanup_errors
            raise BaseExceptionGroup("用户事务退出和清理失败", errors) from None

        if isinstance(exception, IntegrityError):
            field = _resolve_user_conflict_field(exception)
            if field is not None:
                raise UserConflictError(field) from exception

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("UserUnitOfWork 尚未进入事务上下文")

        try:
            await self._session.commit()
        except IntegrityError as error:
            try:
                with CancelScope(shield=True):
                    await self._session.rollback()
            except BaseException as cleanup_error:
                raise BaseExceptionGroup("用户事务提交和回滚失败", (error, cleanup_error)) from None
            field = _resolve_user_conflict_field(error)
            if field is None:
                raise

            raise UserConflictError(field) from error


def _resolve_user_conflict_field(error: IntegrityError) -> UserConflictField | None:
    original = error.orig
    if original is None:
        return None

    if getattr(original, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
        return _SQLITE_UNIQUE_COLUMNS.get(str(original))

    cause = getattr(original, "__cause__", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None) or getattr(cause, "sqlstate", None)
    if sqlstate == "23505":
        return _postgresql_conflict_field(original, cause)

    if original.args and original.args[0] == 1062:
        return _mysql_conflict_field(original)

    return None


def _postgresql_conflict_field(original: BaseException, cause: object) -> UserConflictField | None:
    for candidate in (cause, getattr(original, "diag", None), original):
        if candidate is None:
            continue
        table_name = getattr(candidate, "table_name", None)
        if table_name is not None and table_name != "users":
            return None
        constraint_name = getattr(candidate, "constraint_name", None)
        if isinstance(constraint_name, str):
            return _USER_UNIQUE_CONSTRAINTS.get(constraint_name)
    return None


def _mysql_conflict_field(original: BaseException) -> UserConflictField | None:
    if len(original.args) != 2 or not isinstance(original.args[1], str):
        return None
    matched = _MYSQL_DUPLICATE_KEY.fullmatch(original.args[1])
    if matched is None:
        return None
    key = matched.group("key")
    if key.startswith("users."):
        key = key.removeprefix("users.")
    return _USER_UNIQUE_CONSTRAINTS.get(key)
