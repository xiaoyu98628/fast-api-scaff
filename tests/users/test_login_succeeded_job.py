"""验证登录成功任务的编码约束和日志行为。"""

import logging
from typing import cast
from uuid import UUID, uuid7

import pytest

from app.contexts.user.jobs.login_succeeded import LOGIN_SUCCEEDED_MESSAGE, LoginSucceededJob
from app.infrastructure.queue.job import describe_job, encode_job, job_reference


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

    await LoginSucceededJob(user_id=user_id).handle()

    records = [record for record in caplog.records if getattr(record, "event", None) == "user.login_succeeded"]
    assert [record.getMessage() for record in records] == [LOGIN_SUCCEEDED_MESSAGE]
    assert [getattr(record, "details", None) for record in records] == [{"user_id": str(user_id)}]
