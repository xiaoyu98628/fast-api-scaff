# 独立 Worker

Worker 与 HTTP 是独立进程，共享 Settings、组合根和资源生命周期。HTTP lifespan 不启动消费者，Worker 不启动 FastAPI/Uvicorn。

## 启动

```bash
uv run python -m app.worker --help
uv run python -m app.worker
# 可选：为隔离的业务队列单独启动 Worker
uv run python -m app.worker --connection redis --queue reports --concurrency 4
# 只启动 Compose 中的 Worker 服务
docker compose up --build worker
```

省略 connection/queue 时采用默认连接和该连接的默认队列。省略 concurrency 时采用 QUEUE_WORKER__CONCURRENCY。

只要默认队列连接配置有效且后端可访问，即使队列当前没有消息、项目也没有预先注册的 Job，Worker 仍可启动并等待。Job 在消息到达后根据类路径动态解析，不存在启动前注册清单。

`docker compose up --build` 默认同时启动 `service` 和 `worker`；只需要 HTTP 时使用 `docker compose up --build service`。Compose 中的 `worker` 服务复用应用镜像、`.env` 和网络，不暴露端口，也不配置只适用于 HTTP 的健康检查。镜像本身不声明健康检查，Compose 只为 HTTP 服务检测 `/health`。Worker 不会自动创建队列服务；`.env` 必须配置容器可访问的 Redis、Kafka 或 RabbitMQ 地址。容器内的 `127.0.0.1` 是 Worker 容器自身。

脚手架内置 `LoginSucceededJob` 最小任务。登录接口向默认连接配置的默认队列（`sample.env` 为 `default`）尽力投递 `user_id` 参数和固定文案，并把当前 HTTP request ID 作为 correlation ID；Worker 调用它的 `handle(context)` 输出“用户登录成功，队列任务已执行。”并记录结构化用户 ID。任务不含用户名、密码或 Token。`user_id` 暂时可空，以兼容队列中已经存在的旧消息。`sample.env` 以 Redis 为默认连接，因此 Worker 可以不带参数启动。

新增任务时，继承 `QueueJob[JobExecutionContext]`、声明可序列化字段并实现异步 `handle(context)`。投递端自动把实际类路径写入消息；Worker 收到后动态导入、验证、解码并执行，不扫描业务目录，也不需要修改上下文 composition 或应用组合根。完整示例见[队列](queue.md)。

一个默认 Worker 可以执行默认队列中的所有合法 QueueJob，但不会动态扫描 Redis Stream、Kafka Topic 或 RabbitMQ Queue。命名队列是用于优先级、并发和扩缩容隔离的可选高级能力，需要时为它单独启动 Worker。

`jobs/` 是当前示例的组织习惯，不是 Worker 约定。Job 可放在应用根包的任意业务模块，Worker 只依据消息携带的类路径解析。类移动后应暂时保留旧模块兼容入口，以便处理已经入队的消息。Application/Domain 不导入 Worker、队列驱动或全局容器。

Worker 在容器启动成功后创建不可变 `WorkerContext`，其中保存当前 `Settings` 和同一个 `ApplicationContainer`。执行器从它为每条消息创建独立的 `JobExecutionContext`：常用的 `settings` 和 `container` 保持直接访问，任务 ID、类型和版本、入队时间、连接、队列、correlation ID 与重放来源集中在 `context.job`，再把整个执行上下文传给 `handle(context)`；同一投递内重试复用同一个对象。因此 Job 可以选择 `container.users` 等上下文公开服务，也可以在宿主级维护场景中使用 `container.databases`、`caches`、`http`、`queues` 和 `vectors`。多个并发槽共享 Manager 和底层连接池，但不得共享任务级 `AsyncSession`、事务或其他可变状态。

Job 应保持入站适配器职责：把消息数据转换成应用 Command 并调用公开应用服务。Application/Domain 不导入 `JobExecutionContext`、`WorkerContext`、全局容器或具体 Manager；需要把缓存、HTTP 上游或向量查询纳入业务用例时，应在当前上下文 Application 层定义窄协议，由 Infrastructure 实现并通过 composition 注入。只有不属于业务用例的宿主级维护任务才直接操作 Manager，而且仍应使用公共入口而不是具体驱动。

## 重试与超时

JobPolicy 的 max_attempts 包含首次执行；backoff_seconds 依次使用，超过长度后复用最后一个值，空元组表示立即重试。策略在首次投递或解析 Job 类型时验证。

仅 `RetryableJobError` 和框架执行超时进行重试。QueueJob 可把明确的暂时性适配错误转换为 `app.infrastructure.queue.errors.RetryableJobError`；业务层不直接依赖该基础设施异常。业务自己抛出的 TimeoutError 单独分类并最终失败。

重试属于本次投递，在同一执行槽内等待；不是持久延迟调度。崩溃后尝试次数可能重新开始，没有跨崩溃的全局次数上限。失败分类包含 unknown_job、invalid_envelope、invalid_job_payload、handler_error、handler_timeout_error、execution_timeout、retry_exhausted、timeout_suppressed。

asyncio 超时只能协作式取消。`handle(context)` 应及时让出事件循环，不吞 CancelledError，不执行长时间阻塞调用；它无法强制终止阻塞线程或外部副作用。超时后重试仍可能重复业务效果，必要时由业务实现幂等。

Kafka 的 max_poll_interval_ms 必须大于最大任务执行与全部退避时间，并为失败存储和确认预留余量。Redis 定期续租并在失去租约后取消执行；进程长时间停顿仍可能造成重复执行。RabbitMQ 服务端的消费确认超时应覆盖任务与重试总时间。

## 生命周期与故障

SIGINT/SIGTERM 设置停止信号：停止安排新任务，取消等待消息的执行槽，等待在途任务。超过 QUEUE_WORKER__SHUTDOWN_TIMEOUT_SECONDS 后请求取消在途任务，然后关闭消费者和容器。该上限是发出取消的等待时间，不保证强制终止不响应取消的业务代码。

消费、ACK、失败存储或租约错误会停止整个 Worker，其他在途任务被取消，未确认任务交给后端恢复；首版没有自动无限重连循环。Kafka 再均衡导致在途任务取消时也按故障退出，避免旧消费者继续提交。无在途任务的正常再均衡可以继续消费。

队列连接最后装配，先于数据库/缓存/HTTP 出站资源关闭。关闭失败仍尝试剩余资源并聚合异常。

Worker 生命周期使用 `worker.starting`、`worker.started`、`worker.start_failed`、`worker.stopping`、`worker.stopped` 和 `worker.stop_failed`。执行器的完成日志使用事件 `queue.job.finished`，details 中包含 job_id、queue_name、queue_connection、attempts、failure_reason、correlation_id 和 duration_ms；捕获到异常的失败任务使用 ERROR 级别，并额外记录异常类型及仅含模块、函数和行号的调用栈位置。Worker 进程级故障使用 `worker.failed` 事件记录相同的安全诊断。

任务执行期间，日志过滤器会给 Job、Application 和 Infrastructure 产生的日志自动附加 `job_id`、`job_type`、`job_version`、`queue_connection`、`queue_name`，以及存在时的 `correlation_id` 和 `replay_of`。这些字段通过异步上下文绑定，任务结束后恢复，不会跨并发槽泄漏。任务日志和失败诊断都不记录异常消息、运行时局部变量或任务数据。

## 质量检查

```bash
uv run python -m pytest -q tests/queue tests/worker
uv run python -m pytest -q
uv run ruff check app tests database
uv run ruff format --check app tests database
uv run ty check app tests database
git diff --check
```
