"""验证向量管理器在应用组合根中的装配和懒加载行为。"""

import pytest

from app.bootstrap.build import build_application_container
from app.bootstrap.http.application import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.config.vector import VectorSettings
from app.infrastructure.vector.manager import VectorStoreManager


@pytest.mark.asyncio
async def test_vector_manager_is_available_without_initializing_connections() -> None:
    settings = Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        vector=VectorSettings(
            default="knowledge",
            connections={"knowledge": {"driver": "milvus", "mode": "remote", "host": "127.0.0.1"}},
            _env_file=None,
        ),
        cors=CorsSettings(_env_file=None),
    )
    container = build_application_container(settings)
    app = create_app(settings, container_builder=lambda _: container)

    async with app.router.lifespan_context(app):
        assert isinstance(container.vectors, VectorStoreManager)
        assert container.vectors.connection_names == ("knowledge",)
        assert container.vectors.is_initialized() is False
