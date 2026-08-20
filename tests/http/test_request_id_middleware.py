from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette_context import context
from starlette_context.header_keys import HeaderKeys
from starlette_context.middleware import RawContextMiddleware

from app.bootstrap.app import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings

REQUEST_ID_HEADER = HeaderKeys.request_id.value


def build_settings() -> Settings:
    return Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )


@asynccontextmanager
async def create_test_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            yield client


def test_request_id_is_registered_as_outermost_middleware() -> None:
    app = create_app(build_settings())

    assert app.user_middleware[0].cls is RawContextMiddleware


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
async def test_invalid_request_id_is_rejected() -> None:
    app = create_app(build_settings())

    async with create_test_client(app) as client:
        response = await client.get("/health", headers={REQUEST_ID_HEADER: "invalid request id"})

    assert response.status_code == 400


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
