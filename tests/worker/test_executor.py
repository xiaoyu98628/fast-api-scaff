"""验证 Worker 任务执行、失败恢复、重试和关闭排空。"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast
from unittest.mock import Mock

import pytest

import app.interfaces.worker.executor as worker_executor
from app.config.settings import Settings
from app.infrastructure.logging.context import RuntimeContextFilter
from app.infrastructure.queue.errors import RetryableJobError
from app.infrastructure.queue.job import job_reference
from app.infrastructure.queue.policies import JobPolicy
from app.interfaces.worker.context import JobExecutionContext, WorkerContext
from app.interfaces.worker.executor import JobExecutor
from app.interfaces.worker.resolver import ExecutableJob
from app.interfaces.worker.runner import WorkerRunner
from app.runtime.container import ApplicationContainer
from tests.queue.fakes import (
    Codec,
    FakeQueueBackend,
    Job,
    RecordingFailedJobStore,
    create_queue_manager,
)

_SETTINGS = cast(Settings, object())
_CONTAINER = cast(ApplicationContainer, object())
_WORKER_CONTEXT = WorkerContext(settings=_SETTINGS, container=_CONTAINER)


@dataclass(frozen=True, slots=True)
class StubBinding:
    handler: Callable[[Job], Awaitable[None]]
    policy: JobPolicy = JobPolicy()
    contexts: list[JobExecutionContext] | None = None

    async def execute(self, payload: bytes, context: JobExecutionContext) -> None:
        if self.contexts is not None:
            self.contexts.append(context)
        await self.handler(Codec().decode(payload))


@dataclass(frozen=True, slots=True)
class StubResolver:
    binding: ExecutableJob | None = None

    def resolve(self, reference: str, version: int) -> ExecutableJob:
        if self.binding is None or reference != job_reference(Job) or version != 1:
            raise KeyError((reference, version))
        return self.binding


async def discard_job(_job: Job) -> None:
    pass


def resolver(
    handler: Callable[[Job], Awaitable[None]] = discard_job,
    *,
    policy: JobPolicy = JobPolicy(),
    contexts: list[JobExecutionContext] | None = None,
) -> StubResolver:
    return StubResolver(StubBinding(handler, policy, contexts))


@pytest.mark.asyncio
async def test_retry_and_ack_after_success() -> None:
    queues = create_queue_manager()
    attempts: list[int] = []
    contexts: list[JobExecutionContext] = []

    async def handle(job: Job) -> None:
        attempts.append(job.value)
        if len(attempts) < 3:
            raise RetryableJobError()

    active_resolver = resolver(handle, policy=JobPolicy(backoff_seconds=()), contexts=contexts)
    job_id = await queues.dispatch(Job(8), correlation_id="request-123")
    async with queues.consume() as consumer:
        delivery = await consumer.receive()
        await JobExecutor("main", "default", active_resolver, queues.failed_jobs, queues.codec, _WORKER_CONTEXT).execute(delivery)
    assert attempts == [8, 8, 8]
    assert len(contexts) == 3
    assert all(context is contexts[0] for context in contexts)
    assert contexts[0].settings is _SETTINGS
    assert contexts[0].container is _CONTAINER
    assert contexts[0].job.id == job_id
    assert contexts[0].job.reference == job_reference(Job)
    assert contexts[0].job.version == 1
    assert contexts[0].job.queue_connection == "main"
    assert contexts[0].job.queue_name == "default"
    assert contexts[0].job.correlation_id == "request-123"
    assert contexts[0].job.replay_of is None
    assert await queues.failed_jobs.list() == []
    await queues.aclose()


@pytest.mark.asyncio
async def test_failed_record_recovery_does_not_execute_again_and_replay_retains_original(monkeypatch: pytest.MonkeyPatch) -> None:
    queues = create_queue_manager()
    calls: list[int] = []
    logger = Mock()
    monkeypatch.setattr(worker_executor, "_logger", logger)

    async def handle(job: Job) -> None:
        calls.append(job.value)
        raise ValueError("sensitive payload must not appear in failure reason")

    active_resolver = resolver(handle)
    original_id = await queues.dispatch(Job(9))
    executor = JobExecutor("main", "default", active_resolver, queues.failed_jobs, queues.codec, _WORKER_CONTEXT)
    async with queues.consume() as consumer:
        original = await consumer.receive()

        class BrokenAck:
            payload = original.payload
            identity = original.identity

            async def acknowledge(self) -> None:
                raise OSError("ack failed")

        with pytest.raises(OSError):
            await executor.execute(BrokenAck())
    async with queues.consume() as consumer:
        await executor.execute(await consumer.receive())
    assert calls == [9]
    level, message = logger.log.call_args.args
    details = logger.log.call_args.kwargs["extra"]["details"]
    assert level == logging.ERROR
    assert message == "queue.job.finished"
    assert details["error_type"] == "builtins.ValueError"
    assert details["stacktrace"]
    assert details["duration_ms"] >= 0
    assert "sensitive payload" not in repr(details)
    records = await queues.failed_jobs.list()
    assert len(records) == 1
    assert records[0].reason == "handler_error"
    assert records[0].error_type == "builtins.ValueError"
    assert records[0].stacktrace
    assert "sensitive payload" not in repr((records[0].error_type, records[0].stacktrace))
    replay_id = await queues.replay(records[0].failure_id)
    assert replay_id != original_id
    replay_contexts: list[JobExecutionContext] = []
    replay_executor = JobExecutor(
        "main",
        "default",
        resolver(contexts=replay_contexts),
        queues.failed_jobs,
        queues.codec,
        _WORKER_CONTEXT,
    )
    async with queues.consume() as consumer:
        delivery = await consumer.receive()
        message = queues.codec.decode(delivery.payload)
        assert message.replay_of == records[0].failure_id
        await replay_executor.execute(delivery)
    assert replay_contexts[0].job.id == replay_id
    assert replay_contexts[0].job.replay_of == records[0].failure_id
    assert len(await queues.failed_jobs.list()) == 1
    await queues.aclose()


@pytest.mark.asyncio
async def test_job_logs_receive_execution_context_without_leaking(caplog: pytest.LogCaptureFixture) -> None:
    queues = create_queue_manager()
    logger = logging.getLogger("app.test.worker.context")
    runtime_filter = RuntimeContextFilter()
    caplog.handler.addFilter(runtime_filter)
    caplog.set_level(logging.INFO)

    async def handle(_job: Job) -> None:
        logger.info("inside job")

    try:
        job_id = await queues.dispatch(Job(3), correlation_id="request-456")
        async with queues.consume() as consumer:
            executor = JobExecutor(
                "main",
                "default",
                resolver(handle),
                queues.failed_jobs,
                queues.codec,
                _WORKER_CONTEXT,
            )
            await executor.execute(await consumer.receive())
        logger.info("outside job")
    finally:
        caplog.handler.removeFilter(runtime_filter)
        await queues.aclose()

    inside = next(record for record in caplog.records if record.getMessage() == "inside job")
    outside = next(record for record in caplog.records if record.getMessage() == "outside job")
    assert getattr(inside, "job_id", None) == str(job_id)
    assert getattr(inside, "job_type", None) == job_reference(Job)
    assert getattr(inside, "job_version", None) == 1
    assert getattr(inside, "queue_connection", None) == "main"
    assert getattr(inside, "queue_name", None) == "default"
    assert getattr(inside, "correlation_id", None) == "request-456"
    assert getattr(inside, "replay_of", None) is None
    assert getattr(outside, "job_id", None) is None
    assert getattr(outside, "correlation_id", None) is None


@pytest.mark.asyncio
async def test_job_dispatch_automatically_propagates_incoming_correlation() -> None:
    queues = create_queue_manager()

    async def publish_child(_job: Job) -> None:
        await queues.dispatch(Job(2))

    parent_id = await queues.dispatch(Job(1), correlation_id="request-789")
    async with queues.consume() as consumer:
        parent = await consumer.receive()
        await JobExecutor(
            "main",
            "default",
            resolver(publish_child),
            queues.failed_jobs,
            queues.codec,
            _WORKER_CONTEXT,
        ).execute(parent)

        child_delivery = await consumer.receive()
        child = queues.codec.decode(child_delivery.payload)
        await child_delivery.acknowledge()

    assert child.job_id != parent_id
    assert child.payload == b"2"
    assert child.correlation_id == "request-789"
    await queues.aclose()


@pytest.mark.asyncio
async def test_malformed_envelope_and_unknown_job_are_recorded() -> None:
    queues = create_queue_manager()
    active_resolver = StubResolver()
    backend = FakeQueueBackend()
    await backend.publish("default", b"broken-json")
    async with queues.consume() as unused:
        del unused
        consumer = await backend.consumer("default", 1)
        executor = JobExecutor("main", "default", active_resolver, queues.failed_jobs, queues.codec, _WORKER_CONTEXT)
        await executor.execute(await consumer.receive())
        await queues.dispatch(Job(1))
        async with queues.consume() as source:
            await executor.execute(await source.receive())
        await consumer.aclose()
    assert {row.reason for row in await queues.failed_jobs.list()} == {"invalid_envelope", "unknown_job"}
    await backend.aclose()
    await queues.aclose()


@pytest.mark.asyncio
async def test_failure_store_error_leaves_delivery_unacknowledged() -> None:
    queues = create_queue_manager()

    class BrokenStore(RecordingFailedJobStore):
        async def save(self, record) -> None:
            raise OSError("database unavailable")

    await queues.dispatch(Job(1))
    async with queues.consume() as consumer:
        delivery = await consumer.receive()
        executor = JobExecutor("main", "default", StubResolver(), BrokenStore(), queues.codec, _WORKER_CONTEXT)
        with pytest.raises(OSError):
            await executor.execute(delivery)
    async with queues.consume() as consumer:
        restored = await consumer.receive()
        assert restored.identity == delivery.identity
        await restored.acknowledge()
    await queues.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("own_timeout", [False, True])
async def test_timeout_is_classified_without_confusing_business_timeout(own_timeout: bool) -> None:
    queues = create_queue_manager()

    async def handle(job: Job) -> None:
        if own_timeout:
            raise TimeoutError("upstream")
        await asyncio.Event().wait()

    active_resolver = resolver(handle, policy=JobPolicy(max_attempts=1, timeout_seconds=0.01))
    await queues.dispatch(Job(1))
    async with queues.consume() as consumer:
        await JobExecutor("main", "default", active_resolver, queues.failed_jobs, queues.codec, _WORKER_CONTEXT).execute(await consumer.receive())
    reason = (await queues.failed_jobs.list())[0].reason
    assert reason == ("handler_timeout_error" if own_timeout else "execution_timeout")
    await queues.aclose()


@pytest.mark.asyncio
async def test_runner_drains_active_job_and_stops_idle_receivers() -> None:
    queues = create_queue_manager()
    started, release, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def handle(job: Job) -> None:
        started.set()
        await release.wait()

    active_resolver = resolver(handle)
    await queues.dispatch(Job(1))
    executor = JobExecutor("main", "default", active_resolver, queues.failed_jobs, queues.codec, _WORKER_CONTEXT)
    async with queues.consume(concurrency=2) as consumer:
        runner = WorkerRunner(concurrency=2, shutdown_timeout=1)
        task = asyncio.create_task(runner.run(consumer, executor, stop))
        await asyncio.wait_for(started.wait(), 1)
        stop.set()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        await asyncio.wait_for(task, 1)
    await queues.aclose()


@pytest.mark.asyncio
async def test_runner_timeout_cancels_inflight_without_ack() -> None:
    queues = create_queue_manager()
    started, stop = asyncio.Event(), asyncio.Event()

    async def handle(job: Job) -> None:
        started.set()
        await asyncio.Event().wait()

    active_resolver = resolver(handle)
    await queues.dispatch(Job(1))
    async with queues.consume() as consumer:
        runner = WorkerRunner(concurrency=1, shutdown_timeout=0.01)
        task = asyncio.create_task(
            runner.run(
                consumer,
                JobExecutor("main", "default", active_resolver, queues.failed_jobs, queues.codec, _WORKER_CONTEXT),
                stop,
            )
        )
        await asyncio.wait_for(started.wait(), 1)
        stop.set()
        await asyncio.wait_for(task, 1)
    async with queues.consume() as consumer:
        delivery = await consumer.receive()
        assert queues.codec.decode(delivery.payload).payload == b"1"
        await delivery.acknowledge()
    assert await queues.failed_jobs.list() == []
    await queues.aclose()
