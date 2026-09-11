"""验证队列消息信封、任务策略和管理器核心契约。"""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.config.database import DatabaseSettings
from app.config.queue import QueueConnection, QueueSettings, RabbitMQQueueSettings, RedisQueueSettings, WorkerSettings, parse_connection
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.queue.codecs.envelope_json import EnvelopeJsonCodec
from app.infrastructure.queue.contracts.message import MessageEnvelope
from app.infrastructure.queue.errors import InvalidMessageError, QueueConfigurationError, QueueError
from app.infrastructure.queue.job import describe_job, encode_job, job_reference
from app.infrastructure.queue.manager import QueueManager
from app.runtime.trace import TraceContext, bind_trace_context
from tests.queue.fakes import (
    FakeQueueBackend,
    FakeQueueConsumer,
    Job,
    RecordingFailedJobStore,
    create_queue_manager,
    queue_backend_factory,
)


def message() -> MessageEnvelope:
    return MessageEnvelope(uuid4(), job_reference(Job), 1, b"123", datetime(2026, 9, 7))


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


@pytest.mark.parametrize("concurrency", [True, False, 1.0, 4.5, "4.0", " 4 ", object()])
def test_worker_concurrency_rejects_implicit_numeric_conversion(concurrency: object) -> None:
    with pytest.raises(ValidationError):
        WorkerSettings.model_validate({"concurrency": concurrency})


@pytest.mark.parametrize("queue", ["", ".", "..", "jobs/urgent", "jobs urgent", "任务"])
def test_connection_rejects_non_portable_queue_names(queue: str) -> None:
    with pytest.raises(ValidationError):
        RedisQueueSettings(driver="redis", host="localhost", default_queue=queue)


@pytest.mark.parametrize("raw", [{"driver": "redis"}, {"driver": "rabbitmq"}])
def test_queue_driver_defaults_host_to_loopback(raw: dict[str, object]) -> None:
    connection = parse_connection(raw)

    assert isinstance(connection, RedisQueueSettings | RabbitMQQueueSettings)
    assert connection.host == "127.0.0.1"


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
    queues = create_queue_manager()
    assert not queues.is_initialized()
    job_id = await queues.dispatch(Job(42))
    publisher = await queues.get()
    async with queues.consume() as consumer:
        delivery = await consumer.receive()
        item = queues.codec.decode(delivery.payload)
        assert item.job_id == job_id
        assert item.payload == b"42"
        assert item.correlation_id is None
        await delivery.acknowledge()
    await queues.aclose()
    with pytest.raises(QueueError):
        await queues.get()
    with pytest.raises(QueueError):
        await publisher.dispatch(Job(43))


@pytest.mark.asyncio
async def test_dispatch_inherits_runtime_correlation_and_allows_explicit_override() -> None:
    queues = create_queue_manager()

    with bind_trace_context(TraceContext(correlation_id="request-123", request_id="request-123")):
        inherited_id = await queues.dispatch(Job(1))
        overridden_id = await queues.dispatch(Job(2), correlation_id="manual-456")

    async with queues.consume() as consumer:
        inherited_delivery = await consumer.receive()
        inherited = queues.codec.decode(inherited_delivery.payload)
        await inherited_delivery.acknowledge()
        overridden_delivery = await consumer.receive()
        overridden = queues.codec.decode(overridden_delivery.payload)
        await overridden_delivery.acknowledge()

    assert inherited.job_id == inherited_id
    assert inherited.correlation_id == "request-123"
    assert overridden.job_id == overridden_id
    assert overridden.correlation_id == "manual-456"
    await queues.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("queue", [".", "..", "jobs/urgent", "jobs urgent", "任务"])
async def test_runtime_queue_overrides_use_the_same_portable_validation(queue: str) -> None:
    queues = create_queue_manager()

    with pytest.raises(QueueError, match="队列名不合法"):
        await queues.dispatch(Job(1), queue=queue)
    with pytest.raises(QueueConfigurationError, match="队列名不合法"):
        queues.queue_name(queue=queue)
    with pytest.raises(QueueConfigurationError, match="消费参数不合法"):
        async with queues.consume(queue=queue):
            pass

    await queues.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrency", [True, 1.0])
async def test_runtime_consumer_rejects_non_integer_concurrency(concurrency: object) -> None:
    queues = create_queue_manager()

    with pytest.raises(QueueConfigurationError, match="消费参数不合法"):
        async with queues.consume(concurrency=cast(int, concurrency)):
            pass

    await queues.aclose()


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


@pytest.mark.asyncio
async def test_manager_wraps_backend_creation_failure() -> None:
    async def fail_creation(_settings: QueueConnection) -> FakeQueueBackend:
        raise OSError("connection refused")

    settings = QueueSettings(_env_file=None, default="main", connections={"main": {"driver": "redis", "host": "localhost"}})
    queues = QueueManager(
        settings,
        DatabaseManager(DatabaseSettings(_env_file=None)),
        failed_jobs=RecordingFailedJobStore(),
        factory=fail_creation,
    )

    with pytest.raises(QueueError, match="队列连接 'main' 创建失败") as captured:
        await queues.dispatch(Job(1))

    assert isinstance(captured.value.__cause__, OSError)
    await queues.aclose()


@pytest.mark.asyncio
async def test_manager_wraps_consumer_creation_failure() -> None:
    class FailingConsumerBackend(FakeQueueBackend):
        async def consumer(self, queue: str, concurrency: int) -> FakeQueueConsumer:
            del queue, concurrency
            raise OSError("connection refused")

    settings = QueueSettings(_env_file=None, default="main", connections={"main": {"driver": "redis", "host": "localhost"}})
    backend = FailingConsumerBackend()
    queues = QueueManager(
        settings,
        DatabaseManager(DatabaseSettings(_env_file=None)),
        failed_jobs=RecordingFailedJobStore(),
        factory=queue_backend_factory(backend),
    )

    with pytest.raises(QueueError, match="队列连接 'main' 创建消费者失败") as captured:
        async with queues.consume():
            pass

    assert isinstance(captured.value.__cause__, OSError)
    await queues.aclose()


@pytest.mark.asyncio
async def test_manager_does_not_wrap_backend_creation_cancellation() -> None:
    async def cancel_creation(_settings: QueueConnection) -> FakeQueueBackend:
        raise asyncio.CancelledError()

    settings = QueueSettings(_env_file=None, default="main", connections={"main": {"driver": "redis", "host": "localhost"}})
    queues = QueueManager(
        settings,
        DatabaseManager(DatabaseSettings(_env_file=None)),
        failed_jobs=RecordingFailedJobStore(),
        factory=cancel_creation,
    )

    with pytest.raises(asyncio.CancelledError):
        await queues.get()

    await queues.aclose()


@pytest.mark.parametrize(
    "raw",
    [
        {"driver": "memory"},
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
