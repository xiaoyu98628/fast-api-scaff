from contextlib import AbstractAsyncContextManager
from types import TracebackType

from anyio import CancelScope
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.user.application.errors import UserConflictError, UserConflictField
from app.contexts.user.domain.repository import UserRepository
from app.contexts.user.infrastructure.persistence.repository import SqlAlchemyUserRepository
from app.infrastructure.database.manager import DatabaseManager

_USER_UNIQUE_CONSTRAINT_MARKERS: dict[UserConflictField, tuple[str, ...]] = {
    "username": ("uq_users_username", "users_username_key", "users.username"),
    "email": ("uq_users_email", "users_email_key", "users.email"),
}


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

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("UserUnitOfWork 尚未进入事务上下文")

        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            field = _resolve_user_conflict_field(error)
            if field is None:
                raise

            raise UserConflictError(field) from error


def _resolve_user_conflict_field(error: IntegrityError) -> UserConflictField | None:
    details = _integrity_error_details(error)

    for field, markers in _USER_UNIQUE_CONSTRAINT_MARKERS.items():
        if any(marker in details for marker in markers):
            return field

    return None


def _integrity_error_details(error: IntegrityError) -> str:
    original = error.orig
    candidates = (
        original,
        getattr(original, "__cause__", None),
        getattr(original, "diag", None),
    )
    details: list[str] = []

    for candidate in candidates:
        if candidate is None:
            continue

        details.append(str(candidate))
        constraint_name = getattr(candidate, "constraint_name", None)
        if isinstance(constraint_name, str):
            details.append(constraint_name)

    return " ".join(details).lower()
