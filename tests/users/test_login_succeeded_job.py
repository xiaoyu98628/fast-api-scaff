"""验证登录成功任务的编码约束和日志行为。"""

import logging
from datetime import datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid7

import pytest

from app.contexts.user.application.dto import UserDTO
from app.contexts.user.application.errors import UserNotFoundError
from app.contexts.user.domain.values import UserStatus
from app.contexts.user.jobs.login_succeeded import LOGIN_SUCCEEDED_MESSAGE, LoginSucceededJob
from app.infrastructure.queue.job import describe_job, encode_job, job_reference
from app.interfaces.worker.context import JobExecutionContext

_JOB_CONTEXT = cast(JobExecutionContext, object())


def job_context(service: object) -> JobExecutionContext:
    return cast(
        JobExecutionContext,
        SimpleNamespace(container=SimpleNamespace(users=SimpleNamespace(service=service))),
    )


def test_login_succeeded_job_serializes_user_id_and_rejects_custom_message() -> None:
    user_id = uuid7()
    job = LoginSucceededJob(user_id=user_id)
    encoded = encode_job(job)
    descriptor = describe_job(LoginSucceededJob)

    assert encoded.job_type == job_reference(LoginSucceededJob)
    assert encoded.version == 1
    assert descriptor.codec.decode(encoded.payload) == job
    assert descriptor.codec.decode(b"{}") == LoginSucceededJob()
    with pytest.raises(ValueError, match="用户 ID 不合法"):
        LoginSucceededJob(user_id=cast(UUID, "invalid"))
    with pytest.raises(ValueError, match="任务消息不合法"):
        descriptor.codec.decode(f'{{"user_id":"{user_id}","message":"other"}}'.encode())


@pytest.mark.asyncio
async def test_login_succeeded_job_logs_fixed_message(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.contexts.user.jobs.login_succeeded")
    user_id = uuid7()
    user = UserDTO(
        id=user_id,
        username="alice",
        email="alice@example.com",
        status=UserStatus.ACTIVE,
        created_at=datetime(2026, 9, 14, 12, 0),
        updated_at=datetime(2026, 9, 14, 12, 30),
    )
    service = SimpleNamespace(get=AsyncMock(return_value=user))

    await LoginSucceededJob(user_id=user_id).handle(job_context(service))

    records = [record for record in caplog.records if getattr(record, "event", None) == "user.login_succeeded"]
    assert [record.getMessage() for record in records] == [LOGIN_SUCCEEDED_MESSAGE]
    assert [getattr(record, "details", None) for record in records] == [
        {
            "user_id": str(user_id),
            "user": {
                "id": str(user_id),
                "username": "alice",
                "email": "alice@example.com",
                "status": "active",
                "created_at": "2026-09-14T12:00:00",
                "updated_at": "2026-09-14T12:30:00",
            },
        }
    ]
    service.get.assert_awaited_once_with(user_id)


@pytest.mark.asyncio
async def test_legacy_login_succeeded_job_without_user_id_skips_database(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.contexts.user.jobs.login_succeeded")

    await LoginSucceededJob().handle(_JOB_CONTEXT)

    record = next(record for record in caplog.records if getattr(record, "event", None) == "user.login_succeeded")
    assert getattr(record, "details", None) == {"user_id": None, "user": None}


@pytest.mark.asyncio
async def test_login_succeeded_job_treats_deleted_user_as_completed(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="app.contexts.user.jobs.login_succeeded")
    user_id = uuid7()
    service = SimpleNamespace(get=AsyncMock(side_effect=UserNotFoundError(user_id)))

    await LoginSucceededJob(user_id=user_id).handle(job_context(service))

    record = next(record for record in caplog.records if getattr(record, "event", None) == "user.login_succeeded.user_missing")
    assert record.getMessage() == "登录成功任务执行时用户已不存在。"
    assert getattr(record, "details", None) == {"user_id": str(user_id)}
    service.get.assert_awaited_once_with(user_id)


@pytest.mark.asyncio
async def test_login_succeeded_job_propagates_database_failure() -> None:
    user_id = uuid7()
    service = SimpleNamespace(get=AsyncMock(side_effect=RuntimeError("database unavailable")))

    with pytest.raises(RuntimeError, match="database unavailable"):
        await LoginSucceededJob(user_id=user_id).handle(job_context(service))
