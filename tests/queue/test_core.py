import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.config.database import DatabaseSettings
from app.config.queue import QueueSettings, parse_connection
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.queue.catalog import JobCatalog, JobDefinition
from app.infrastructure.queue.codecs.envelope_json import EnvelopeJsonCodec
from app.infrastructure.queue.contracts.message import MessageEnvelope
from app.infrastructure.queue.drivers.memory import MemoryBackend
from app.infrastructure.queue.errors import InvalidMessageError, QueueConfigurationError, QueueError
from app.infrastructure.queue.manager import QueueManager


@dataclass(frozen=True)
class Job:
    value: int


class Codec:
    def encode(self, job: Job) -> bytes:
        return str(job.value).encode()

    def decode(self, payload: bytes) -> Job:
        return Job(int(payload))


def definition() -> JobDefinition[Job]:
    return JobDefinition("test.job", 1, Job, Codec())


def message() -> MessageEnvelope:
    return MessageEnvelope(uuid4(), "test.job", 1, b"123", datetime(2026, 9, 7))


def manager() -> QueueManager:
    settings = QueueSettings(_env_file=None, default="main", connections={"main": {"driver": "memory", "capacity": 2}})
    queues = QueueManager(settings, DatabaseManager(DatabaseSettings(_env_file=None)))
    queues.catalog.register(definition())
    return queues


def test_worker_settings_are_nested_under_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUEUE_WORKER__CONCURRENCY", "8")
    monkeypatch.setenv("QUEUE_WORKER__SHUTDOWN_TIMEOUT_SECONDS", "45")

    settings = QueueSettings(_env_file=None)

    assert settings.worker.concurrency == 8
    assert settings.worker.shutdown_timeout_seconds == 45


def test_envelope_roundtrip_and_size_and_json_validation() -> None:
    codec = EnvelopeJsonCodec()
    item = message()
    assert codec.decode(codec.encode(item)) == item
    for payload in (b"NaN", b"not-json", b"[Infinity]"):
        with pytest.raises(InvalidMessageError):
            codec.encode(replace(item, payload=payload))
    with pytest.raises(InvalidMessageError):
        EnvelopeJsonCodec(10).encode(item)
    with pytest.raises(InvalidMessageError):
        codec.encode(replace(item, enqueued_at=datetime.now(UTC)))
    for raw in (b"{}", b"null", b"bad"):
        with pytest.raises(InvalidMessageError):
            codec.decode(raw)


def test_catalog_rejects_duplicates_and_unknown_type() -> None:
    catalog = JobCatalog()
    catalog.register(definition())
    assert catalog.encode(Job(7)).payload == b"7"
    with pytest.raises(QueueConfigurationError):
        catalog.register(definition())
    with pytest.raises(QueueConfigurationError):
        catalog.encode(object())
    with pytest.raises(TypeError):
        definition().encode(object())


@pytest.mark.asyncio
async def test_capacity_includes_inflight_and_recovery_never_blocks() -> None:
    backend = MemoryBackend(1)
    await backend.publish("jobs", b"first")
    consumer = await backend.consumer("jobs", 1)
    delivery = await consumer.receive()
    blocked = asyncio.create_task(backend.publish("jobs", b"second"))
    await asyncio.sleep(0)
    assert not blocked.done()
    await asyncio.wait_for(consumer.aclose(), 0.2)
    resumed = await backend.consumer("jobs", 1)
    restored = await resumed.receive()
    assert restored.identity == delivery.identity
    assert restored.payload == b"first"
    with pytest.raises(QueueError):
        await delivery.acknowledge()
    await restored.acknowledge()
    await asyncio.wait_for(blocked, 0.2)
    next_delivery = await resumed.receive()
    assert next_delivery.payload == b"second"
    await next_delivery.acknowledge()
    with pytest.raises(QueueError):
        await next_delivery.acknowledge()
    await resumed.aclose()
    await backend.aclose()


@pytest.mark.asyncio
async def test_shutdown_wakes_blocked_publish_and_receive() -> None:
    backend = MemoryBackend(1)
    await backend.publish("full", b"one")
    consumer = await backend.consumer("empty", 1)
    publish = asyncio.create_task(backend.publish("full", b"two"))
    receive = asyncio.create_task(consumer.receive())
    await asyncio.sleep(0)
    await backend.aclose()
    results = await asyncio.gather(publish, receive, return_exceptions=True)
    assert all(isinstance(item, QueueError) for item in results)


@pytest.mark.asyncio
async def test_manager_is_lazy_and_dispatches_typed_job() -> None:
    queues = manager()
    assert not queues.is_initialized()
    publisher = await queues.get()
    job_id = await publisher.dispatch(Job(42))
    async with queues.consume() as consumer:
        delivery = await consumer.receive()
        item = queues.codec.decode(delivery.payload)
        assert item.job_id == job_id
        assert item.payload == b"42"
        await delivery.acknowledge()
    await queues.aclose()
    with pytest.raises(QueueError):
        await queues.get()
    with pytest.raises(QueueError):
        await publisher.dispatch(Job(43))


@pytest.mark.parametrize(
    "raw",
    [
        {"driver": "memory", "host": "localhost"},
        {"driver": "memory", "capacity": 0},
        {"driver": "rabbitmq"},
        {"driver": "kafka", "bootstrap_servers": []},
        {"driver": "redis", "url": "redis://localhost", "lease_seconds": 0},
    ],
)
def test_strict_driver_configuration(raw: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        parse_connection(raw)
