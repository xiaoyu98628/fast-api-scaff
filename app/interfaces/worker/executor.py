"""执行单条队列消息并协调重试、失败存储和最终确认。"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from app.infrastructure.queue.codecs.envelope_json import EnvelopeJsonCodec
from app.infrastructure.queue.contracts.consumer import Delivery
from app.infrastructure.queue.contracts.failed_store import FailedJobRecord, FailedJobStore
from app.infrastructure.queue.errors import InvalidMessageError, RetryableJobError
from app.interfaces.worker.resolver import ExecutableJob, JobTypeResolver

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """记录一次投递最终执行次数和稳定失败分类。"""

    attempts: int
    failure_reason: str | None = None


async def run_attempts(binding: ExecutableJob, payload: bytes) -> ExecutionResult:
    """按照 JobPolicy 执行任务，并把异常压缩为稳定失败原因。"""

    policy = binding.policy
    for attempt in range(1, policy.max_attempts + 1):
        timeout = asyncio.timeout(policy.timeout_seconds)
        try:
            async with timeout:
                await binding.execute(payload)
            # handler 若吞掉取消，asyncio 可能正常退出但 timeout 已经到期。
            if timeout.expired():
                return ExecutionResult(attempt, "timeout_suppressed")
        except RetryableJobError:
            reason = "retry_exhausted"
        except TimeoutError:
            if not timeout.expired():
                return ExecutionResult(attempt, "handler_timeout_error")
            reason = "execution_timeout"
        except InvalidMessageError:
            return ExecutionResult(attempt, "invalid_job_payload")
        except Exception:
            return ExecutionResult(attempt, "handler_error")
        else:
            return ExecutionResult(attempt)
        if attempt == policy.max_attempts:
            return ExecutionResult(attempt, reason)
        await asyncio.sleep(policy.retry_delay(attempt))
    raise RuntimeError("任务重试配置不合法")


@dataclass(frozen=True, slots=True)
class JobExecutor:
    """保证失败现场先可靠保存，再确认后端消息。"""

    connection: str
    queue: str
    resolver: JobTypeResolver
    failures: FailedJobStore
    codec: EnvelopeJsonCodec
    clock: Callable[[], datetime] = datetime.now

    async def execute(self, delivery: Delivery) -> None:
        """处理一条 delivery；未抛异常时该消息已经被确认。"""

        message = None
        try:
            message = self.codec.decode(delivery.payload)
        except InvalidMessageError:
            identity = "raw:" + sha256(delivery.payload).hexdigest()
        else:
            identity = str(message.job_id)
        # 确定性 ID 让 ACK 失败后的重复投递只补做确认，不再次执行已记录的失败任务。
        # 连接与队列也参与身份，避免跨队列投递同一个 job_id 相互抑制。
        failure_id = uuid5(NAMESPACE_URL, repr(("queue-failure", self.connection, self.queue, identity)))
        if await self.failures.find(failure_id) is not None:
            await delivery.acknowledge()
            return
        if message is None:
            result = ExecutionResult(0, "invalid_envelope")
        else:
            try:
                binding = self.resolver.resolve(message.job_type, message.job_version)
            except KeyError:
                result = ExecutionResult(0, "unknown_job")
            else:
                result = await run_attempts(binding, message.payload)
        if result.failure_reason is not None:
            # 保存成功后才能 ACK，否则失败记录和原消息可能同时丢失。
            await self.failures.save(
                FailedJobRecord(
                    failure_id,
                    delivery.payload,
                    self.connection,
                    self.queue,
                    self.clock(),
                    result.attempts,
                    result.failure_reason,
                    message.job_id if message else None,
                )
            )
        # 成功任务不落失败表，但同样遵循“处理完成后确认”的至少一次语义。
        await delivery.acknowledge()
        _logger.info(
            "queue.job.finished",
            extra={
                "event": "queue.job.finished",
                "details": {
                    "job_id": str(message.job_id) if message else None,
                    "queue_name": self.queue,
                    "queue_connection": self.connection,
                    "attempts": result.attempts,
                    "failure_reason": result.failure_reason,
                    "correlation_id": message.correlation_id if message else None,
                },
            },
        )
