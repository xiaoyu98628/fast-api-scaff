import logging
from typing import Annotated

import pytest
from fastapi import HTTPException, Query
from httpx import ASGITransport, AsyncClient

from app.bootstrap.app import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.infrastructure.logging.context import RequestContextFilter
from app.interfaces.http.exceptions.error import HttpError
from app.interfaces.http.logging import HttpLogEvent
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.interfaces.http.shared.response.codes.success_code import SuccessCode


def build_settings(service_code: str = "001", *, debug: bool = False) -> Settings:
    return Settings(
        app=AppSettings(service_code=service_code, debug=debug, _env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )


def test_http_error_rejects_success_code() -> None:
    with pytest.raises(ValueError, match="4xx 或 5xx"):
        HttpError(SuccessCode.OK)


@pytest.mark.asyncio
async def test_validation_error_uses_unified_response() -> None:
    app = create_app(build_settings(service_code="321"))

    @app.get("/validation")
    async def validation(limit: Annotated[int, Query(ge=1)]) -> None:
        return None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/validation", params={"limit": 0})

    body = response.json()
    validation_error = body["data"][0]

    assert response.status_code == 422
    assert body["code"] == "4223210101"
    assert body["success"] is False
    assert body["message"] == ErrorCode.VALIDATION_ERROR.message
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert validation_error["location"] == ["query", "limit"]
    assert set(validation_error) == {"type", "location", "message"}


@pytest.mark.asyncio
async def test_route_and_method_errors_use_unified_response() -> None:
    app = create_app(build_settings(service_code="321"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        missing = await client.get("/missing")
        method_not_allowed = await client.post("/health")

    assert missing.status_code == 404
    assert missing.json()["code"] == "4043210101"
    assert missing.json()["message"] == ErrorCode.ROUTE_NOT_FOUND.message
    assert missing.json()["request_id"] == missing.headers["X-Request-ID"]

    assert method_not_allowed.status_code == 405
    assert method_not_allowed.headers["Allow"] == "GET"
    assert method_not_allowed.json()["code"] == "4053210101"
    assert method_not_allowed.json()["message"] == ErrorCode.METHOD_NOT_ALLOWED.message
    assert method_not_allowed.json()["request_id"] == method_not_allowed.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_http_exception_preserves_message_and_headers() -> None:
    app = create_app(build_settings())

    @app.get("/protected")
    async def protected() -> None:
        raise HTTPException(
            status_code=401,
            detail="登录凭证已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/protected")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["code"] == "4010010101"
    assert response.json()["message"] == "登录凭证已过期"


@pytest.mark.asyncio
async def test_unlisted_http_status_preserves_status_and_hides_server_detail() -> None:
    app = create_app(build_settings())

    @app.get("/teapot")
    async def teapot() -> None:
        raise HTTPException(status_code=418, detail={"reason": "short and stout"})

    @app.get("/unavailable")
    async def unavailable() -> None:
        raise HTTPException(
            status_code=503,
            detail="sensitive upstream detail",
            headers={"Retry-After": "30"},
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        teapot_response = await client.get("/teapot")
        unavailable_response = await client.get("/unavailable")

    assert teapot_response.status_code == 418
    assert teapot_response.json()["code"] == "4180010101"
    assert teapot_response.json()["data"] == {"reason": "short and stout"}

    assert unavailable_response.status_code == 503
    assert unavailable_response.headers["Retry-After"] == "30"
    assert unavailable_response.json()["code"] == "5030010101"
    assert unavailable_response.json()["message"] == ErrorCode.INTERNAL_ERROR.message
    assert "sensitive upstream detail" not in unavailable_response.text


@pytest.mark.asyncio
async def test_http_error_uses_declared_code_and_data() -> None:
    app = create_app(build_settings())

    @app.get("/users/current")
    async def current_user() -> None:
        raise HttpError(
            ErrorCode.RESOURCE_NOT_FOUND,
            data={"resource": "user"},
            headers={"X-Error-Source": "users"},
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/users/current")

    assert response.status_code == 404
    assert response.headers["X-Error-Source"] == "users"
    assert response.json()["code"] == "4040010102"
    assert response.json()["message"] == ErrorCode.RESOURCE_NOT_FOUND.message
    assert response.json()["data"] == {"resource": "user"}


@pytest.mark.asyncio
async def test_server_http_error_hides_internal_detail() -> None:
    app = create_app(build_settings())

    @app.get("/expected-failure")
    async def expected_failure() -> None:
        raise HttpError(
            ErrorCode.INTERNAL_ERROR,
            message="sensitive internal message",
            data={"secret": "sensitive internal data"},
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/expected-failure")

    assert response.status_code == 500
    assert response.json()["code"] == "5000010101"
    assert response.json()["message"] == ErrorCode.INTERNAL_ERROR.message
    assert "sensitive internal" not in response.text


@pytest.mark.asyncio
async def test_unexpected_exception_uses_request_context_and_cors(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(build_settings())
    logger_name = "app.interfaces.http.exception"
    logging.getLogger(logger_name).disabled = False
    caplog.set_level(logging.ERROR, logger=logger_name)
    request_context_filter = RequestContextFilter()
    caplog.handler.addFilter(request_context_filter)

    @app.get("/unexpected-failure")
    async def unexpected_failure() -> None:
        raise RuntimeError("sensitive internal detail")

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(
                "/unexpected-failure",
                headers={"Origin": "https://app.example.com"},
            )
    finally:
        caplog.handler.removeFilter(request_context_filter)

    body = response.json()

    assert response.status_code == 500
    assert body["code"] == "5000010101"
    assert body["message"] == ErrorCode.INTERNAL_ERROR.message
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["access-control-allow-origin"] == "*"
    assert "sensitive internal detail" not in response.text

    exception_record = next(record for record in caplog.records if getattr(record, "event", None) is HttpLogEvent.UNHANDLED_EXCEPTION)
    assert exception_record.exc_info is not None
    assert getattr(exception_record, "request_id", None) == body["request_id"]


@pytest.mark.asyncio
async def test_debug_mode_preserves_starlette_debug_response() -> None:
    app = create_app(build_settings(debug=True))

    @app.get("/debug-failure")
    async def debug_failure() -> None:
        raise RuntimeError("visible debug detail")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/debug-failure")

    assert response.status_code == 500
    assert "visible debug detail" in response.text
