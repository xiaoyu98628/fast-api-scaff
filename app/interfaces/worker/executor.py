"""执行单条队列消息并协调重试、失败存储和最终确认。"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from time import perf_counter
from uuid import NAMESPACE_URL, UUID, uuid5

from app.infrastructure.logging.context import JobLogContext, bind_job_log_context
from app.infrastructure.logging.record import ExceptionStackFrame, safe_exception_details
from app.infrastructure.queue.codecs.envelope_json import EnvelopeJsonCodec
from app.infrastructure.queue.contracts.consumer import Delivery
from app.infrastructure.queue.contracts.failed_store import FailedJobRecord, FailedJobStore
from app.infrastructure.queue.contracts.message import MessageEnvelope
from app.infrastructure.queue.errors import InvalidMessageError, RetryableJobError
from app.interfaces.worker.context import JobExecutionContext, JobMetadata, WorkerContext
from app.interfaces.worker.resolver import ExecutableJob, JobTypeResolver

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """记录一次投递最终执行次数和稳定失败分类。"""

    attempts: int
    failure_reason: str | None = None
    error_type: str | None = None
    stacktrace: tuple[ExceptionStackFrame, ...] = ()


async def run_attempts(binding: ExecutableJob, payload: bytes, context: JobExecutionContext) -> ExecutionResult:
    """按照 JobPolicy 执行任务，并把异常压缩为稳定失败原因。"""

    policy = binding.policy
    for attempt in range(1, policy.max_attempts + 1):
        timeout = asyncio.timeout(policy.timeout_seconds)
        failure_error: BaseException | None = None
        try:
            async with timeout:
                await binding.execute(payload, context)
            # handler 若吞掉取消，asyncio 可能正常退出但 timeout 已经到期。
            if timeout.expired():
                return ExecutionResult(attempt, "timeout_suppressed")
        except RetryableJobError as error:
            reason = "retry_exhausted"
            failure_error = error
        except TimeoutError as error:
            if not timeout.expired():
                return _failed_result(attempt, "handler_timeout_error", error)
            reason = "execution_timeout"
            failure_error = error
        except InvalidMessageError as error:
            return _failed_result(attempt, "invalid_job_payload", error)
        except Exception as error:
            return _failed_result(attempt, "handler_error", error)
        else:
            return ExecutionResult(attempt)
        if attempt == policy.max_attempts:
            assert failure_error is not None
            return _failed_result(attempt, reason, failure_error)
        await asyncio.sleep(policy.retry_delay(attempt))
    raise RuntimeError("任务重试配置不合法")


def _failed_result(attempts: int, reason: str, error: BaseException) -> ExecutionResult:
    """保留失败分类及安全诊断，不携带异常消息或任务数据。"""

    error_type, stacktrace = safe_exception_details(error)
    return ExecutionResult(attempts, reason, error_type, stacktrace)


@dataclass(frozen=True, slots=True)
class JobExecutor:
    """保证失败现场先可靠保存，再确认后端消息。"""

    connection: str
    queue: str
    resolver: JobTypeResolver
    failures: FailedJobStore
    codec: EnvelopeJsonCodec
    context: WorkerContext
    clock: Callable[[], datetime] = datetime.now

    async def execute(self, delivery: Delivery) -> None:
        """处理一条 delivery；未抛异常时该消息已经被确认。"""

        started_at = perf_counter()
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
        if message is None:
            if await self.failures.find(failure_id) is not None:
                await delivery.acknowledge()
                return
            result = ExecutionResult(0, "invalid_envelope")
            await self._finish(delivery, message, result, failure_id=failure_id, started_at=started_at)
            return

        context = JobExecutionContext(
            settings=self.context.settings,
            container=self.context.container,
            job=JobMetadata(
                id=message.job_id,
                reference=message.job_type,
                version=message.job_version,
                enqueued_at=message.enqueued_at,
                queue_connection=self.connection,
                queue_name=self.queue,
                correlation_id=message.correlation_id,
                replay_of=message.replay_of,
            ),
        )
        log_context = JobLogContext(
            job_id=str(context.job.id),
            job_type=context.job.reference,
            job_version=context.job.version,
            queue_connection=context.job.queue_connection,
            queue_name=context.job.queue_name,
            correlation_id=context.job.correlation_id,
            replay_of=str(context.job.replay_of) if context.job.replay_of is not None else None,
        )
        with bind_job_log_context(log_context):
            if await self.failures.find(failure_id) is not None:
                await delivery.acknowledge()
                return
            try:
                binding = self.resolver.resolve(message.job_type, message.job_version)
            except KeyError:
                result = ExecutionResult(0, "unknown_job")
            else:
                result = await run_attempts(binding, message.payload, context)
            await self._finish(delivery, message, result, failure_id=failure_id, started_at=started_at)

    async def _finish(
        self,
        delivery: Delivery,
        message: MessageEnvelope | None,
        result: ExecutionResult,
        *,
        failure_id: UUID,
        started_at: float,
    ) -> None:
        """保存最终失败、确认消息，并输出稳定的完成事件。"""

        if result.failure_reason is not None:
            # 保存成功后才能 ACK，否则失败记录和原消息可能同时丢失。
            await self.failures.save(
                FailedJobRecord(
                    failure_id=failure_id,
                    payload=delivery.payload,
                    connection=self.connection,
                    queue=self.queue,
                    failed_at=self.clock(),
                    attempts=result.attempts,
                    reason=result.failure_reason,
                    job_id=message.job_id if message else None,
                    error_type=result.error_type,
                    stacktrace=result.stacktrace,
                )
            )
            # 失败现场已经可靠保存；即使随后 ACK 失败，也必须留下本次执行诊断。
            _log_execution_result(
                message,
                result,
                connection=self.connection,
                queue=self.queue,
                started_at=started_at,
            )
        # 成功任务不落失败表，但同样遵循“处理完成后确认”的至少一次语义。
        await delivery.acknowledge()
        if result.failure_reason is None:
            _log_execution_result(
                message,
                result,
                connection=self.connection,
                queue=self.queue,
                started_at=started_at,
            )


def _log_execution_result(
    message: MessageEnvelope | None,
    result: ExecutionResult,
    *,
    connection: str,
    queue: str,
    started_at: float,
) -> None:
    """按最终执行结果写入成功或不含敏感值的失败日志。"""

    details: dict[str, object] = {
        "job_id": str(message.job_id) if message else None,
        "queue_name": queue,
        "queue_connection": connection,
        "attempts": result.attempts,
        "failure_reason": result.failure_reason,
        "correlation_id": message.correlation_id if message else None,
        "duration_ms": round((perf_counter() - started_at) * 1000, 3),
    }
    if result.error_type is not None:
        details["error_type"] = result.error_type
        details["stacktrace"] = result.stacktrace

    _logger.log(
        logging.ERROR if result.failure_reason is not None else logging.INFO,
        "queue.job.finished",
        extra={"event": "queue.job.finished", "details": details},
    )
