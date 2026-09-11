"""验证认证 HTTP 接口、凭据处理和安全响应头。"""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, AsyncMock, Mock
from uuid import UUID, uuid7

import pytest
import pytest_asyncio
from httpx2 import ASGITransport, AsyncClient

from app.bootstrap.http.application import create_app
from app.config.app import AppSettings
from app.config.auth import AuthSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.contexts.user.jobs.login_succeeded import LoginSucceededJob
from app.interfaces.http.controllers.v1.auth.router import _publish_login_succeeded
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.runtime.container import ApplicationContainer
from database.main.model_registry import load_main_database_metadata


def settings() -> Settings:
    return Settings(
        app=AppSettings(_env_file=None),
        auth=AuthSettings(session_ttl_seconds=120, _env_file=None),
        database=DatabaseSettings(_env_file=None, connections={"main": {"driver": "sqlite", "database": ":memory:"}}),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(settings())
    async with app.router.lifespan_context(app):
        engine = await app.state.container.databases.get_engine("main")
        async with engine.begin() as connection:
            await connection.run_sync(load_main_database_metadata().create_all)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
            yield http


@pytest.mark.asyncio
async def test_http_login_me_logout_and_public_crud(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    publish_login_succeeded = AsyncMock()
    monkeypatch.setattr("app.interfaces.http.controllers.v1.auth.router._publish_login_succeeded", publish_login_succeeded)
    created = await client.post("/api/v1/users", json={"username": "alice", "email": "alice@example.com", "password": "password123"})
    assert created.status_code == 201
    user = created.json()["data"]
    login = await client.post("/api/v1/auth/login", json={"username": " ALICE ", "password": "password123"})
    assert login.status_code == 200
    assert login.headers["Cache-Control"] == "no-store"
    token = login.json()["data"]
    assert set(token) == {"access_token", "token_type", "expires_in"}
    assert token["token_type"] == "bearer"
    assert token["expires_in"] == 120
    assert len(token["access_token"]) == 43
    publish_login_succeeded.assert_awaited_once_with(
        ANY,
        UUID(user["id"]),
        login.headers["X-Request-ID"],
    )
    headers = {"Authorization": f"Bearer {token['access_token']}"}

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["data"] == user
    assert me.headers["Cache-Control"] == "no-store"
    assert not {"password", "password_hash", "role", "auth_version", "row_version"} & me.json()["data"].keys()

    for _ in range(2):
        logout = await client.post("/api/v1/auth/logout", headers=headers)
        assert logout.status_code == 204
        assert logout.content == b""
    logged_out = await client.get("/api/v1/auth/me", headers=headers)
    assert logged_out.status_code == 401
    assert logged_out.json()["message"] == ErrorCode.UNAUTHORIZED.message
    assert (await client.get("/api/v1/users")).status_code == 200


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer", "Bearer malformed", "Bearer " + "x" * 43, "Bearer " + "x" * 513])
@pytest.mark.asyncio
async def test_missing_malformed_and_unknown_credentials_use_unified_401(client: AsyncClient, authorization: str | None) -> None:
    response = await client.get("/api/v1/auth/me", headers={"Authorization": authorization} if authorization is not None else {})
    assert response.status_code == 401
    assert response.json()["code"] == "4010010101"
    assert response.json()["message"] == ErrorCode.UNAUTHORIZED.message
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["success"] is False
    assert response.json()["data"] is None
    assert response.json()["request_id"]
    if authorization is not None:
        assert authorization not in response.text


@pytest.mark.asyncio
async def test_login_reports_missing_user_and_does_not_log_secrets(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_login_succeeded = AsyncMock()
    monkeypatch.setattr("app.interfaces.http.controllers.v1.auth.router._publish_login_succeeded", publish_login_succeeded)
    password = "sensitive-test-password"
    created = await client.post("/api/v1/users", json={"username": "alice", "email": "alice@example.com", "password": password})
    user_id = created.json()["data"]["id"]
    missing = await client.post("/api/v1/auth/login", json={"username": "missing", "password": password})
    incorrect = await client.post("/api/v1/auth/login", json={"username": "alice", "password": "wrong-password"})
    await client.patch(f"/api/v1/users/{user_id}/status", json={"status": "disabled"})
    disabled = await client.post("/api/v1/auth/login", json={"username": "alice", "password": password})
    assert missing.status_code == 404
    assert missing.json()["message"] == "用户不存在"
    assert missing.json()["success"] is False
    assert missing.json()["data"] is None
    assert missing.headers["Cache-Control"] == "no-store"
    assert "WWW-Authenticate" not in missing.headers
    assert password not in missing.text
    for result in (incorrect, disabled):
        assert result.status_code == 401
        assert result.json()["message"] == "用户名或密码错误"
        assert result.headers["WWW-Authenticate"] == "Bearer"
    assert password not in caplog.text
    assert "wrong-password" not in caplog.text
    publish_login_succeeded.assert_not_awaited()


@pytest.mark.asyncio
async def test_login_queue_failure_does_not_change_successful_response(client: AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    await client.post("/api/v1/users", json={"username": "alice", "email": "alice@example.com", "password": "password123"})
    caplog.set_level("ERROR", logger="app.interfaces.http.controllers.v1.auth.router")

    response = await client.post("/api/v1/auth/login", json={"username": "alice", "password": "password123"})

    assert response.status_code == 200
    assert any(getattr(record, "event", None) == "user.login_succeeded.dispatch_failed" for record in caplog.records)


@pytest.mark.asyncio
async def test_login_publisher_uses_default_queue() -> None:
    queues = Mock(dispatch=AsyncMock())
    container = cast(ApplicationContainer, SimpleNamespace(queues=queues))
    user_id = uuid7()

    await _publish_login_succeeded(container, user_id, "request-123")

    queues.dispatch.assert_awaited_once_with(
        LoginSucceededJob(user_id=user_id),
        correlation_id="request-123",
    )


@pytest.mark.asyncio
async def test_invalid_login_payload_does_not_echo_password(client: AsyncClient) -> None:
    secret = "do-not-echo-this-password"
    response = await client.post("/api/v1/auth/login", json={"username": "alice", "password": secret, "role": "admin"})
    assert response.status_code == 422
    assert secret not in response.text
    oversized = await client.post("/api/v1/auth/login", json={"username": "alice", "password": "x" * 1025})
    assert oversized.status_code == 422


def test_auth_openapi_documents_bearer_and_unified_responses() -> None:
    schema = create_app(settings()).openapi()
    paths = schema["paths"]
    assert schema["components"]["securitySchemes"]["SessionBearer"]["scheme"] == "bearer"
    assert "security" not in paths["/api/v1/auth/login"]["post"]
    not_found = paths["/api/v1/auth/login"]["post"]["responses"]["404"]
    assert not_found["description"] == "登录用户不存在"
    assert "JsonResponse" in not_found["content"]["application/json"]["schema"]["$ref"]
    assert "security" not in paths["/api/v1/users"]["get"]
    for path, method in (("/api/v1/auth/me", "get"), ("/api/v1/auth/logout", "post")):
        operation = paths[path][method]
        assert operation["security"] == [{"SessionBearer": []}]
        reference = operation["responses"]["401"]["content"]["application/json"]["schema"]["$ref"]
        assert "JsonResponse" in reference
    assert "content" not in paths["/api/v1/auth/logout"]["post"]["responses"]["204"]
    assert schema["components"]["schemas"]["LoginRequest"]["properties"]["password"]["writeOnly"] is True
