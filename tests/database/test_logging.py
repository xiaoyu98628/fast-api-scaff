"""验证数据库查询日志的脱敏、计时和错误分类。"""

import logging
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

import app.infrastructure.database.factory as database_factory_module
import app.infrastructure.database.logging as database_logging_module
from app.config.database import DatabaseSettings
from app.infrastructure.database.errors import DatabaseDriverError
from app.infrastructure.database.factory import close_database_resource
from app.infrastructure.database.logging import DatabaseLogEvent
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.database.providers.sqlite import SQLiteDatabaseProvider
from app.infrastructure.database.resource import DatabaseResource


def build_manager(*, echo: bool = False, slow_query_ms: int = 500) -> DatabaseManager:
    return DatabaseManager(
        DatabaseSettings(
            default="main",
            connections={
                "main": {
                    "driver": "sqlite",
                    "database": ":memory:",
                    "echo": echo,
                    "slow_query_ms": slow_query_ms,
                }
            },
            _env_file=None,
        )
    )


@pytest.mark.asyncio
async def test_database_resource_lifecycle_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    manager = build_manager()
    caplog.set_level(logging.INFO, logger="app.infrastructure.database")

    await manager.get_engine()
    await manager.aclose()

    events = [record.event for record in caplog.records if hasattr(record, "event")]

    assert DatabaseLogEvent.RESOURCE_CREATED in events
    assert DatabaseLogEvent.RESOURCE_CLOSED in events


@pytest.mark.asyncio
async def test_database_creation_failure_log_excludes_driver_error_message(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "PRIVATE_DATABASE_DRIVER_TOKEN"
    definition = SQLiteDatabaseProvider().prepare({"driver": "sqlite", "database": ":memory:"})
    monkeypatch.setattr(
        database_factory_module,
        "create_async_engine",
        Mock(side_effect=ModuleNotFoundError(secret)),
    )
    caplog.set_level(logging.ERROR, logger="app.infrastructure.database")

    with pytest.raises(DatabaseDriverError, match="无法加载"):
        await database_factory_module.create_database_resource("main", definition)

    record = next(record for record in caplog.records if getattr(record, "event", None) is DatabaseLogEvent.RESOURCE_CREATE_FAILED)
    assert record.exc_info is None
    assert getattr(record, "details")["error_type"] == "builtins.ModuleNotFoundError"
    assert getattr(record, "details")["stacktrace"]
    assert secret not in repr(record.__dict__)


@pytest.mark.asyncio
async def test_database_close_failure_log_excludes_driver_error_message(caplog: pytest.LogCaptureFixture) -> None:
    secret = "PRIVATE_DATABASE_CLOSE_TOKEN"
    engine = SimpleNamespace(
        dispose=AsyncMock(side_effect=RuntimeError(secret)),
        url=SimpleNamespace(drivername="test+async"),
    )
    resource = cast(DatabaseResource, SimpleNamespace(connection_name="main", engine=engine))
    caplog.set_level(logging.ERROR, logger="app.infrastructure.database")

    with pytest.raises(RuntimeError, match=secret):
        await close_database_resource(resource)

    record = next(record for record in caplog.records if getattr(record, "event", None) is DatabaseLogEvent.RESOURCE_CLOSE_FAILED)
    assert record.exc_info is None
    assert getattr(record, "details")["error_type"] == "builtins.RuntimeError"
    assert getattr(record, "details")["stacktrace"]
    assert secret not in repr(record.__dict__)


@pytest.mark.asyncio
async def test_echo_logs_statement_without_parameters(caplog: pytest.LogCaptureFixture) -> None:
    manager = build_manager(echo=True)
    caplog.set_level(logging.INFO, logger="app.infrastructure.database")

    async with manager.session() as session:
        await session.execute(text("SELECT :secret"), {"secret": "sensitive-value"})

    query_record = next(record for record in caplog.records if getattr(record, "event", None) is DatabaseLogEvent.QUERY_COMPLETED)

    details = getattr(query_record, "details", None)
    assert isinstance(details, dict)
    assert "sensitive-value" not in str(details)
    assert "parameters" not in details
    await manager.aclose()


@pytest.mark.asyncio
async def test_failed_query_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    manager = build_manager()
    caplog.set_level(logging.ERROR, logger="app.infrastructure.database")

    with pytest.raises(DBAPIError):
        async with manager.session() as session:
            await session.execute(text("SELECT * FROM missing_table"))

    record = next(record for record in caplog.records if getattr(record, "event", None) is DatabaseLogEvent.QUERY_FAILED)

    details = getattr(record, "details", None)
    assert isinstance(details, dict)
    assert details["connection"] == "main"
    assert details["operation"] == "SELECT"
    assert isinstance(details["statement_id"], str)
    assert "statement" not in details
    assert "missing_table" not in str(details)
    assert record.exc_info is None
    await manager.aclose()


@pytest.mark.asyncio
async def test_slow_query_is_logged_when_echo_is_disabled(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter((10.0, 10.6))
    monkeypatch.setattr(database_logging_module, "perf_counter", lambda: next(ticks))
    manager = build_manager(echo=False, slow_query_ms=500)
    caplog.set_level(logging.WARNING, logger="app.infrastructure.database")

    async with manager.session() as session:
        await session.execute(text("SELECT 1"))

    record = next(record for record in caplog.records if getattr(record, "event", None) is DatabaseLogEvent.QUERY_SLOW)

    details = getattr(record, "details", None)
    assert isinstance(details, dict)
    assert details["connection"] == "main"
    assert details["duration_ms"] == 600.0
    assert details["operation"] == "SELECT"
    assert "statement" not in details
    await manager.aclose()
