# 队列

队列基础设施提供 QueueJob、Dispatcher、QueueManager 和三种后端：Redis Streams、Kafka、RabbitMQ。HTTP 和 Console 可以发布任务；消费由[独立 Worker](worker.md)启动。

## 1. 连接与逻辑队列

`QUEUE_CONNECTIONS__<NAME>` 中的 `<NAME>` 是连接名，用来区分后端、集群、认证信息和消费组；`QUEUE_DEFAULT` 选择默认连接。每个连接的 `default_queue` 默认为 `default`。普通 Job 都发布到这个默认逻辑队列，因此业务代码不需要知道 Redis、Kafka、RabbitMQ 或具体队列名。

默认发布只需要：

```python
from app.runtime.container import ApplicationContainer

async def submit(container: ApplicationContainer, job: object):
    return await container.queues.dispatch(job)
```

只有在任务需要独立优先级、并发或扩缩容时，才覆盖连接或队列：

```python
await container.queues.dispatch(job, connection="redis", queue="reports", correlation_id="request-123")
```

`dispatch()` 不启动消费者；构建容器也不连接队列服务。第一次发布时 Kafka 才建立 Producer，RabbitMQ 在第一次获取 Dispatcher 时建立发布连接，Redis 客户端在首次命令时连接。Kafka Worker 只消费时不会初始化 Producer。

队列名映射为 Redis 的 `prefix + queue`、Kafka Topic、RabbitMQ 同名持久队列。RabbitMQ 使用默认 exchange 和同名 routing key；首版不提供自定义 exchange 或绑定。

`sample.env` 同时声明 `redis`、`kafka` 和 `rabbitmq` 三个命名连接，并以 `redis` 为默认连接、`default` 为该连接的默认逻辑队列。`uv run python -m app.worker` 直接消费该队列；`--connection` 和 `--queue` 只是高级覆盖。Worker 不会动态扫描所有物理队列；未显式隔离的 Job 都复用默认队列。

