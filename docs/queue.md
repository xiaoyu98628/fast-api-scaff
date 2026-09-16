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
await container.queues.dispatch(job, connection="redis", queue="reports")
```

`correlation_id` 是跨宿主关联字段，不等同于某一种入口 ID。HTTP、Console 与 Worker 分别在入口把 request ID、command ID 或消息 correlation ID 绑定到宿主无关的追踪上下文；Dispatcher 未收到显式值时自动继承它。因此正常调用只需 `dispatch(job)`，特殊场景仍可通过 `correlation_id="..."` 覆盖。没有追踪上游的根任务仍允许该字段为空。Console 的失败任务 retry 直接发布原信封，保留原 correlation ID，并通过新 `job_id` 和 `replay_of` 表达重放关系，不用当前 command ID 覆盖原调用链。

`dispatch()` 不启动消费者；构建容器也不连接队列服务。第一次发布时 Kafka 才建立 Producer，RabbitMQ 在第一次获取 Dispatcher 时建立发布连接，Redis 客户端在首次命令时连接。Kafka Worker 只消费时不会初始化 Producer。后端首次创建、连接或消费者创建阶段的驱动异常会在 `QueueManager` 边界转换为 `QueueError`，已有 `QueueError` 与任务取消保持原语义。

队列名映射为 Redis 的 `prefix + queue`、Kafka Topic、RabbitMQ 同名持久队列。配置默认队列、运行时 `dispatch(queue=...)`、重放和 Worker `--queue` 使用同一可移植规则：长度 1–200，只允许 ASCII 字母、数字、点、下划线和连字符，且不能是 `.` 或 `..`。RabbitMQ 使用默认 exchange 和同名 routing key；首版不提供自定义 exchange 或绑定。

`sample.env` 同时声明 `redis`、`kafka` 和 `rabbitmq` 三个命名连接，并以 `redis` 为默认连接、`default` 为该连接的默认逻辑队列。`uv run python -m app.worker` 直接消费该队列；`--connection` 和 `--queue` 只是高级覆盖。Worker 不会动态扫描所有物理队列；未显式隔离的 Job 都复用默认队列。

配置见[配置参考](configuration.md#队列与-worker)与 `sample.env`。未配置连接时，HTTP/Console 仍可启动；调用队列公共入口才报告未配置错误。连接字段在容器构建时严格校验。

## 2. QueueJob 与自动发现

一个业务任务由一个 QueueJob 类表达，数据与执行入口放在同一个类中。可消费任务必须直接定义在 `app/**/jobs.py` 或 `app/**/jobs/**/*.py`，也就是相对 `app` 的模块路径中包含独立的 `jobs` 段。推荐在限界上下文内使用 `jobs/` 包并按类名建立蛇形命名模块。包的 `__init__.py` 保持完全空，调用方从实际定义模块显式导入：

```python
from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.queue.job import QueueJob
from app.interfaces.worker.context import JobExecutionContext


@dataclass(frozen=True, slots=True)
class LoadUserJob(QueueJob[JobExecutionContext]):
    user_id: UUID

    async def handle(self, context: JobExecutionContext) -> None:
        # Job 是入站适配器：把 payload 转给已装配的应用用例。
        await context.container.users.service.get(self.user_id)
```

投递仍然只有一个入口：

```python
await container.queues.dispatch(LoadUserJob(user_id=user_id))
```

Worker 启动时通过 Python 包语义枚举 `app` 下的模块名称，只主动导入路径中含独立 `jobs` 段的模块和包。发现器只收集直接定义在当前模块中的非抽象 `QueueJob` 子类，忽略导入进来的别名；结果按模块和类名稳定排序。包遍历为读取子包 `__path__` 会导入包本身，因此所有 `__init__.py` 必须继续保持无副作用的空文件。`jobs` 模块顶层同样不得连接外部服务、读取业务数据或执行注册之外的实际动作。

发现完成后，Worker 在创建消费者前一次性校验任务引用、版本、Codec、历史 Decoder 和执行策略，并建立不可变任务目录。重复引用、模块导入失败或任务定义不合法都会阻止 Worker 启动，不会等到某条消息触发导入。消息处理只按 `(reference, version)` 查询目录，不执行由消息内容控制的 import。测试或自定义宿主仍可直接向 `JobResolver` 注入任务类型元组，以隔离自动发现。

默认任务引用仍是 `类型.__module__:类型.__qualname__`，因此现有消息协议不变。新任务可以显式声明与 Python 路径解耦的稳定 `reference`；移动或重命名已有任务时，用 `legacy_references` 保留旧消息引用：

```python
from typing import ClassVar


