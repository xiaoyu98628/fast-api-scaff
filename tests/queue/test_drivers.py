import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractIncomingMessage
from aiokafka import TopicPartition
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.config.queue import KafkaQueueSettings, RedisQueueSettings
from app.infrastructure.queue.drivers.kafka import KafkaBackend, KafkaConsumer, RebalanceListener
from app.infrastructure.queue.drivers.rabbitmq import RabbitBackend, RabbitDelivery
from app.infrastructure.queue.drivers.redis import RedisBackend, RedisConsumer, RedisDelivery
from app.infrastructure.queue.errors import DeliveryLostError


@pytest.mark.asyncio
async def test_rabbit_publish_declares_durable_queue_and_waits_for_confirmation() -> None:
    channel = Mock()
    channel.declare_queue = AsyncMock()
    channel.default_exchange.publish = AsyncMock()
    backend = RabbitBackend(cast(AbstractConnection, Mock()), cast(AbstractChannel, channel))
    await backend.publish("jobs", b"one")
    await backend.publish("jobs", b"two")
    channel.declare_queue.assert_awaited_once_with("jobs", durable=True)
    arguments = channel.default_exchange.publish.call_args
    assert arguments.kwargs == {"routing_key": "jobs", "mandatory": True}
    assert arguments.args[0].body == b"two"
    assert arguments.args[0].delivery_mode == 2
    channel.default_exchange.publish.side_effect = OSError("unroutable")
    with pytest.raises(OSError):
        await backend.publish("jobs", b"three")


@pytest.mark.asyncio
async def test_rabbit_delivery_does_not_ack_before_execution() -> None:
    message = Mock(body=b"one", message_id="id", delivery_tag=1)
    message.ack = AsyncMock()
    delivery = RabbitDelivery(cast(AbstractIncomingMessage, message))
    assert delivery.payload == b"one"
    message.ack.assert_not_awaited()
    await delivery.acknowledge()
    message.ack.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_pending_recovery_and_owner_checked_ack() -> None:
    client = Mock()
    client.xgroup_create = AsyncMock(side_effect=ResponseError("BUSYGROUP exists"))
    client.xautoclaim = AsyncMock(return_value=[b"0-0", [(b"1-0", {b"payload": b"old"})], []])
    client.xreadgroup = AsyncMock()
    client.eval = AsyncMock(return_value=1)
    settings = RedisQueueSettings(driver="redis", url="redis://localhost")
    consumer = RedisConsumer(cast(Redis, client), "jobs", settings)
    await consumer.start()
    delivery = await consumer.receive()
    assert delivery.payload == b"old"
    client.xreadgroup.assert_not_awaited()
    await delivery.acknowledge()
    assert client.eval.call_args.args[2:] == ("jobs", "workers", consumer.name, "1-0")
    with pytest.raises(DeliveryLostError):
        await delivery.acknowledge()
    await consumer.aclose()


@pytest.mark.asyncio
async def test_redis_owner_loss_does_not_ack() -> None:
    client = Mock(eval=AsyncMock(return_value=0))
    consumer = RedisConsumer(cast(Redis, client), "jobs", RedisQueueSettings(driver="redis", url="redis://localhost"))
    delivery = RedisDelivery(consumer, "1-0", b"message")
    consumer.pending[delivery.identity] = delivery
    with pytest.raises(DeliveryLostError):
        await delivery.acknowledge()
    assert not delivery.settled
    assert consumer.pending
    await consumer.aclose()


@pytest.mark.asyncio
async def test_redis_new_message_uses_manual_group_read() -> None:
    client = Mock()
    client.xautoclaim = AsyncMock(return_value=[b"0-0", [], []])
    client.xreadgroup = AsyncMock(return_value=[(b"jobs", [(b"2-0", {b"payload": b"new"})])])
    consumer = RedisConsumer(cast(Redis, client), "jobs", RedisQueueSettings(driver="redis", url="redis://localhost"))
    delivery = await consumer.receive()
    assert delivery.payload == b"new"
    assert client.xreadgroup.call_args.args == ("workers", consumer.name, {"jobs": ">"})
    await consumer.aclose()


