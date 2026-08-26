import logging

import pytest
from httpx import ASGITransport, AsyncClient
from starlette_context.middleware import RawContextMiddleware

from app.bootstrap.app import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.logging import LoggingSettings
from app.config.settings import Settings
from app.interfaces.http.logging import HttpLogEvent
from app.interfaces.http.middleware.access_log import AccessLogMiddleware


def build_settings(*, access_enabled: bool = True) -> Settings:
    return Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
        logging=LoggingSettings(access_enabled=access_enabled, _env_file=None),
    )


def test_access_log_runs_inside_request_context() -> None:
    app = create_app(build_settings())

    assert app.user_middleware[0].cls is RawContextMiddleware
    assert app.user_middleware[1].cls is AccessLogMiddleware


@pytest.mark.asyncio
async def test_access_log_contains_request_metadata(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(build_settings())
    logger_name = "app.interfaces.http.access"
    logging.getLogger(logger_name).disabled = False
    caplog.set_level(logging.INFO, logger=logger_name)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/health")

    records = [record for record in caplog.records if record.name == "app.interfaces.http.access"]

    assert response.status_code == 200
    assert len(records) == 1
    assert getattr(records[0], "event", None) is HttpLogEvent.REQUEST_COMPLETED

    details = getattr(records[0], "details", None)
    assert isinstance(details, dict)
    assert details["method"] == "GET"
    assert details["path"] == "/health"
    assert details["route"] == "/health"
    assert details["status_code"] == 200
    assert details["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_access_log_can_be_disabled(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(build_settings(access_enabled=False))
    logger_name = "app.interfaces.http.access"
    logging.getLogger(logger_name).disabled = False
    caplog.set_level(logging.INFO, logger=logger_name)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert not [record for record in caplog.records if record.name == "app.interfaces.http.access"]
