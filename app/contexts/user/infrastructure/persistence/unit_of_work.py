"""使用 SQLAlchemy Session 实现用户上下文工作单元。"""

import re
import sqlite3
from contextlib import AbstractAsyncContextManager
from types import TracebackType

from anyio import CancelScope
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.user.application.errors import UserConflictError, UserConflictField
from app.contexts.user.domain.repository import UserRepository
from app.contexts.user.domain.session_repository import SessionRepository
from app.contexts.user.infrastructure.persistence.repository import SqlAlchemyUserRepository
from app.contexts.user.infrastructure.persistence.session_repository import SqlAlchemySessionRepository
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
        """保存数据库入口和连接名称，进入上下文时才创建 Session。"""

        self._databases = databases
        self._connection_name = connection_name
        self._session_context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._users: UserRepository | None = None
        self._sessions: SessionRepository | None = None

    @property
    def users(self) -> UserRepository:
        """返回当前事务的用户仓储。"""

        if self._users is None:
            raise RuntimeError("UserUnitOfWork 尚未进入事务上下文")

        return self._users

    @property
    def sessions(self) -> SessionRepository:
        """返回当前事务的会话仓储。"""

        if self._sessions is None:
            raise RuntimeError("UserUnitOfWork 尚未进入事务上下文")
        return self._sessions

    async def __aenter__(self) -> SqlAlchemyUserUnitOfWork:
        """创建一个 Session，并让两个仓储共享同一事务。"""

        self._session_context = self._databases.session(self._connection_name)
        self._session = await self._session_context.__aenter__()
        self._users = SqlAlchemyUserRepository(self._session)
        self._sessions = SqlAlchemySessionRepository(self._session)
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """回滚失败用例、释放 Session，并转换已知唯一约束异常。"""

        cleanup_errors: list[BaseException] = []

        try:
            # 清理阶段屏蔽外部取消，避免遗留未回滚或未关闭的 Session。
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
            # 无论清理是否成功都解除仓储引用，禁止退出后继续使用旧事务。
            self._session_context = None
            self._session = None
            self._users = None
            self._sessions = None

        if cleanup_errors:
            # 同时保留原始业务异常和全部清理错误，避免诊断信息被覆盖。
            errors = ([exception] if exception is not None else []) + cleanup_errors
            raise BaseExceptionGroup("用户事务退出和清理失败", errors) from None

        if isinstance(exception, IntegrityError):
            field = _resolve_user_conflict_field(exception)
            if field is not None:
                raise UserConflictError(field) from exception

    async def commit(self) -> None:
        """提交当前事务，并把已知用户唯一冲突转换为应用异常。"""

        if self._session is None:
            raise RuntimeError("UserUnitOfWork 尚未进入事务上下文")

        try:
            await self._session.commit()
        except IntegrityError as error:
            # 提交失败后先完成回滚，工作单元退出时无需再次依赖异常 Session。
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
    """从各数据库驱动异常中识别用户名或邮箱唯一冲突。"""

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
    """从 PostgreSQL 诊断对象读取 users 表约束名称。"""

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
    """从 MySQL 1062 错误文本提取唯一索引名称。"""

    if len(original.args) != 2 or not isinstance(original.args[1], str):
        return None
    matched = _MYSQL_DUPLICATE_KEY.fullmatch(original.args[1])
    if matched is None:
        return None
    key = matched.group("key")
    if key.startswith("users."):
        key = key.removeprefix("users.")
    return _USER_UNIQUE_CONSTRAINTS.get(key)
