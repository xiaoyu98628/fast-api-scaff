# 队列

队列基础设施提供 JobCatalog、Dispatcher、QueueManager 和四种后端：Memory、Redis Streams、Kafka、RabbitMQ。HTTP 可以发布任务；消费由[独立 Worker](worker.md)启动。

## 1. 连接与逻辑队列

使用 `ApplicationContainer.queues` 获取已绑定连接的 Dispatcher：

```python
from app.bootstrap.container import ApplicationContainer

async def submit(container: ApplicationContainer, job: object):
    dispatcher = await container.queues.get("main")
    return await dispatcher.dispatch(job, queue="reports", correlation_id="request-123")
```

`job` 必须先注册到该容器的 `queues.catalog`。`get()` 不启动消费者；构建容器也不连接队列服务。第一次发布时 Kafka 才建立 Producer，RabbitMQ 在第一次 `get()` 时建立发布连接，Redis 客户端在首次命令时连接。Kafka Worker 只消费时不会初始化 Producer。

队列名映射为 Memory 队列名、Redis 的 `prefix + queue`、Kafka Topic、RabbitMQ 同名持久队列。RabbitMQ 使用默认 exchange 和同名 routing key；首版不提供自定义 exchange 或绑定。

配置见[配置参考](configuration.md#队列与-worker)与 `sample.env`。未配置连接时，HTTP/Console 仍可启动；调用队列公共入口才报告未配置错误。连接字段在容器构建时严格校验。

## 2. Job 数据与 Codec

业务 Application 定义纯数据类及业务发布窄协议。共享基础设施不能导入业务模块，也不使用 pickle、Python 模块路径或自动反射构造对象。

下面是可在同一进程执行的完整 Memory 示例，所有队列操作经过公共容器入口：

```python
import asyncio
from dataclasses import dataclass

from app.bootstrap.build import build_application_container
from app.bootstrap.runtime import ApplicationRuntime
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.queue import QueueSettings
from app.config.settings import Settings
from app.infrastructure.queue.catalog import JobDefinition
from app.interfaces.worker.executor import JobExecutor
from app.interfaces.worker.registry import HandlerRegistry
from app.interfaces.worker.runner import WorkerRunner

@dataclass(frozen=True, slots=True)
class ExampleJob:
    number: int

class ExampleCodec:
    def encode(self, job: ExampleJob) -> bytes:
        return str(job.number).encode()

    def decode(self, payload: bytes) -> ExampleJob:
        return ExampleJob(int(payload))

async def main() -> None:
    settings = Settings(
        app=AppSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        queue=QueueSettings(
            _env_file=None, default="main",
            connections={"main": {"driver": "memory", "capacity": 10}},
        ),
    )
    stop = asyncio.Event()

    async def handle(job: ExampleJob) -> None:
        print(job.number)
        stop.set()

    async with ApplicationRuntime(lambda: build_application_container(settings)) as container:
        definition = JobDefinition("example.number", 1, ExampleJob, ExampleCodec())
        container.queues.catalog.register(definition)
        handlers = HandlerRegistry()
        handlers.register(definition, handle)
        dispatcher = await container.queues.get("main")
        await dispatcher.dispatch(ExampleJob(42))
        executor = JobExecutor("main", "default", handlers, container.queues.failed_jobs, container.queues.codec)
        async with container.queues.consume(connection="main", concurrency=1) as consumer:
            await WorkerRunner(concurrency=1, shutdown_timeout=5).run(consumer, executor, stop)

asyncio.run(main())
```

真实业务将数据类放在上下文 Application，将 Codec、业务发布窄协议的实现放在该上下文 Infrastructure，在上下文组合根中注册任务定义。Worker 的 `composition.py` 只接收组合根公开的定义/服务来绑定 Handler，不直接导入上下文 Infrastructure。

JobDefinition 的同一 Python 类型只能注册一个发布版本；Worker 可注册不同类型的旧版本来兼容历史任务。重复注册报错。Catalog 不持有 Handler，HTTP 不加载执行依赖。

## 3. 信封与交付保证

信封包含 `schema_version=1`、`job_id`、`job_name`、`job_version`、`payload`、`enqueued_at`、`correlation_id`、`replay_of`。业务 payload 必须是合法 JSON 字节，在外层 JSON 中采用 Base64 表达；不接受 NaN/Infinity。默认整个信封不超过 1 MiB。时间保持本地无时区，各宿主应使用相同 `TZ`。

发布成功表示后端接受，不表示业务完成。发布超时或连接故障可能发生在接受之后，因此结果可能不确定，不能盲目重投。消息成功处理后再确认，外部后端恢复未确认消息时可能重复执行；业务幂等不由框架自动提供。数据库提交与发布不是原子操作，首版显式在 UoW 提交后投递，没有 after_commit 包装器或 Outbox。

| 后端 | 行为与边界 |
| --- | --- |
| Memory | `asyncio.Queue` 保存字节；容量包括在途任务，消费者关闭后使用恢复缓冲交还未确认任务；连接关闭唤醒等待者；进程退出丢失全部数据 |
| Redis | Streams + Consumer Group，消费时创建组并从 0-0 起读；XAUTOCLAIM 恢复超时 pending；后台续租；Lua 检查所有者后 ACK；command_timeout 独立于发布超时；失败退出后等待租约过期恢复 |
| Kafka | 禁止自动 offset 提交；每个分区最多一条在途，成功提交 offset+1 后恢复该分区；跨分区并发；再均衡取消当前执行并使旧 delivery 失效，Worker 退出报告故障 |
| RabbitMQ | 默认 exchange、同名 durable 队列、persistent 消息、发布确认和 mandatory；手动 ACK，prefetch 等于并发数；关闭消费 channel 后未确认消息由服务端恢复 |

Redis 使用 XAUTOCLAIM，需 Redis 6.2+。Redis Stream 不自动裁剪；ACK 只删除 pending 状态，不删除历史条目。保留策略由使用者按所有消费组进度设计，不能裁掉尚未确认的任务。Kafka Topic 及其保留策略由使用者管理，框架不调用管理 API 创建 Topic；保留时间必须覆盖处理与恢复窗口。

Memory 后端仅同一 QueueManager 的同名队列共享。独立 HTTP 与 Worker 进程不能通过它通信，需改用外部后端。没有隐式内存降级。

## 4. 失败存储与重放

先保存失败记录，再确认原消息。失败存储不可用时不确认，Worker 报错退出。连接、队列和任务 ID 确定失败记录 ID；再次投递可补做确认而不重复执行已记录失败的任务。这不是并发去重锁，也不会记录成功任务。

非法信封按原始字节摘要记录，保留原始数据和失败原因；这种记录无法直接重放，需修正生产者协议。失败原因使用固定分类，日志和 Console 列表不输出 payload 或任意业务异常文本。

失败任务固定使用 SQL 存储；这与负责传输待执行任务的 Memory Queue Driver 是两个独立组件。配置失败记录数据库并执行对应迁移：

```dotenv
QUEUE_FAILED__DATABASE=main
```

```bash
uv run alembic -c database/main/alembic.ini upgrade head
uv run python -m app.interfaces.console queue failed --limit 20 --offset 0
uv run python -m app.interfaces.console queue retry <failure-id>
uv run python -m app.interfaces.console queue forget <failure-id>
```

SQL 使用独立短事务，表名为 `queue_failed_jobs`，迁移归 main 管理。若选择其他数据库连接，必须保证该连接具有同一表结构；框架不会启动时自动建表。迁移 downgrade 会删除失败记录。

retry 生成新 job_id 并保留 replay_of，原失败记录保留；forget 单独删除。重复 retry 可生成多条任务。发布结果不确定时需检查下游，不能宣称人工重放 exactly-once。独立 Console 在 Memory 失败存储下明确报错，不返回误导性的空列表。

## 5. 验证范围

测试包含内存实际消息流、SQLite 失败存储与迁移、模拟外部客户端的 ACK/offset/所有权恢复，以及 Worker 关闭和取消。未新增真实 Redis、Kafka、RabbitMQ 服务集成测试，模拟测试不代表真实服务已验证。

驱动机制参考 [aiokafka consumer](https://aiokafka.readthedocs.io/en/stable/consumer.html)、[aio-pika](https://docs.aio-pika.com/quick-start.html)、[Redis XCLAIM](https://redis.io/docs/latest/commands/xclaim/)。
