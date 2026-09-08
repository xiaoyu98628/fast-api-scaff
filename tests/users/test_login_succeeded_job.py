import logging

import pytest

from app.contexts.user.jobs.login_succeeded import LOGIN_SUCCEEDED_MESSAGE, LoginSucceededJob
from app.infrastructure.queue.job import describe_job, encode_job, job_reference


def test_login_succeeded_job_uses_fixed_payload() -> None:
    job = LoginSucceededJob()
    encoded = encode_job(job)
    descriptor = describe_job(LoginSucceededJob)

    assert encoded.job_type == job_reference(LoginSucceededJob)
    assert encoded.version == 1
    assert descriptor.codec.decode(encoded.payload) == job
    with pytest.raises(ValueError, match="任务消息不合法"):
        descriptor.codec.decode(b'{"message":"other"}')


@pytest.mark.asyncio
async def test_login_succeeded_job_logs_fixed_message(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.contexts.user.jobs.login_succeeded")

    await LoginSucceededJob().handle()

    assert [record.getMessage() for record in caplog.records if getattr(record, "event", None) == "user.login_succeeded"] == [LOGIN_SUCCEEDED_MESSAGE]
