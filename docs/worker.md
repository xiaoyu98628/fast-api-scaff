# 独立 Worker

Worker 与 HTTP 是独立进程，共享 Settings、ApplicationRuntime 和应用服务。HTTP lifespan 不启动消费者，Worker 不启动 FastAPI/Uvicorn。

## 启动

```bash
uv run python -m app.interfaces.worker --help
uv run python -m app.interfaces.worker --connection main --queue reports --concurrency 4
```

省略 connection/queue 时采用默认连接和该连接的默认队列。省略 concurrency 时采用 WORKER_CONCURRENCY。

脚手架没有虚构业务任务。首次使用需在上下文/全局组合根向 `container.queues.catalog` 注册 JobDefinition，在 `app/interfaces/worker/composition.py` 显式绑定 Handler；空注册表会在连接队列前报错退出。完整同进程示例见[队列](queue.md)。

```python
from app.infrastructure.queue.policies import JobPolicy
from app.interfaces.worker.registry import HandlerRegistry

# definition 由组合根提供，service 是已注入依赖的应用服务。
def bind_report_job(definition, service) -> HandlerRegistry:
    registry = HandlerRegistry()

    async def handle(job):
        await service.generate(job.report_id)

    registry.register(
        definition, handle,
        policy=JobPolicy(max_attempts=3, backoff_seconds=(1, 5), timeout_seconds=30),
    )
    return registry
```

Handler 位于 Worker 入站适配器，转换数据并调用应用服务。Application/Domain 不导入 Worker、队列驱动或全局容器；应用层需要投递时定义业务窄协议，由上下文 Infrastructure 实现。不要在 Handler 中绕过应用用例直接操作 ORM。

## 重试与超时

JobPolicy 的 max_attempts 包含首次执行；backoff_seconds 依次使用，超过长度后复用最后一个值，空元组表示立即重试。策略在注册时验证。

仅 `RetryableJobError` 和框架执行超时进行重试。Worker Handler 可把明确的暂时性业务错误转换为 `app.infrastructure.queue.errors.RetryableJobError`；业务层不直接依赖该基础设施异常。业务自己抛出的 TimeoutError 单独分类并最终失败。

重试属于本次投递，在同一执行槽内等待；不是持久延迟调度。崩溃后尝试次数可能重新开始，没有跨崩溃的全局次数上限。失败分类包含 unknown_job、invalid_envelope、invalid_job_payload、handler_error、handler_timeout_error、execution_timeout、retry_exhausted、timeout_suppressed。

asyncio 超时只能协作式取消。Handler 应及时让出事件循环，不吞 CancelledError，不执行长时间阻塞调用；它无法强制终止阻塞线程或外部副作用。超时后重试仍可能重复业务效果，必要时由业务实现幂等。

Kafka 的 max_poll_interval_ms 必须大于最大任务执行与全部退避时间，并为失败存储和确认预留余量。Redis 定期续租并在失去租约后取消执行；进程长时间停顿仍可能造成重复执行。RabbitMQ 服务端的消费确认超时应覆盖任务与重试总时间。

## 生命周期与故障

SIGINT/SIGTERM 设置停止信号：停止安排新任务，取消等待消息的执行槽，等待在途任务。超过 WORKER_SHUTDOWN_TIMEOUT_SECONDS 后请求取消在途任务，然后关闭消费者和容器。该上限是发出取消的等待时间，不保证强制终止不响应取消的业务代码。

消费、ACK、失败存储或租约错误会停止整个 Worker，其他在途任务被取消，未确认任务交给后端恢复；首版没有自动无限重连循环。Kafka 再均衡导致在途任务取消时也按故障退出，避免旧消费者继续提交。无在途任务的正常再均衡可以继续消费。

队列连接最后装配，先于数据库/缓存/HTTP 出站资源关闭。关闭失败仍尝试剩余资源并聚合异常。

任务完成日志使用事件 `queue.job.finished`，details 中包含 job_id、queue_name、queue_connection、attempts、failure_reason 和 correlation_id，不输出任务数据。

## 质量检查

```bash
uv run python -m pytest -q tests/queue tests/worker
uv run python -m pytest -q
uv run ruff check app tests database
uv run ruff format --check app tests database
uv run ty check app tests database
git diff --check
```
