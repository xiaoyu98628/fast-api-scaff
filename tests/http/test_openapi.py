import pytest
from httpx import ASGITransport, AsyncClient

from app.bootstrap.app import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings


def build_settings() -> Settings:
    return Settings(
        app=AppSettings(
            name="test-api",
            version="1.2.3",
            _env_file=None,
        ),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )


def test_openapi_metadata_and_swagger_settings() -> None:
    app = create_app(build_settings())
    schema = app.openapi()

    assert schema["info"] == {
        "title": "test-api",
        "summary": "test-api API 文档",
        "description": "基于 FastAPI 构建的后端 API 服务。",
        "version": "1.2.3",
    }
    assert schema["paths"]["/health"]["get"]["tags"] == ["system"]
    assert app.swagger_ui_parameters is not None
    assert app.swagger_ui_parameters["filter"] is True
    assert app.swagger_ui_parameters["displayRequestDuration"] is True


@pytest.mark.asyncio
async def test_documentation_endpoints_are_available() -> None:
    app = create_app(build_settings())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        assert (await client.get("/docs")).status_code == 200
        assert (await client.get("/redoc")).status_code == 200
        assert (await client.get("/openapi.json")).status_code == 200
