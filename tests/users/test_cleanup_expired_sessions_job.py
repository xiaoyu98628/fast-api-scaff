"""验证过期会话清理任务的编码、日志和重试分类。"""

import logging
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import DisconnectionError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.contexts.user.jobs.cleanup_expired_sessions import CleanupExpiredSessionsJob
from app.infrastructure.queue.errors import RetryableJobError
from app.infrastructure.queue.job import describe_job, encode_job, job_reference
from app.interfaces.worker.context import JobExecutionContext


def job_context(auth: object) -> JobExecutionContext:
    """构造只暴露认证应用服务的任务上下文。"""

    return cast(
        JobExecutionContext,
        SimpleNamespace(container=SimpleNamespace(users=SimpleNamespace(auth=auth))),
    )


def test_cleanup_job_has_empty_stable_payload() -> None:
    job = CleanupExpiredSessionsJob()
    encoded = encode_job(job)
    descriptor = describe_job(CleanupExpiredSessionsJob)

    assert encoded.job_type == job_reference(CleanupExpiredSessionsJob)
    assert encoded.version == 1
    assert descriptor.codec.decode(encoded.payload) == job
    assert descriptor.codec.decode(b"{}") == job


@pytest.mark.asyncio
async def test_cleanup_job_calls_application_service_and_logs_count(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.contexts.user.jobs.cleanup_expired_sessions")
    auth = SimpleNamespace(cleanup_expired_sessions=AsyncMock(return_value=3))

    await CleanupExpiredSessionsJob().handle(job_context(auth))

    auth.cleanup_expired_sessions.assert_awaited_once_with()
    record = next(record for record in caplog.records if getattr(record, "event", None) == "user.sessions.expired_removed")
    assert record.getMessage() == "过期用户会话清理完成。"
    assert getattr(record, "details", None) == {"removed_count": 3}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["disconnect", "pool", "invalidated", "permanent"])
async def test_cleanup_job_retries_only_identified_transient_database_failures(failure_kind: str) -> None:
    failures = {
        "disconnect": DisconnectionError("connection lost"),
        "pool": SQLAlchemyTimeoutError("pool exhausted"),
        "invalidated": OperationalError(None, None, Exception("connection lost"), connection_invalidated=True),
        "permanent": OperationalError(None, None, Exception("no such table")),
    }
    error = failures[failure_kind]
    auth = SimpleNamespace(cleanup_expired_sessions=AsyncMock(side_effect=error))

    expected_error = OperationalError if failure_kind == "permanent" else RetryableJobError
    with pytest.raises(expected_error):
        await CleanupExpiredSessionsJob().handle(job_context(auth))

    auth.cleanup_expired_sessions.assert_awaited_once_with()
