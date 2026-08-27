import logging
from enum import StrEnum
from hashlib import sha256
from time import perf_counter

from sqlalchemy import event
from sqlalchemy.engine import Connection, ExceptionContext
from sqlalchemy.ext.asyncio import AsyncEngine

from app.infrastructure.database.connections.spec import DatabaseEngineSpec
from app.infrastructure.logging.record import log_extra

_DATABASE_LOGGER = logging.getLogger("app.infrastructure.database")
_QUERY_TIMER_KEY = "application_query_started_at"


class DatabaseLogEvent(StrEnum):
    RESOURCE_CREATED = "database.resource.created"
    RESOURCE_CREATE_FAILED = "database.resource.create_failed"
    RESOURCE_CLOSED = "database.resource.closed"
    RESOURCE_CLOSE_FAILED = "database.resource.close_failed"
    QUERY_COMPLETED = "database.query.completed"
    QUERY_SLOW = "database.query.slow"
    QUERY_FAILED = "database.query.failed"


def configure_database_logging(
    engine: AsyncEngine,
    *,
    connection_name: str,
    spec: DatabaseEngineSpec,
) -> None:
    """为一个异步 Engine 注册不包含 SQL 参数的执行日志。"""
    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def before_cursor_execute(
        connection: Connection,
        _cursor: object,
        _statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        started_stack = connection.info.setdefault(_QUERY_TIMER_KEY, [])
        if isinstance(started_stack, list):
            started_stack.append(perf_counter())

    @event.listens_for(sync_engine, "after_cursor_execute")
    def after_cursor_execute(
        connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        executemany: bool,
    ) -> None:
        duration_ms = _pop_duration_ms(connection)
        slow = _is_slow_query(duration_ms, spec.slow_query_ms)

        if slow:
            event_name = DatabaseLogEvent.QUERY_SLOW
            level = logging.WARNING
        elif spec.log_queries:
            event_name = DatabaseLogEvent.QUERY_COMPLETED
            level = logging.INFO
        else:
            return

        details: dict[str, object] = {
            "connection": connection_name,
            "duration_ms": duration_ms,
            "executemany": executemany,
        }
        details.update(_describe_statement(statement, include_statement=spec.log_queries))

        _DATABASE_LOGGER.log(level, "Database query completed", extra=log_extra(event_name, **details))

    @event.listens_for(sync_engine, "handle_error")
    def handle_error(exception_context: ExceptionContext) -> None:
        exception = exception_context.original_exception
        duration_ms = _pop_duration_ms(exception_context.connection)
        details: dict[str, object] = {
            "connection": connection_name,
            "duration_ms": duration_ms,
            "error_type": type(exception).__name__,
        }
        error_code = _get_database_error_code(exception)
        if error_code is not None:
            details["error_code"] = error_code

        details.update(_describe_statement(exception_context.statement, include_statement=spec.log_queries))

        _DATABASE_LOGGER.error(
            "Database query failed",
            extra=log_extra(DatabaseLogEvent.QUERY_FAILED, **details),
        )


def _pop_duration_ms(connection: Connection | None) -> float | None:
    if connection is None:
        return None

    started_stack = connection.info.get(_QUERY_TIMER_KEY)
    if not isinstance(started_stack, list) or not started_stack:
        return None

    started_at = started_stack.pop()
    if not isinstance(started_at, float):
        return None

    return round((perf_counter() - started_at) * 1000, 3)


def _is_slow_query(duration_ms: float | None, threshold_ms: int) -> bool:
    return threshold_ms > 0 and duration_ms is not None and duration_ms >= threshold_ms


def _describe_statement(statement: str | None, *, include_statement: bool) -> dict[str, object]:
    if statement is None:
        return {}

    normalized = " ".join(statement.split())
    operation, _separator, _remainder = normalized.partition(" ")
    details: dict[str, object] = {
        "operation": operation.upper(),
        "statement_id": sha256(normalized.encode("utf-8")).hexdigest()[:16],
    }

    if include_statement:
        details["statement"] = statement

    return details


def _get_database_error_code(exception: BaseException) -> str | int | None:
    for attribute in ("sqlstate", "pgcode"):
        value = getattr(exception, attribute, None)
        if isinstance(value, str) and value:
            return value

    arguments = getattr(exception, "args", ())
    if arguments and isinstance(arguments[0], int):
        return arguments[0]

    return None
