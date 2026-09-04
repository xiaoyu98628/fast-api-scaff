import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from starlette_context import context
from starlette_context.header_keys import HeaderKeys

from app.bootstrap.app import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.interfaces.http.logging import HttpLogEvent
from app.interfaces.http.middleware.request_id import RequestIdMiddleware

REQUEST_ID_HEADER = HeaderKeys.request_id.value


def build_settings(cors: CorsSettings | None = None) -> Settings:
    return Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=cors if cors is not None else CorsSettings(_env_file=None),
    )


@asynccontextmanager
async def create_test_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            yield client


def test_request_id_is_registered_as_outermost_middleware() -> None:
    app = create_app(build_settings())

    assert app.user_middleware[0].cls is RequestIdMiddleware


@pytest.mark.asyncio
async def test_missing_request_id_is_generated_and_available_in_context() -> None:
    app = create_app(build_settings())

    @app.get("/request-id")
    async def read_request_id() -> dict[str, str]:
        request_id = context[HeaderKeys.request_id]
        assert isinstance(request_id, str)
        return {"request_id": request_id}

    async with create_test_client(app) as client:
        response = await client.get("/request-id")

    request_id = response.headers[REQUEST_ID_HEADER]

    assert response.status_code == 200
    assert UUID(request_id).version == 4
    assert response.json() == {"request_id": request_id}
    assert context.exists() is False


@pytest.mark.asyncio
async def test_valid_request_id_is_preserved() -> None:
    app = create_app(build_settings())
    request_id = uuid4().hex

    async with create_test_client(app) as client:
        response = await client.get("/health", headers={REQUEST_ID_HEADER: request_id})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == request_id


@pytest.mark.asyncio
async def test_invalid_request_id_is_rejected_and_logged_safely(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(build_settings())
    logger_name = "app.interfaces.http.request_id"
    logging.getLogger(logger_name).disabled = False
    caplog.set_level(logging.WARNING, logger=logger_name)

    async with create_test_client(app) as client:
        response = await client.get("/health", headers={REQUEST_ID_HEADER: "invalid request id"})

    assert response.status_code == 400
    assert REQUEST_ID_HEADER not in response.headers
    assert response.json() == {
        "code": "4000010101",
        "success": False,
        "message": "请求内容有误，请检查后重试",
        "data": None,
    }

    records = [record for record in caplog.records if record.name == logger_name]
    assert len(records) == 1

    record = records[0]
    assert record.levelno == logging.WARNING
    assert getattr(record, "event", None) is HttpLogEvent.INVALID_REQUEST_ID
    assert getattr(record, "request_id", None) is None
    assert getattr(record, "details", None) == {
        "method": "GET",
        "status_code": 400,
    }
    assert "invalid request id" not in record.getMessage()


@pytest.mark.asyncio
async def test_request_id_is_exposed_to_cross_origin_clients() -> None:
    app = create_app(build_settings())

    async with create_test_client(app) as client:
        response = await client.get("/health", headers={"Origin": "https://app.example.com"})

    exposed_headers = response.headers["access-control-expose-headers"].lower()

    assert response.status_code == 200
    assert REQUEST_ID_HEADER.lower() in exposed_headers
    assert REQUEST_ID_HEADER in response.headers


@pytest.mark.asyncio
async def test_request_id_is_explicitly_exposed_with_credentials_and_wildcard() -> None:
    origin = "https://app.example.com"
    app = create_app(
        build_settings(
            CorsSettings(
                allow_origins=[origin],
                allow_credentials=True,
                expose_headers=["*"],
                _env_file=None,
            )
        )
    )

    async with create_test_client(app) as client:
        client.cookies.set("session", "test-session")
        response = await client.get("/health", headers={"Origin": origin})

    exposed_headers = {header.strip().lower() for header in response.headers["access-control-expose-headers"].split(",")}

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert exposed_headers == {REQUEST_ID_HEADER.lower(), "*"}
    assert REQUEST_ID_HEADER in response.headers


@pytest.mark.asyncio
async def test_cors_preflight_response_has_request_id() -> None:
    app = create_app(build_settings())

    async with create_test_client(app) as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert REQUEST_ID_HEADER in response.headers
