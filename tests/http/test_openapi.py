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
    assert schema["paths"]["/health"]["get"]["tags"] == ["health"]
    health_response = schema["paths"]["/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    response_schema_name = health_response["$ref"].rsplit("/", maxsplit=1)[-1]
    response_schema = schema["components"]["schemas"][response_schema_name]
    assert set(response_schema["properties"]) == {"code", "success", "message", "data", "request_id"}
    user_list_parameters = schema["paths"]["/api/v1/users"]["get"]["parameters"]
    assert {parameter["name"] for parameter in user_list_parameters} == {
        "limit",
        "page",
    }
    user_list_response = schema["paths"]["/api/v1/users"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    user_list_envelope = schema["components"]["schemas"][user_list_response["$ref"].rsplit("/", maxsplit=1)[-1]]
    page_reference = next(item["$ref"] for item in user_list_envelope["properties"]["data"]["anyOf"] if "$ref" in item)
    page_schema = schema["components"]["schemas"][page_reference.rsplit("/", maxsplit=1)[-1]]
    meta_reference = page_schema["properties"]["meta"]["$ref"]
    meta_schema = schema["components"]["schemas"][meta_reference.rsplit("/", maxsplit=1)[-1]]
    assert set(page_schema["properties"]) == {"items", "meta"}
    assert set(meta_schema["properties"]) == {"page", "limit", "total", "total_pages"}
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
