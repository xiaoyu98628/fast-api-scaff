import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.infrastructure.queue.catalog import JobCatalog
from app.infrastructure.queue.codecs.envelope_json import EnvelopeJsonCodec
from app.infrastructure.queue.contracts.message import MessageEnvelope
from app.infrastructure.queue.contracts.publisher import QueuePublisher
from app.infrastructure.queue.errors import QueueError


@dataclass(frozen=True, slots=True)
class Dispatcher:
    publisher: QueuePublisher
    catalog: JobCatalog
    codec: EnvelopeJsonCodec
    default_queue: str
    publish_timeout: float = 10.0
    clock: Callable[[], datetime] = datetime.now
    new_id: Callable[[], UUID] = uuid4

    async def dispatch(self, job: object, *, queue: str | None = None, correlation_id: str | None = None) -> UUID:
        encoded = self.catalog.encode(job)
        message = MessageEnvelope(self.new_id(), encoded.name, encoded.version, encoded.payload, self.clock(), correlation_id)
        await self.publish_envelope(message, queue=queue)
        return message.job_id

    async def publish_envelope(self, message: MessageEnvelope, *, queue: str | None = None) -> None:
        target = self.default_queue if queue is None else queue
        if not target.strip() or len(target) > 200:
            raise QueueError("队列名不能为空")
        payload = self.codec.encode(message)
        try:
            async with asyncio.timeout(self.publish_timeout):
                await self.publisher.publish(target, payload)
        except Exception as error:
            raise QueueError("消息发布未获确认，结果可能不确定；请勿盲目重复投递") from error
