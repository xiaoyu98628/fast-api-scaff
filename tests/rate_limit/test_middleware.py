"""验证限流的 HTTP 响应、上下文、客户端地址与排除路径。"""

import logging
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from starlette.types import Scope

from app.bootstrap.build import build_application_container
from app.bootstrap.http.application import create_app
from app.config.cors import CorsSettings
from app.config.rate_limit import RateLimitSettings
from app.config.settings import Settings
from app.infrastructure.rate_limit.contracts import RateLimitDecision, RateLimitUnavailableError
from app.interfaces.http.middleware.rate_limit import RateLimitMiddleware
from tests.rate_limit.test_config import build_settings


def build_app(limiter: AsyncMock, *, enabled: bool = True, fail_open: bool = False) -> FastAPI:
    settings = build_settings(enabled=False)
    settings = settings.model_copy(
        update={
            "rate_limit": RateLimitSettings(enabled=enabled, fail_open=fail_open, _env_file=None),
            "cors": CorsSettings(allow_origins=["https://example.com"], allow_methods=["*"], _env_file=None),
        }
    )

    def build_container(active: Settings):
        return replace(build_application_container(active), rate_limiter=limiter)

    return create_app(settings, container_builder=build_container)


@pytest.mark.asyncio
async def test_rejection_keeps_response_context_and_access_log(caplog: pytest.LogCaptureFixture) -> None:
    limiter = AsyncMock()
    limiter.acquire.return_value = RateLimitDecision(False, 12)
    app = build_app(limiter)
    request_id = "4c287283-5ef1-43ee-a749-f6d95eced597"
    async with app.router.lifespan_context(app):
        with caplog.at_level(logging.INFO):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/missing", headers={"Origin": "https://example.com", "X-Request-ID": request_id})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "12"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "https://example.com"
    assert response.headers["x-request-id"] == request_id
    assert response.json()["request_id"] == request_id
    assert response.json()["code"].startswith("429")
    assert response.json()["success"] is False
    assert any(getattr(record, "event", None) == "http.request.completed" for record in caplog.records)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_open,expected", [(False, 503), (True, 404)])
async def test_dependency_failure_policy(fail_open: bool, expected: int, caplog: pytest.LogCaptureFixture) -> None:
    limiter = AsyncMock()
    limiter.acquire.side_effect = RateLimitUnavailableError("sensitive backend message")
    app = build_app(limiter, fail_open=fail_open)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/missing")
    assert response.status_code == expected
    assert "retry-after" not in response.headers
    if not fail_open:
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["code"].startswith("503")
    assert "sensitive backend message" not in caplog.text
    record = next(record for record in caplog.records if getattr(record, "event", None) == "http.rate_limit.unavailable")
    assert getattr(record, "details")["fail_open"] is fail_open


@pytest.mark.asyncio
async def test_exclusions_and_api_boundary() -> None:
    limiter = AsyncMock()
    limiter.acquire.return_value = RateLimitDecision(False, 1)
    app = build_app(limiter)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for path in ("/health", "/docs", "/openapi.json", "/api-other"):
                assert (await client.get(path)).status_code != 429
            preflight = await client.options("/api/missing", headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"})
            assert preflight.status_code == 200
            limiter.acquire.assert_not_awaited()
            assert (await client.options("/api/missing")).status_code == 429
            assert (await client.get("/api")).status_code == 429
            assert limiter.acquire.await_count == 2


@pytest.mark.asyncio
async def test_disabled_does_not_invoke_limiter() -> None:
    limiter = AsyncMock()
    app = build_app(limiter, enabled=False)
    assert not any(item.cls is RateLimitMiddleware for item in app.user_middleware)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/missing")).status_code == 404
    limiter.acquire.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "address,identity",
    [
        ("192.0.2.1", "ip:192.0.2.1"),
        ("::ffff:192.0.2.1", "ip:192.0.2.1"),
        ("2001:0db8::1", "ip:2001:db8::1"),
        ("testclient", "ip:unknown"),
    ],
)
async def test_server_ip_is_normalized_and_forwarded_headers_ignored(address: str, identity: str) -> None:
    limiter = AsyncMock()
    limiter.acquire.return_value = RateLimitDecision(True)
    app = build_app(limiter)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, client=(address, 1234))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/missing", headers={"X-Forwarded-For": "203.0.113.9", "Forwarded": "for=203.0.113.9"})
    assert response.status_code == 404
    limiter.acquire.assert_awaited_once_with(identity)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/service/api/missing", "/api/missing"])
async def test_root_path_does_not_bypass_limit(path: str) -> None:
    limiter = AsyncMock()
    limiter.acquire.return_value = RateLimitDecision(False, 1)
    app = build_app(limiter)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, root_path="/service")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get(path)).status_code == 429
    limiter.acquire.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_http_scope_passes_through_unchanged() -> None:
    downstream = AsyncMock()
    receive, send = AsyncMock(), AsyncMock()
    scope: Scope = {"type": "websocket", "path": "/api/socket"}
    await RateLimitMiddleware(downstream)(scope, receive, send)
    downstream.assert_awaited_once_with(scope, receive, send)


@pytest.mark.asyncio
async def test_missing_client_uses_shared_unknown_identity() -> None:
    limiter = AsyncMock()
    limiter.acquire.return_value = RateLimitDecision(False, 1)
    app = build_app(limiter)
    async with app.router.lifespan_context(app):
        scope: Scope = {"type": "http", "path": "/api/missing", "method": "GET", "headers": [], "app": app}
        await RateLimitMiddleware(AsyncMock())(scope, AsyncMock(), AsyncMock())
    limiter.acquire.assert_awaited_once_with("ip:unknown")
