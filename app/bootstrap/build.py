from app.bootstrap.container import ApplicationContainer
from app.config.settings import Settings
from app.contexts.user.composition import build_user_context
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.cache.providers.registry import DEFAULT_CACHE_PROVIDERS, CacheProviderRegistry
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.database.providers.registry import DEFAULT_DATABASE_PROVIDERS, DatabaseProviderRegistry


def build_application_container(
    settings: Settings,
    *,
    database_providers: DatabaseProviderRegistry = DEFAULT_DATABASE_PROVIDERS,
    cache_providers: CacheProviderRegistry = DEFAULT_CACHE_PROVIDERS,
) -> ApplicationContainer:
    """构建并连接应用所需的组件。"""
    databases = DatabaseManager(settings.database, providers=database_providers)
    caches = CacheManager(settings.cache, providers=cache_providers)
    users = build_user_context(databases)

    return ApplicationContainer(
        databases=databases,
        caches=caches,
        users=users,
        async_shutdown_callbacks=(databases.aclose, caches.aclose),
    )
