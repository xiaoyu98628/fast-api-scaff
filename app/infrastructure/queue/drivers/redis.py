"""使用 Redis Streams、Consumer Group 和租约实现任务队列。"""

import asyncio
from contextlib import suppress
from typing import cast
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.config.queue import RedisQueueSettings
from app.infrastructure.queue.errors import DeliveryLostError, QueueError

_READ_BLOCK_MS = 1000

# 比较 PEL 所有者与确认/续租在同一 Redis 脚本内完成，防止旧消费者确认已被接管的消息。
_OWNED_ACK = """
local p = redis.call('XPENDING', KEYS[1], ARGV[1], ARGV[3], ARGV[3], 1)
if #p == 0 or p[1][2] ~= ARGV[2] then return 0 end
local acknowledged = redis.call('XACK', KEYS[1], ARGV[1], ARGV[3])
if acknowledged == 1 then redis.call('XDEL', KEYS[1], ARGV[3]) end
return acknowledged
"""
_OWNED_RENEW = """
local p = redis.call('XPENDING', KEYS[1], ARGV[1], ARGV[3], ARGV[3], 1)
if #p == 0 or p[1][2] ~= ARGV[2] then return 0 end
redis.call('XCLAIM', KEYS[1], ARGV[1], ARGV[2], 0, ARGV[3], 'JUSTID')
return 1
"""


class RedisDelivery:
    """持有一条属于当前 Redis Consumer 的未确认 Stream 消息。"""

    def __init__(self, consumer: RedisConsumer, identity: str, payload: bytes) -> None:
        self._consumer = consumer
        self.identity = identity
        self.payload = payload
        self.owner = asyncio.current_task()
        self.settled = False

    async def acknowledge(self) -> None:
        """仅由当前所有者原子执行 XACK 和 XDEL。"""

        source = self._consumer
        if self.settled or source.closed:
            raise DeliveryLostError("Redis delivery 已失效")
        async with source.lock:
            result = await source.client.eval(_OWNED_ACK, 1, source.stream, source.group, source.name, self.identity)
            if result != 1:
                raise DeliveryLostError("Redis 消息所有权已丢失")
            self.settled = True
            source.pending.pop(self.identity, None)


class RedisConsumer:
    """优先接管过期 pending 消息，并为在途任务持续续租。"""

    def __init__(self, client: Redis, stream: str, settings: RedisQueueSettings) -> None:
        self.client = client
        self.stream = stream
        self.group = settings.group
        self.name = str(uuid4())
        self.lease = settings.lease_seconds
        self.pending: dict[str, RedisDelivery] = {}
        self.lock = asyncio.Lock()
        self._receive_lock = asyncio.Lock()
        self._cursor: str | bytes = "0-0"
        self.closed = False
        self._renewal: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """确保消费组存在，并启动在途任务续租循环。"""

        try:
            await self.client.xgroup_create(self.stream, self.group, id="0-0", mkstream=True)
        except ResponseError as error:
            if not str(error).startswith("BUSYGROUP"):
                raise
        self._renewal = asyncio.create_task(self._renew())

    async def receive(self) -> RedisDelivery:
        """先恢复租约过期消息，没有时再阻塞读取新消息。"""

        async with self._receive_lock:
            while not self.closed:
                if self._renewal is not None and self._renewal.done():
                    # 续租故障必须终止消费，不能继续执行可能已被接管的消息。
                    await self._renewal
                claimed = await self.client.xautoclaim(self.stream, self.group, self.name, int(self.lease * 1000), self._cursor, count=1)
                self._cursor = claimed[0]
                entries = cast(list[tuple[bytes, dict[bytes, bytes]]], claimed[1])
                if not entries:
                    result = await self.client.xreadgroup(self.group, self.name, {self.stream: ">"}, count=1, block=_READ_BLOCK_MS)
                    entries = cast(list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]], result)[0][1] if result else []
                if entries:
                    identity, fields = entries[0]
                    key = identity.decode() if isinstance(identity, bytes) else identity
                    if key in self.pending:
                        raise DeliveryLostError("Redis 在途消息租约已过期，停止重复执行")
                    delivery = RedisDelivery(self, key, fields.get(b"payload", b""))
                    self.pending[key] = delivery
                    return delivery
        raise QueueError("Redis 消费者已关闭")

    async def _renew(self) -> None:
        """以租约三分之一为周期刷新当前消费者持有的消息。"""

        try:
            while True:
                await asyncio.sleep(self.lease / 3)
                async with asyncio.timeout(self.lease / 3), self.lock:
                    for delivery in tuple(self.pending.values()):
                        result = await self.client.eval(_OWNED_RENEW, 1, self.stream, self.group, self.name, delivery.identity)
                        if result != 1:
                            raise DeliveryLostError("Redis 续租失败或所有权丢失")
        except Exception:
            # 所有权不再可信时取消对应执行任务，让 Worker 按故障路径退出。
            for delivery in self.pending.values():
                if delivery.owner is not None:
                    delivery.owner.cancel()
            raise

    async def aclose(self) -> None:
        self.closed = True
        if self._renewal is not None:
            self._renewal.cancel()
            with suppress(asyncio.CancelledError):
                await self._renewal


class RedisBackend:
    """把逻辑队列映射为带前缀的 Redis Stream。"""

    def __init__(self, settings: RedisQueueSettings) -> None:
        self._settings = settings
        self._client = Redis(
            host=settings.host,
            port=settings.port,
            db=settings.database,
            username=settings.username,
            password=settings.password.get_secret_value() if settings.password is not None else None,
            ssl=settings.ssl,
            max_connections=settings.max_connections,
            decode_responses=False,
            protocol=2,
            socket_connect_timeout=settings.connect_timeout,
            socket_timeout=settings.command_timeout,
        )

    async def publish(self, queue: str, payload: bytes) -> None:
        await self._client.xadd(self._settings.prefix + queue, {"payload": payload})

    async def consumer(self, queue: str, concurrency: int) -> RedisConsumer:
        consumer = RedisConsumer(self._client, self._settings.prefix + queue, self._settings)
        await consumer.start()
        return consumer

    async def aclose(self) -> None:
        await self._client.aclose()