def test_redis_uses_separate_connect_and_command_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    from_url = Mock(return_value=Mock())
    monkeypatch.setattr("app.infrastructure.queue.drivers.redis.Redis.from_url", from_url)

    RedisBackend(RedisQueueSettings(driver="redis", url="redis://localhost", publish_timeout=0.5, command_timeout=3))

    assert from_url.call_args.kwargs["socket_connect_timeout"] == 0.5
    assert from_url.call_args.kwargs["socket_timeout"] == 3


@pytest.mark.asyncio
async def test_kafka_producer_is_lazy_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    producer = Mock(start=AsyncMock(), stop=AsyncMock(), send_and_wait=AsyncMock())
    constructor = Mock(return_value=producer)
    monkeypatch.setattr("app.infrastructure.queue.drivers.kafka.AIOKafkaProducer", constructor)
    backend = await KafkaBackend.create(KafkaQueueSettings(driver="kafka", bootstrap_servers=["localhost:9092"]))

    constructor.assert_not_called()
    await backend.publish("jobs", b"one")
    await backend.publish("jobs", b"two")

    constructor.assert_called_once()
    producer.start.assert_awaited_once()
    assert producer.send_and_wait.await_args_list[0].args == ("jobs", b"one")
    assert producer.send_and_wait.await_args_list[1].args == ("jobs", b"two")
    await backend.aclose()
    producer.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_kafka_pauses_partition_until_explicit_offset_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.getone = AsyncMock(return_value=SimpleNamespace(topic="jobs", partition=1, offset=7, value=b"task"))
    client.commit = AsyncMock()
    client.stop = AsyncMock()
    constructor = Mock(return_value=client)
    monkeypatch.setattr("app.infrastructure.queue.drivers.kafka.AIOKafkaConsumer", constructor)
    consumer = KafkaConsumer(KafkaQueueSettings(driver="kafka", bootstrap_servers=["localhost:9092"]), "jobs")
    assert constructor.call_args.kwargs["enable_auto_commit"] is False
    delivery = await consumer.receive()
    partition = TopicPartition("jobs", 1)
    client.pause.assert_called_once_with(partition)
    client.commit.assert_not_awaited()
    await delivery.acknowledge()
    client.commit.assert_awaited_once_with({partition: 8})
    client.resume.assert_called_once_with(partition)
    await consumer.aclose()


@pytest.mark.asyncio
async def test_kafka_rebalance_cancels_owner_and_fences_old_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.getone = AsyncMock(return_value=SimpleNamespace(topic="jobs", partition=0, offset=2, value=b"task"))
    client.commit = AsyncMock()
    client.stop = AsyncMock()
    monkeypatch.setattr("app.infrastructure.queue.drivers.kafka.AIOKafkaConsumer", Mock(return_value=client))
    consumer = KafkaConsumer(KafkaQueueSettings(driver="kafka", bootstrap_servers=["localhost:9092"]), "jobs")
    ready = asyncio.Event()
    deliveries = []

    async def owner() -> None:
        deliveries.append(await consumer.receive())
        ready.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(owner())
    await ready.wait()
    await RebalanceListener(consumer).on_partitions_revoked([TopicPartition("jobs", 0)])
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(DeliveryLostError):
        await deliveries[0].acknowledge()
    client.commit.assert_not_awaited()
    await consumer.aclose()


@pytest.mark.asyncio
async def test_kafka_failed_commit_keeps_partition_paused(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock(
        getone=AsyncMock(return_value=SimpleNamespace(topic="jobs", partition=0, offset=2, value=b"task")),
        commit=AsyncMock(side_effect=OSError("coordinator unavailable")),
        stop=AsyncMock(),
    )
    monkeypatch.setattr("app.infrastructure.queue.drivers.kafka.AIOKafkaConsumer", Mock(return_value=client))
    consumer = KafkaConsumer(KafkaQueueSettings(driver="kafka", bootstrap_servers=["localhost:9092"]), "jobs")
    delivery = await consumer.receive()
    with pytest.raises(OSError):
        await delivery.acknowledge()
    client.resume.assert_not_called()
    assert not delivery.settled
    await consumer.aclose()
