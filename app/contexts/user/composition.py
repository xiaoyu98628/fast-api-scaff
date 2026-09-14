"""在用户上下文边界组装应用服务及其基础设施实现。"""

from dataclasses import dataclass
from functools import partial

from app.config.settings import Settings
from app.contexts.user.application.auth_service import AuthApplicationService
from app.contexts.user.application.service import UserApplicationService
from app.contexts.user.infrastructure.persistence.unit_of_work import SqlAlchemyUserUnitOfWork
from app.contexts.user.infrastructure.security.password_hasher import PwdlibPasswordHasher
from app.contexts.user.infrastructure.security.redis_login_attempts import RedisLoginAttemptLimiter
from app.contexts.user.infrastructure.security.session_token import SecureSessionTokenCodec
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager

_USER_DATABASE_CONNECTION_NAME = "main"


@dataclass(frozen=True, slots=True)
class UserContext:
    """保存用户上下文对应用入口公开的服务。"""

    service: UserApplicationService
    auth: AuthApplicationService


def build_user_context(
    settings: Settings,
    databases: DatabaseManager,
    caches: CacheManager | None = None,
) -> UserContext:
    """根据全局配置组装用户上下文及其基础设施实现。"""

    # 工厂保证每个应用用例获得独立 SQLAlchemy Session 和事务边界。
    unit_of_work_factory = partial(SqlAlchemyUserUnitOfWork, databases, connection_name=_USER_DATABASE_CONNECTION_NAME)
    # 两个应用服务共享并发限制器，统一约束进程内密码慢哈希的并发量。
    password_hasher = PwdlibPasswordHasher()
    # 全局配置只在组合层拆解，Application 和 Domain 仍只接收自身需要的窄依赖。
    auth_settings = settings.auth
    login_attempts = None
    if auth_settings.login_limit_cache is not None:
        if caches is None:
            raise CacheConfigurationError("启用登录限制时必须提供缓存管理器")

        # 组合阶段只校验驱动能力，不建立 Redis 网络连接。
        cache_name = caches.require_redis(auth_settings.login_limit_cache)
        login_attempts = RedisLoginAttemptLimiter(
            client_factory=partial(caches.get_redis, cache_name),
            max_failures=auth_settings.login_max_failures,
            failure_window_seconds=auth_settings.login_failure_window_seconds,
            lock_seconds=auth_settings.login_lock_seconds,
        )

    return UserContext(
        service=UserApplicationService(unit_of_work_factory=unit_of_work_factory, password_hasher=password_hasher),
        auth=AuthApplicationService(
            unit_of_work_factory=unit_of_work_factory,
            password_hasher=password_hasher,
            tokens=SecureSessionTokenCodec(),
            session_ttl_seconds=auth_settings.session_ttl_seconds,
            login_attempts=login_attempts,
        ),
    )
