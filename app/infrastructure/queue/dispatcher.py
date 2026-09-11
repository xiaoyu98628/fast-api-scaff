"""把 QueueJob 编码成信封并发布到选定逻辑队列。"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.config.queue import validate_queue_name
from app.infrastructure.queue.codecs.envelope_json import EnvelopeJsonCodec
from app.infrastructure.queue.contracts.message import MessageEnvelope
from app.infrastructure.queue.contracts.publisher import QueuePublisher
from app.infrastructure.queue.errors import QueueError
from app.infrastructure.queue.job import encode_job
from app.runtime.trace import current_correlation_id


def _always_active() -> None:
    pass


@dataclass(frozen=True, slots=True)
class Dispatcher:
    """提供与具体 Redis、Kafka 或 RabbitMQ 驱动无关的投递入口。"""

    publisher: QueuePublisher
    codec: EnvelopeJsonCodec
    default_queue: str
    publish_timeout: float = 10.0
    clock: Callable[[], datetime] = datetime.now
    new_id: Callable[[], UUID] = uuid4
    ensure_active: Callable[[], None] = field(default=_always_active, repr=False, compare=False)

    async def dispatch(self, job: object, *, queue: str | None = None, correlation_id: str | None = None) -> UUID:
        """编码并投递 QueueJob；未显式指定时继承当前关联 ID。"""

        encoded = encode_job(job)
        active_correlation_id = current_correlation_id() if correlation_id is None else correlation_id
        message = MessageEnvelope(
            self.new_id(),
            encoded.job_type,
            encoded.version,
            encoded.payload,
            self.clock(),
            active_correlation_id,
        )
        await self.publish_envelope(message, queue=queue)
        return message.job_id

    async def publish_envelope(self, message: MessageEnvelope, *, queue: str | None = None) -> None:
        """发布已经构造的信封，供失败任务重放等内部流程使用。"""

        self.ensure_active()
        try:
            target = validate_queue_name(self.default_queue if queue is None else queue)
        except TypeError, ValueError:
            raise QueueError("队列名不合法")
        payload = self.codec.encode(message)
        try:
            async with asyncio.timeout(self.publish_timeout):
                await self.publisher.publish(target, payload)
        except Exception as error:
            # 超时或断连可能发生在后端已经接受消息之后，不能宣称发布一定失败。
            raise QueueError("消息发布未获确认，结果可能不确定；请勿盲目重复投递") from error
