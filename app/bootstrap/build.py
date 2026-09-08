"""作为组合根连接基础设施与各限界上下文。"""

from app.config.settings import Settings
from app.contexts.user.composition import build_user_context
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.cache.providers.registry import DEFAULT_CACHE_PROVIDERS, CacheProviderRegistry
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.database.providers.registry import DEFAULT_DATABASE_PROVIDERS, DatabaseProviderRegistry
from app.infrastructure.http.manager import HttpClientManager
from app.infrastructure.queue.manager import QueueManager
from app.runtime.container import ApplicationContainer


def build_application_container(
    settings: Settings,
    *,
    database_providers: DatabaseProviderRegistry = DEFAULT_DATABASE_PROVIDERS,
    cache_providers: CacheProviderRegistry = DEFAULT_CACHE_PROVIDERS,
) -> ApplicationContainer:
    """构建并连接应用所需的组件。"""

    # Manager 只保存配置并按需创建连接，构建容器本身不会主动访问外部服务。
    databases = DatabaseManager(settings.database, providers=database_providers)
    caches = CacheManager(settings.cache, providers=cache_providers)
    http = HttpClientManager(settings.http)
    queues = QueueManager(settings.queue, databases)
    # 组合根可以知道具体上下文；用户业务的内部装配仍封装在 composition 模块中。
    users = build_user_context(databases, session_ttl_seconds=settings.auth.session_ttl_seconds)

    # 宿主只依赖统一容器，资源关闭顺序由 ApplicationContainer 集中管理。
    return ApplicationContainer(
        databases=databases,
        caches=caches,
        http=http,
        users=users,
        queues=queues,
        async_shutdown_callbacks=(databases.aclose, caches.aclose, http.aclose, queues.aclose),
    )
