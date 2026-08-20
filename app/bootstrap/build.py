from app.bootstrap.container import ApplicationContainer
from app.config.settings import Settings
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager


def build_application_container(settings: Settings) -> ApplicationContainer:
    """构建并连接应用所需的组件。"""
    databases = DatabaseManager(settings.database)
    caches = CacheManager(settings.cache)

    return ApplicationContainer(
        databases=databases,
        caches=caches,
        async_shutdown_callbacks=(databases.aclose, caches.aclose),
    )
