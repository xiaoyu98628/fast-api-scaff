"""在用户上下文边界组装应用服务及其基础设施实现。"""

from dataclasses import dataclass
from functools import partial

from app.contexts.user.application.auth_service import AuthApplicationService
from app.contexts.user.application.service import UserApplicationService
from app.contexts.user.infrastructure.persistence.unit_of_work import SqlAlchemyUserUnitOfWork
from app.contexts.user.infrastructure.security.password_hasher import PwdlibPasswordHasher
from app.contexts.user.infrastructure.security.session_token import SecureSessionTokenCodec
from app.infrastructure.database.manager import DatabaseManager

_USER_DATABASE_CONNECTION_NAME = "main"


@dataclass(frozen=True, slots=True)
class UserContext:
    """保存用户上下文对应用入口公开的服务。"""

    service: UserApplicationService
    auth: AuthApplicationService


def build_user_context(databases: DatabaseManager, *, session_ttl_seconds: int = 3600) -> UserContext:
    """组装用户上下文及其基础设施实现。"""

    # 工厂保证每个应用用例获得独立 SQLAlchemy Session 和事务边界。
    unit_of_work_factory = partial(SqlAlchemyUserUnitOfWork, databases, connection_name=_USER_DATABASE_CONNECTION_NAME)
    # 两个应用服务共享并发限制器，统一约束进程内密码慢哈希的并发量。
    password_hasher = PwdlibPasswordHasher()

    return UserContext(
        service=UserApplicationService(unit_of_work_factory=unit_of_work_factory, password_hasher=password_hasher),
        auth=AuthApplicationService(
            unit_of_work_factory=unit_of_work_factory,
            password_hasher=password_hasher,
            tokens=SecureSessionTokenCodec(),
            session_ttl_seconds=session_ttl_seconds,
        ),
    )
