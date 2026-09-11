"""验证 HTTP 访问日志的状态、耗时和排除规则。"""

import logging
from asyncio import CancelledError

import pytest
from fastapi import APIRouter
from httpx2 import ASGITransport, AsyncClient

from app.bootstrap.http.application import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.logging import LoggingSettings
from app.config.settings import Settings
from app.interfaces.http.logging import HttpLogEvent
from app.interfaces.http.middleware.access_log import AccessLogMiddleware
from app.interfaces.http.middleware.query_param_decode import encode_query_param
from app.interfaces.http.middleware.request_id import RequestIdMiddleware
from app.interfaces.http.middleware.trace_context import TraceContextMiddleware


def build_settings(
    *,
    access_enabled: bool = True,
    exclude_routes: frozenset[str] = frozenset({"/health"}),
) -> Settings:
    return Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
        logging=LoggingSettings(
            access_enabled=access_enabled,
            access_exclude_routes=exclude_routes,
            _env_file=None,
        ),
    )


def test_access_log_runs_inside_request_context() -> None:
    app = create_app(build_settings())

    assert app.user_middleware[1].cls is RequestIdMiddleware
    assert app.user_middleware[2].cls is TraceContextMiddleware
    assert app.user_middleware[3].cls is AccessLogMiddleware


@pytest.mark.parametrize("query_mode", ["plain", "encoded", "invalid"])
@pytest.mark.asyncio
async def test_access_log_contains_request_metadata(caplog: pytest.LogCaptureFixture, query_mode: str) -> None:
    app = create_app(build_settings())

    @app.get("/items/{item_id}")
    async def read_item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    logger_name = "app.interfaces.http.access"
    logging.getLogger(logger_name).disabled = False
    caplog.set_level(logging.INFO, logger=logger_name)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/items/sensitive-token", params=query_params(query_mode))

    records = [record for record in caplog.records if record.name == "app.interfaces.http.access"]

    assert response.status_code == 200
    assert len(records) == 1
    assert getattr(records[0], "event", None) is HttpLogEvent.REQUEST_COMPLETED

    details = getattr(records[0], "details", None)
    assert isinstance(details, dict)
    assert details["method"] == "GET"
    assert "path" not in details
    assert "sensitive-query" not in str(details)
    assert details["route"] == "/items/sensitive-token"
    assert details["status_code"] == 200
    assert details["duration_ms"] >= 0


@pytest.mark.parametrize("query_mode", ["plain", "encoded", "invalid"])
@pytest.mark.asyncio
async def test_access_log_distinguishes_same_route_under_different_prefixes(caplog: pytest.LogCaptureFixture, query_mode: str) -> None:
    app = create_app(build_settings())
    shared_router = APIRouter()

    @shared_router.get("/items/{item_id}")
    async def read_shared_item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    app.include_router(shared_router, prefix="/public")
    app.include_router(shared_router, prefix="/internal")

    logger_name = "app.interfaces.http.access"
    logging.getLogger(logger_name).disabled = False
    caplog.set_level(logging.INFO, logger=logger_name)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        public_response = await client.get("/public/items/public-id", params=query_params(query_mode))
        internal_response = await client.get("/internal/items/internal-id", params=query_params(query_mode))

    records = [record for record in caplog.records if record.name == logger_name]
    details: list[dict[str, object]] = []
    for record in records:
        item = getattr(record, "details", None)
        assert isinstance(item, dict)
        details.append(item)

    assert public_response.status_code == 200
    assert internal_response.status_code == 200
    assert [item["route"] for item in details] == ["/public/items/public-id", "/internal/items/internal-id"]
    assert "sensitive-query" not in str(details)


@pytest.mark.asyncio
async def test_unmatched_request_logs_full_path_without_query(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(build_settings())
    logger_name = "app.interfaces.http.access"
    logging.getLogger(logger_name).disabled = False
    caplog.set_level(logging.WARNING, logger=logger_name)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/missing/request-path", params={"secret": "query-value"})

    record = next(record for record in caplog.records if record.name == logger_name)
    details = getattr(record, "details", None)

    assert response.status_code == 404
    assert isinstance(details, dict)
    assert details["route"] == "/missing/request-path"
    assert "query-value" not in str(details)


@pytest.mark.asyncio
async def test_access_log_can_be_disabled(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(build_settings(access_enabled=False))

    @app.get("/visible")
    async def visible() -> None:
        return None

    logger_name = "app.interfaces.http.access"
    logging.getLogger(logger_name).disabled = False
    caplog.set_level(logging.INFO, logger=logger_name)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/visible")

    assert response.status_code == 200
    assert not [record for record in caplog.records if record.name == "app.interfaces.http.access"]


@pytest.mark.parametrize("query_mode", ["plain", "encoded", "invalid"])
@pytest.mark.asyncio
async def test_successful_excluded_route_is_not_logged(caplog: pytest.LogCaptureFixture, query_mode: str) -> None:
    app = create_app(build_settings())
    logger_name = "app.interfaces.http.access"
    logging.getLogger(logger_name).disabled = False
    caplog.set_level(logging.INFO, logger=logger_name)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/health", params=query_params(query_mode))

    assert response.status_code == 200
    assert not [record for record in caplog.records if record.name == logger_name]


@pytest.mark.parametrize("query_mode", ["plain", "encoded", "invalid"])
@pytest.mark.asyncio
async def test_failed_excluded_route_is_logged(caplog: pytest.LogCaptureFixture, query_mode: str) -> None:
    app = create_app(build_settings(exclude_routes=frozenset({"/excluded"})))

    @app.get("/excluded")
    async def excluded() -> None:
        raise RuntimeError("failed")

    logger_name = "app.interfaces.http.access"
    logging.getLogger(logger_name).disabled = False
    caplog.set_level(logging.ERROR, logger=logger_name)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/excluded", params=query_params(query_mode))

    record = next(record for record in caplog.records if record.name == logger_name)
    details = getattr(record, "details", None)

    assert response.status_code == 500
    assert isinstance(details, dict)
    assert details["route"] == "/excluded"
    assert details["status_code"] == 500


@pytest.mark.parametrize("query_mode", ["plain", "encoded", "invalid"])
@pytest.mark.asyncio
async def test_cancelled_request_is_logged_as_499(caplog: pytest.LogCaptureFixture, query_mode: str) -> None:
    app = create_app(build_settings())

    @app.get("/cancelled")
    async def cancelled() -> None:
        raise CancelledError

    logger_name = "app.interfaces.http.access"
    logging.getLogger(logger_name).disabled = False
    caplog.set_level(logging.WARNING, logger=logger_name)

    with pytest.raises(CancelledError):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await client.get("/cancelled", params=query_params(query_mode))

    record = next(record for record in caplog.records if record.name == logger_name)
    details = getattr(record, "details", None)

    assert isinstance(details, dict)
    assert details["status_code"] == 499
    assert details["failed"] is True
    assert details["failure_type"] == "CancelledError"


def query_params(mode: str) -> dict[str, str]:
    if mode == "encoded":
        return {"f": encode_query_param({"filter": "sensitive-query"})}
    if mode == "invalid":
        return {"f": "not-base64!"}
    return {"filter": "sensitive-query"}
