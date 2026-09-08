import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest

from app.infrastructure.queue.errors import RetryableJobError
from app.infrastructure.queue.job import job_reference
from app.infrastructure.queue.policies import JobPolicy
from app.interfaces.worker.executor import JobExecutor
from app.interfaces.worker.resolver import ExecutableJob
from app.interfaces.worker.runner import WorkerRunner
from tests.queue.fakes import (
    Codec,
    FakeQueueBackend,
    Job,
    RecordingFailedJobStore,
    create_queue_manager,
)


@dataclass(frozen=True, slots=True)
class StubBinding:
    handler: Callable[[Job], Awaitable[None]]
    policy: JobPolicy = JobPolicy()

    async def execute(self, payload: bytes) -> None:
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
) -> StubResolver:
    return StubResolver(StubBinding(handler, policy))


@pytest.mark.asyncio
async def test_retry_and_ack_after_success() -> None:
    queues = create_queue_manager()
    attempts: list[int] = []

    async def handle(job: Job) -> None:
        attempts.append(job.value)
        if len(attempts) < 3:
            raise RetryableJobError()

    active_resolver = resolver(handle, policy=JobPolicy(backoff_seconds=()))
    await queues.dispatch(Job(8))
    async with queues.consume() as consumer:
        delivery = await consumer.receive()
        await JobExecutor("main", "default", active_resolver, queues.failed_jobs, queues.codec).execute(delivery)
    assert attempts == [8, 8, 8]
    assert await queues.failed_jobs.list() == []
    await queues.aclose()


@pytest.mark.asyncio
async def test_failed_record_recovery_does_not_execute_again_and_replay_retains_original() -> None:
    queues = create_queue_manager()
    calls: list[int] = []

    async def handle(job: Job) -> None:
        calls.append(job.value)
        raise ValueError("sensitive payload must not appear in failure reason")

    active_resolver = resolver(handle)
    original_id = await queues.dispatch(Job(9))
    executor = JobExecutor("main", "default", active_resolver, queues.failed_jobs, queues.codec)
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
    records = await queues.failed_jobs.list()
    assert len(records) == 1
    assert records[0].reason == "handler_error"
    replay_id = await queues.replay(records[0].failure_id)
    assert replay_id != original_id
    async with queues.consume() as consumer:
        delivery = await consumer.receive()
        message = queues.codec.decode(delivery.payload)
        assert message.replay_of == records[0].failure_id
        await delivery.acknowledge()
    assert len(await queues.failed_jobs.list()) == 1
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
        executor = JobExecutor("main", "default", active_resolver, queues.failed_jobs, queues.codec)
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
        executor = JobExecutor("main", "default", StubResolver(), BrokenStore(), queues.codec)
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
        await JobExecutor("main", "default", active_resolver, queues.failed_jobs, queues.codec).execute(await consumer.receive())
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
    executor = JobExecutor("main", "default", active_resolver, queues.failed_jobs, queues.codec)
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
        task = asyncio.create_task(runner.run(consumer, JobExecutor("main", "default", active_resolver, queues.failed_jobs, queues.codec), stop))
        await asyncio.wait_for(started.wait(), 1)
        stop.set()
        await asyncio.wait_for(task, 1)
    async with queues.consume() as consumer:
        delivery = await consumer.receive()
        assert queues.codec.decode(delivery.payload).payload == b"1"
        await delivery.acknowledge()
    assert await queues.failed_jobs.list() == []
    await queues.aclose()