class LoadUserJob(QueueJob[JobExecutionContext]):
    reference: ClassVar[str | None] = "users.load"
    legacy_references: ClassVar[tuple[str, ...]] = (
        "app.contexts.user.jobs.load_user:LoadUserJob",
    )

    async def handle(self, context: JobExecutionContext) -> None:
        ...
```

引用长度最多 500，只允许 ASCII 字母、数字、点、下划线、连字符和冒号，且必须以字母或数字开头。当前引用、历史引用以及其他任务的全部引用都必须唯一。Dispatcher 把当前引用、默认版本 1 和 JSON payload 写入消息；Worker 解码后执行 `await job.handle(context)`。可先运行 `uv run python -m app.console queue jobs` 查看当前部署会发现的任务、引用、支持版本和策略，命令只做发现与校验，不启动应用容器或连接队列。

普通 dataclass 和 Pydantic Model 默认使用基于 Pydantic schema 的 JSON Codec；特殊当前协议可以在 Job 类上覆盖 `codec`。重试策略通过类级 `policy` 覆盖，当前版本通过类级 `version` 覆盖。`WorkerContext` 是不可变的进程级宿主上下文，保存当前 `Settings` 和已启动的 `ApplicationContainer`；执行器从它为每条消息创建独立的 `JobExecutionContext`，继续直接提供 `settings` 和 `container`，并把低频消息元数据收敛到 `context.job`。其中包括 `id`、`reference`、`version`、`enqueued_at`、`queue_connection`、`queue_name`、`correlation_id` 和 `replay_of`。同一条消息的全部投递内重试复用同一个任务上下文。所有消费槽共享同一个应用容器，数据库 Session 和业务 UoW 仍需按任务或用例单独创建。Manager 保持延迟初始化，未被 Job 使用的数据库、缓存、HTTP 或向量资源不会仅因 Worker 启动而连接。

Job 属于 Worker 入站适配边界。业务任务应通过 `context.container.<context>.service` 调用应用用例，让 Repository、事务和业务缓存策略继续封装在限界上下文中；不要把 `JobExecutionContext`、`WorkerContext` 或 `ApplicationContainer` 传入 Application/Domain。宿主级维护任务确实需要通用技术能力时，可以使用 `context.container.databases`、`caches`、`http`、`queues` 或 `vectors` 的公共入口，但不应直接依赖具体数据库、Redis、Memcached 或其他驱动。

### Job 版本兼容

升级 payload 契约时递增 `version`，并通过 `legacy_decoders` 显式声明仍受支持的历史版本。历史 Decoder 接收旧 payload，但必须返回当前 Job 类型；当前版本始终使用 `codec`。例如：

```python
import json
from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from app.infrastructure.queue.errors import JobDecodeError
from app.infrastructure.queue.job import QueueJob
from app.interfaces.worker.context import JobExecutionContext


class LoadUserV1Decoder:
    def decode(self, payload: bytes) -> "LoadUserJob":
        try:
            data = json.loads(payload)
            return LoadUserJob(user_id=UUID(data["id"]))
        except (KeyError, TypeError, ValueError) as error:
            raise JobDecodeError("版本 1 payload 不合法") from error


@dataclass(frozen=True, slots=True)
class LoadUserJob(QueueJob[JobExecutionContext]):
    user_id: UUID
    source: str = "queue"
    version: ClassVar[int] = 2
    legacy_decoders: ClassVar[dict[int, LoadUserV1Decoder]] = {1: LoadUserV1Decoder()}

    async def handle(self, context: JobExecutionContext) -> None:
        await context.container.users.service.get(self.user_id)
