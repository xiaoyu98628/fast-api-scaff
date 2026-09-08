"""验证 CORS 预检、普通请求和错误响应行为。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx2 import ASGITransport, AsyncClient

from app.bootstrap.http.application import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings


def build_settings(cors: CorsSettings) -> Settings:
    return Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=cors,
    )


@asynccontextmanager
async def create_test_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            yield client


def test_cors_is_always_registered() -> None:
    app = create_app(build_settings(CorsSettings(_env_file=None)))

    assert app.user_middleware[0].cls is CORSMiddleware


@pytest.mark.asyncio
async def test_allowed_and_rejected_origins_on_regular_requests() -> None:
    app = create_app(
        build_settings(
            CorsSettings(
                allow_origins=["https://app.example.com"],
                _env_file=None,
            )
        )
    )

    assert app.user_middleware[0].cls is CORSMiddleware

    async with create_test_client(app) as client:
        allowed = await client.get("/health", headers={"Origin": "https://app.example.com"})
        rejected = await client.get("/health", headers={"Origin": "https://other.example.com"})

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://app.example.com"
    assert rejected.status_code == 200
    assert "access-control-allow-origin" not in rejected.headers


@pytest.mark.asyncio
async def test_valid_preflight_request() -> None:
    app = create_app(
        build_settings(
            CorsSettings(
                allow_origins=["https://app.example.com"],
                allow_methods=["GET"],
                allow_headers=["X-Request-ID"],
                max_age=1200,
                _env_file=None,
            )
        )
    )

    async with create_test_client(app) as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Request-ID",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"
    assert "GET" in response.headers["access-control-allow-methods"]
    assert "x-request-id" in response.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-max-age"] == "1200"


@pytest.mark.parametrize(
    ("origin", "method"),
    [
        ("https://other.example.com", "GET"),
        ("https://app.example.com", "DELETE"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_preflight_request(origin: str, method: str) -> None:
    app = create_app(
        build_settings(
            CorsSettings(
                allow_origins=["https://app.example.com"],
                allow_methods=["GET"],
                _env_file=None,
            )
        )
    )

    async with create_test_client(app) as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
            },
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_credentials_use_an_explicit_origin() -> None:
    app = create_app(
        build_settings(
            CorsSettings(
                allow_origins=["https://app.example.com"],
                allow_credentials=True,
                _env_file=None,
            )
        )
    )

    async with create_test_client(app) as client:
        response = await client.get("/health", headers={"Origin": "https://app.example.com"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.parametrize("origin", ["https://app.example.com", "https://other.example.com"])
@pytest.mark.parametrize("failure", ["request_id", "internal"])
@pytest.mark.asyncio
async def test_cors_wraps_early_rejections_and_internal_errors(origin: str, failure: str) -> None:
    app = create_app(build_settings(CorsSettings(allow_origins=["https://app.example.com"], _env_file=None)))

    @app.get("/failure")
    async def fail() -> None:
        raise RuntimeError("internal failure")

    headers = {"Origin": origin}
    if failure == "request_id":
        headers["X-Request-ID"] = "invalid-id"
    async with create_test_client(app) as client:
        response = await client.get("/failure", headers=headers)
    assert response.status_code == (400 if failure == "request_id" else 500)
    assert response.headers.get("access-control-allow-origin") == (origin if origin == "https://app.example.com" else None)
    assert "code" in response.json()
    if failure == "internal":
        assert response.json()["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize("origin", ["https://app.example.com", "https://other.example.com"])
@pytest.mark.asyncio
async def test_preflight_bypasses_request_context_and_access_log(origin: str, caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(build_settings(CorsSettings(allow_origins=["https://app.example.com"], _env_file=None)))
    logger = logging.getLogger("app.interfaces.http.access")
    with caplog.at_level(logging.INFO, logger=logger.name):
        async with create_test_client(app) as client:
            response = await client.options(
                "/preflight",
                headers={"Origin": origin, "Access-Control-Request-Method": "GET", "X-Request-ID": "invalid-id"},
            )
    assert response.status_code == (200 if origin == "https://app.example.com" else 400)
    assert "X-Request-ID" not in response.headers
    assert not [record for record in caplog.records if record.name == logger.name]
