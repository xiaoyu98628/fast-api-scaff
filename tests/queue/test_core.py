from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import ClassVar
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.config.database import DatabaseSettings
from app.config.queue import QueueSettings, parse_connection
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.queue.codecs.envelope_json import EnvelopeJsonCodec
from app.infrastructure.queue.contracts.message import MessageEnvelope
from app.infrastructure.queue.errors import InvalidMessageError, QueueConfigurationError, QueueError
from app.infrastructure.queue.job import QueueJob, describe_job, encode_job, job_reference
from app.infrastructure.queue.manager import QueueManager
from tests.queue.fakes import FakeQueueBackend, RecordingFailedJobStore, queue_backend_factory


class Codec:
    def encode(self, job: Job) -> bytes:
        return str(job.value).encode()

    def decode(self, payload: bytes) -> Job:
        return Job(int(payload))


@dataclass(frozen=True)
class Job(QueueJob):
    value: int
    codec: ClassVar[Codec] = Codec()

    async def handle(self) -> None:
        pass


def message() -> MessageEnvelope:
    return MessageEnvelope(uuid4(), job_reference(Job), 1, b"123", datetime(2026, 9, 7))


def manager() -> QueueManager:
    settings = QueueSettings(_env_file=None, default="main", connections={"main": {"driver": "redis", "host": "localhost"}})
    backend = FakeQueueBackend()
    queues = QueueManager(
        settings,
        DatabaseManager(DatabaseSettings(_env_file=None)),
        failed_jobs=RecordingFailedJobStore(),
        factory=queue_backend_factory(backend),
    )
    return queues


def test_sql_failure_store_rejects_unknown_database_on_use() -> None:
    settings = QueueSettings(_env_file=None, failed={"database": "missing"})
    databases = DatabaseManager(DatabaseSettings(_env_file=None))
    queues = QueueManager(settings, databases)

    with pytest.raises(QueueConfigurationError, match="SQL 失败存储数据库未配置"):
        _ = queues.failed_jobs


def test_failure_store_driver_is_not_configurable() -> None:
    with pytest.raises(ValidationError):
        QueueSettings(_env_file=None, failed={"driver": "sql"})


def test_worker_settings_are_nested_under_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUEUE_WORKER__CONCURRENCY", "8")
    monkeypatch.setenv("QUEUE_WORKER__SHUTDOWN_TIMEOUT_SECONDS", "45")

    settings = QueueSettings(_env_file=None)

    assert settings.worker.concurrency == 8
    assert settings.worker.shutdown_timeout_seconds == 45


def test_envelope_roundtrip_and_size_and_json_validation() -> None:
    codec = EnvelopeJsonCodec()
    item = message()
    raw = codec.encode(item)
    assert codec.decode(raw) == item
    with pytest.raises(InvalidMessageError):
        codec.decode(raw.replace(b'"schema_version":2', b'"schema_version":1'))
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


def test_job_descriptor_encodes_subclass_and_rejects_unknown_type() -> None:
    descriptor = describe_job(Job)
    encoded = encode_job(Job(7))
    assert encoded.job_type == job_reference(Job)
    assert encoded.version == 1
    assert encoded.payload == b"7"
    with pytest.raises(QueueConfigurationError):
        encode_job(object())
    with pytest.raises(TypeError):
        descriptor.encode(object())


@pytest.mark.asyncio
async def test_manager_is_lazy_and_dispatches_typed_job() -> None:
    queues = manager()
    assert not queues.is_initialized()
    job_id = await queues.dispatch(Job(42))
    publisher = await queues.get()
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


@pytest.mark.asyncio
async def test_cached_dispatcher_checks_manager_lifecycle() -> None:
    class PermissiveBackend(FakeQueueBackend):
        async def aclose(self) -> None:
            pass

    settings = QueueSettings(_env_file=None, default="main", connections={"main": {"driver": "redis", "host": "localhost"}})
    backend = PermissiveBackend()
    queues = QueueManager(
        settings,
        DatabaseManager(DatabaseSettings(_env_file=None)),
        failed_jobs=RecordingFailedJobStore(),
        factory=queue_backend_factory(backend),
    )
    dispatcher = await queues.get()
    await queues.aclose()

    with pytest.raises(QueueError, match="队列管理器已关闭"):
        await dispatcher.dispatch(Job(1))


@pytest.mark.parametrize(
    "raw",
    [
        {"driver": "memory"},
        {"driver": "rabbitmq"},
        {"driver": "rabbitmq", "url": "amqp://guest:guest@localhost/"},
        {"driver": "kafka", "bootstrap_servers": []},
        {"driver": "redis", "url": "redis://localhost"},
        {"driver": "redis", "host": "localhost", "lease_seconds": 0},
        {"driver": "redis", "host": "localhost", "command_timeout": 1.5},
        {"driver": "redis", "host": "localhost", "default_queue": "q" * 201},
    ],
)
def test_strict_driver_configuration(raw: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        parse_connection(raw)