```

自定义 Codec 和历史 Decoder 对坏数据应抛出 `JobDecodeError`，Worker 会把它记录为 `invalid_job_payload` 并确认消息。任务目录中不存在的引用记为 `unknown_job`，未声明的历史版本记为 `unsupported_job_version`。jobs 模块或其依赖导入失败、Codec/Policy/Decoder 配置错误会在开始消费前阻止启动；消息到达后 Decoder 意外异常或返回错误类型仍属于部署定义缺陷，Worker 保持消息未确认并退出，不能把它伪装成可丢弃的未知消息。删除历史 Decoder 或历史引用前，应确认所有生产者已经升级且对应旧消息已经排空。

任务引用属于队列消息契约。现有任务未声明 `reference` 时仍使用类路径；移动它之前应先发布包含旧类路径 `legacy_references` 的兼容版本，再移动代码，最后在生产者升级且旧消息排空后删除别名。新任务优先选择稳定、表达业务含义的引用，可减少目录重构对消息协议的影响。不要通过在旧模块重新导入新类维持兼容：发现器会忽略非当前模块直接定义的类，兼容关系应显式写在任务定义中。

当前内置 `LoginSucceededJob` 作为最小业务示例：登录 HTTP 适配器在会话提交后向默认队列尽力投递 `user_id` 参数和固定文案，Dispatcher 自动把当前 request ID 写入消息的 `correlation_id`；Worker 调用其 `handle(context)`，再通过 `context.container.users.service.get(user_id)` 使用数据库读取当前用户，最后只记录文案、结构化用户 ID 和状态。消息本身不携带用户名、密码或 Token，日志也不记录用户名、邮箱或认证秘密。用户已删除属于永久业务状态，任务记录 `user.login_succeeded.user_missing` 后结束；数据库运行故障继续由投递内重试和失败存储处理。`user_id` 暂时可空，以兼容队列中已经存在的旧消息，旧消息会跳过数据库查询。发布失败不改变登录响应。该通知不具备 Outbox 或 exactly-once 保证，不应用于审计或安全决策。

## 3. 信封与交付保证

信封包含 `schema_version=2`、`job_id`、`job_type`、`job_version`、`payload`、`enqueued_at`、`correlation_id`、`replay_of`。`job_type` 保存任务稳定引用；未显式声明时它与可导入类路径相同。业务 payload 必须是合法 JSON 字节，在外层 JSON 中采用 Base64 表达；不接受 NaN/Infinity。默认整个信封不超过 1 MiB。时间保持本地无时区，各宿主应使用相同 `TZ`。旧的 schema version 1 消息会按非法信封写入失败记录，不会尝试执行。

发布成功表示后端接受，不表示业务完成。发布超时或连接故障可能发生在接受之后，因此结果可能不确定，不能盲目重投。消息成功处理后再确认，外部后端恢复未确认消息时可能重复执行；业务幂等不由框架自动提供。数据库提交与发布不是原子操作，首版显式在 UoW 提交后投递，没有 after_commit 包装器或 Outbox。

| 后端 | 行为与边界 |
| --- | --- |
| Redis | Streams + Consumer Group，消费时创建组并从 0-0 起读；XAUTOCLAIM 恢复超时 pending；单次 Lua 调用检查并批量续租全部在途消息；Lua 检查所有者后原子 XACK + XDEL；command_timeout 独立于发布超时；失败退出后等待租约过期恢复 |
| Kafka | 禁止自动 offset 提交；每个分区最多一条在途，成功提交 offset+1 后恢复该分区；跨分区并发；新分配分区的首条消息保守标记为可能重投；再均衡取消当前执行并使旧 delivery 失效，Worker 退出报告故障 |
| RabbitMQ | 默认 exchange、同名 durable 队列、persistent 消息、发布确认和 mandatory；手动 ACK，prefetch 等于并发数；关闭消费 channel 后未确认消息由服务端恢复 |

Redis 使用 XAUTOCLAIM，需 Redis 6.2+。续租脚本先确认全部在途消息仍属于当前消费者，再在一次 Redis 调用中刷新租约；任何消息缺失或已经换主都会使本轮失败并取消对应执行任务。执行成功，或失败记录已可靠保存后，所有者检查、XACK 和 XDEL 在同一 Lua 脚本中完成，已处理条目不继续占用 Stream。因此 Redis 适配器是竞争消费的工作队列，不支持在同一 Stream 上用多个消费组做广播；广播需使用独立队列或后端原生事件模型。Kafka Topic 及其保留策略由使用者管理，框架不调用管理 API 创建 Topic；保留时间必须覆盖处理与恢复窗口。

## 4. 失败存储与重放

先保存失败记录，再确认原消息。失败存储不可用时不确认，Worker 报错退出。连接、队列和任务 ID 确定失败记录 ID；再次投递可补做确认而不重复执行已记录失败的任务。这不是并发去重锁，也不会记录成功任务。

失败记录补偿查询不再位于每条消息的正常热路径：Redis 仅对 XAUTOCLAIM 恢复消息查询，RabbitMQ 使用 broker 的 redelivered 标记，Kafka 对新分配分区的首条消息保守查询。新消息直接执行，最终失败时仍先写 SQL 再 ACK；因此该优化不改变至少一次投递和 ACK 失败恢复语义。

非法信封按原始字节摘要记录，保留原始数据和失败原因；这种记录无法直接重放，需修正生产者协议。失败原因使用固定分类，日志和 Console 列表不输出 payload 或任意业务异常文本。

失败任务固定使用 SQL 存储；它与负责传输待执行任务的队列驱动是两个独立组件。配置失败记录数据库并执行对应迁移：

```dotenv
QUEUE_FAILED__DATABASE=main
```

```bash
uv run alembic -c database/main/alembic.ini upgrade head
uv run python -m app.console queue jobs
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