配置见[配置参考](configuration.md#队列与-worker)与 `sample.env`。未配置连接时，HTTP/Console 仍可启动；调用队列公共入口才报告未配置错误。连接字段在容器构建时严格校验。

## 2. QueueJob 与动态解析

一个业务任务由一个 QueueJob 类表达，数据与执行入口放在同一个类中。项目当前把用户任务组织在 `app/contexts/user/jobs/` 并按类名使用蛇形命名模块，但这是代码组织方式，不是队列框架的扫描规则；Job 可以移动到应用根包内的其他模块。包的 `__init__.py` 保持完全空，调用方从实际定义模块显式导入：

```python
from dataclasses import dataclass

from app.infrastructure.queue.job import QueueJob

@dataclass(frozen=True, slots=True)
class ExampleJob(QueueJob):
    number: int

    async def handle(self) -> None:
        print(self.number)
```

投递仍然只有一个入口：

```python
await container.queues.dispatch(ExampleJob(number=42))
```

Dispatcher 自动取得 `类型.__module__:类型.__qualname__`，将类路径、默认版本 1 和 JSON payload 写入消息。Worker 不扫描 `contexts`、`jobs` 或其他业务目录，也没有 Job Catalog 或 Handler 注册表；它按消息中的类路径动态导入类型，确认模块属于应用根包且类型继承 `QueueJob`，解码后直接执行 `await job.handle()`。解析结果会缓存。

普通 dataclass 和 Pydantic Model 默认使用基于 Pydantic schema 的 JSON Codec；需要兼容特殊历史协议时，可以在 Job 类上覆盖 `codec`。重试策略同样通过类级 `policy` 覆盖，版本通过类级 `version` 覆盖。当前 `handle()` 固定为无参数方法，Worker 不注入全局容器、应用服务或其他依赖，因此现有能力适合只依赖自身 payload 的任务。需要访问业务能力时，必须先扩展显式装配边界并注入上下文内定义的窄接口，不能让 Application/Domain 反向依赖 `ApplicationContainer`。

类路径属于队列消息契约。移动或重命名 Job 时，尚未消费的消息仍引用旧路径；应在旧模块暂时保留一个指向新类的显式导入，待旧队列排空后再删除。动态导入以队列服务是内部可信资源为前提，默认拒绝应用根包之外的类路径。

当前内置 `LoginSucceededJob` 作为最小业务示例：登录 HTTP 适配器在会话提交后向默认队列尽力投递 `user_id` 参数和固定文案，Worker 调用其 `handle()` 记录该文案和结构化用户 ID。任务不携带用户名、密码或 Token；发布失败不改变登录响应。`user_id` 暂时可空，以兼容队列中已经存在的旧消息。该通知不具备 Outbox 或 exactly-once 保证，不应用于审计或安全决策。

## 3. 信封与交付保证

信封包含 `schema_version=2`、`job_id`、`job_type`、`job_version`、`payload`、`enqueued_at`、`correlation_id`、`replay_of`。`job_type` 是可导入的 Job 类路径。业务 payload 必须是合法 JSON 字节，在外层 JSON 中采用 Base64 表达；不接受 NaN/Infinity。默认整个信封不超过 1 MiB。时间保持本地无时区，各宿主应使用相同 `TZ`。旧的 schema version 1 消息会按非法信封写入失败记录，不会尝试执行。

发布成功表示后端接受，不表示业务完成。发布超时或连接故障可能发生在接受之后，因此结果可能不确定，不能盲目重投。消息成功处理后再确认，外部后端恢复未确认消息时可能重复执行；业务幂等不由框架自动提供。数据库提交与发布不是原子操作，首版显式在 UoW 提交后投递，没有 after_commit 包装器或 Outbox。

| 后端 | 行为与边界 |
| --- | --- |
| Redis | Streams + Consumer Group，消费时创建组并从 0-0 起读；XAUTOCLAIM 恢复超时 pending；后台续租；Lua 检查所有者后原子 XACK + XDEL；command_timeout 独立于发布超时；失败退出后等待租约过期恢复 |
| Kafka | 禁止自动 offset 提交；每个分区最多一条在途，成功提交 offset+1 后恢复该分区；跨分区并发；再均衡取消当前执行并使旧 delivery 失效，Worker 退出报告故障 |
| RabbitMQ | 默认 exchange、同名 durable 队列、persistent 消息、发布确认和 mandatory；手动 ACK，prefetch 等于并发数；关闭消费 channel 后未确认消息由服务端恢复 |

Redis 使用 XAUTOCLAIM，需 Redis 6.2+。执行成功，或失败记录已可靠保存后，所有者检查、XACK 和 XDEL 在同一 Lua 脚本中完成，已处理条目不继续占用 Stream。因此 Redis 适配器是竞争消费的工作队列，不支持在同一 Stream 上用多个消费组做广播；广播需使用独立队列或后端原生事件模型。Kafka Topic 及其保留策略由使用者管理，框架不调用管理 API 创建 Topic；保留时间必须覆盖处理与恢复窗口。

## 4. 失败存储与重放

先保存失败记录，再确认原消息。失败存储不可用时不确认，Worker 报错退出。连接、队列和任务 ID 确定失败记录 ID；再次投递可补做确认而不重复执行已记录失败的任务。这不是并发去重锁，也不会记录成功任务。

非法信封按原始字节摘要记录，保留原始数据和失败原因；这种记录无法直接重放，需修正生产者协议。失败原因使用固定分类，日志和 Console 列表不输出 payload 或任意业务异常文本。

失败任务固定使用 SQL 存储；它与负责传输待执行任务的队列驱动是两个独立组件。配置失败记录数据库并执行对应迁移：

```dotenv
QUEUE_FAILED__DATABASE=main
```

```bash
uv run alembic -c database/main/alembic.ini upgrade head
uv run python -m app.console queue failed --limit 20 --offset 0
uv run python -m app.console queue retry <failure-id>
uv run python -m app.console queue forget <failure-id>
```

### 查看 MySQL 中的失败消息

`queue_failed_jobs.payload` 保存队列收到的完整原始消息信封，因此模型使用 `LargeBinary`，在 MySQL 中对应 `LONGBLOB`。正常消息仍然是 UTF-8 JSON，可以转换为文本查看：

```sql
SELECT
    failure_id,
    reason,
    CONVERT(payload USING utf8mb4) AS envelope
FROM queue_failed_jobs
ORDER BY failed_at DESC;
```

完整信封中的 `payload` 是经过 Base64 编码的 Job 参数。对于合法信封，可以继续解码为 JSON 文本：

```sql
SELECT
    failure_id,
    reason,
    CONVERT(
        FROM_BASE64(
            JSON_UNQUOTE(
                JSON_EXTRACT(
                    CONVERT(payload USING utf8mb4),
                    '$.payload'
                )
            )
        )
        USING utf8mb4
    ) AS job_payload
FROM queue_failed_jobs
WHERE failure_id = '<failure-id>'
  AND reason <> 'invalid_envelope';
```

`invalid_envelope` 可能包含任意二进制数据，不能假设它是 JSON 或 UTF-8 文本。使用十六进制可以无损查看：

```sql
SELECT
    failure_id,
    reason,
    HEX(payload) AS payload_hex
FROM queue_failed_jobs
WHERE failure_id = '<failure-id>';
```

Console 的 `queue failed` 命令默认只展示失败元数据，不输出 payload，避免把用户 ID 或未来任务中的敏感业务数据泄漏到终端和命令日志。直接查询 payload 时也应遵守相同的数据访问和脱敏要求。

SQL 使用独立短事务，表名为 `queue_failed_jobs`，迁移归 main 管理。若选择其他数据库连接，必须保证该连接具有同一表结构；框架不会启动时自动建表。迁移 downgrade 会删除失败记录。

retry 生成新 job_id 并保留 replay_of，原失败记录保留；forget 单独删除。重复 retry 可生成多条任务。发布结果不确定时需检查下游，不能宣称人工重放 exactly-once。独立 Console 只读取配置的 SQL 失败存储；数据库不可访问时明确报错，不返回误导性的空列表。

## 5. 验证范围

测试包含内存实际消息流、SQLite 失败存储与迁移、模拟外部客户端的 ACK/offset/所有权恢复，以及 Worker 关闭和取消。未新增真实 Redis、Kafka、RabbitMQ 服务集成测试，模拟测试不代表真实服务已验证。

驱动机制参考 [aiokafka consumer](https://aiokafka.readthedocs.io/en/stable/consumer.html)、[aio-pika](https://docs.aio-pika.com/quick-start.html)、[Redis XCLAIM](https://redis.io/docs/latest/commands/xclaim/)。
