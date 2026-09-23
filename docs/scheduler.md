# 独立 Scheduler

Scheduler 是与 HTTP、Console 和 Worker 并列的独立宿主。它读取代码中声明的计划，按照容器操作系统本地时区计算触发时间，并通过 `ApplicationContainer.queues` 投递现有 `QueueJob`。Scheduler 不消费队列，也不直接执行业务用例；Worker 负责消息解码、重试、失败存储和 `QueueJob.handle(context)` 调用。

## 1. 启动

```bash
uv run python -m app.scheduler
# 查看当前代码计划目录
uv run python -m app.console scheduler list
# 只启动 Compose 中的 Scheduler
docker compose up --build scheduler
```

Scheduler 和 Worker 是两个常驻进程。存在已注册计划时，Scheduler 会在启动触发循环前校验计划使用的队列连接和逻辑队列；校验不建立网络连接。计划到期并首次投递时才按需创建队列后端。注册表为空是合法状态，进程仍会响应终止信号并完成应用容器生命周期。

`scheduler list` 使用与 SchedulerHost 相同的代码目录，按稳定计划 ID 输出 Trigger、Job 引用和版本、声明的队列路由、合并策略及延迟窗口。它不输出任务 payload，不构建应用容器，也不连接外部服务；`connection` 或 `queue` 为 `null` 表示计划使用对应默认值。空目录输出 `[]`。

同一部署只运行一个 Scheduler 实例。每个实例都使用内存计划目录并独立计算触发时间；并行运行多个实例会重复投递相同计划。队列仍采用至少一次执行语义，业务 Job 应根据自身副作用设计幂等边界。

## 2. 组件边界

```text
app/contexts/<context>/schedules/
        ↓
QueueJobSchedule / ScheduleRegistry
        ↓
SchedulerEngine
        ↓
APScheduler 入站适配器
        ↓
QueueManager.dispatch()
        ↓
Redis / Kafka / RabbitMQ
        ↓
Worker → QueueJob.handle(context)
```

`app.interfaces.scheduler.contracts` 定义稳定的计划和 Trigger；`app.interfaces.scheduler.apscheduler` 是唯一允许导入 APScheduler 的应用模块，架构测试保护该边界。`SchedulerHost` 只依赖 `SchedulerEngine` 协议，不接触第三方 `Job`、`Task`、`Schedule`、JobStore 或 DataStore 类型。

计划以代码为唯一来源，每次启动由 `app.interfaces.scheduler.discovery.discover_schedule_registry()` 扫描并构建，不写入 APScheduler 持久化存储。SchedulerHost 和 `scheduler list` 使用同一个发现入口。稳定计划 ID 用于重复校验、日志聚合和运行诊断，不作为业务幂等键。

## 3. 声明计划

业务任务必须直接定义在 `app/**/jobs.py` 或 `app/**/jobs/**/*.py`，确保 Worker 能按现有约定发现和校验。下面的目录表达报表上下文拥有计划声明和队列任务：

```text
app/contexts/report/
├── jobs/
│   ├── __init__.py
│   └── generate_daily_report.py
└── schedules/
    ├── __init__.py
    └── reports.py
```

任务保持 Worker 入站适配器职责：

```python
from dataclasses import dataclass

from app.infrastructure.queue.job import QueueJob
from app.interfaces.worker.context import JobExecutionContext


@dataclass(frozen=True, slots=True)
class GenerateDailyReportJob(QueueJob[JobExecutionContext]):
    """调用报表应用服务生成每日结果。"""

    async def handle(self, context: JobExecutionContext) -> None:
        """把周期触发转换为报表应用用例调用。"""

        await context.container.reports.service.generate_daily()
```

上下文计划模块只声明触发和队列路由：

```python
from app.contexts.report.jobs.generate_daily_report import GenerateDailyReportJob
from app.interfaces.scheduler.contracts import CronSchedule, QueueJobSchedule
from app.interfaces.scheduler.registry import ScheduleRegistry


def register_schedules(registry: ScheduleRegistry) -> None:
    """注册报表上下文拥有的周期计划。"""

    registry.add(
        QueueJobSchedule(
            id="reports.daily.generate",
            trigger=CronSchedule(hour=3, minute=0),
            job=GenerateDailyReportJob(),
            queue="reports",
        )
    )
```

发现器只导入 `app` 包下路径中含独立 `schedules` 包的模块，并按模块名稳定调用当前模块直接定义的 `register_schedules(registry)`。辅助模块可以不定义注册函数；`schedules/__init__.py` 保持空白。新增计划文件无需修改 Scheduler、Console 或全局组合根。计划模块导入失败、同名注册对象不是当前模块直接定义、注册过程失败或计划 ID 重复都会中止发现，避免部署在计划不完整时继续运行。计划模块在导入阶段只能声明代码，不应连接数据库、队列或其他外部服务。

`QueueJobSchedule` 在加入目录前验证稳定 ID、Trigger、合并策略、延迟窗口以及 Job 编码契约。计划保存构造时提供的 Job 值，并在每次触发时重新编码为新消息；Job 应采用不可变值对象，随执行时间变化的数据由 Worker 通过应用服务读取，不在 Scheduler 中读取业务数据库。

用户上下文使用文件夹组织计划：

```text
app/contexts/user/
├── jobs/
│   └── cleanup_expired_sessions.py
└── schedules/
    ├── __init__.py
    └── sessions.py
```

内置 `users.sessions.cleanup_expired` 计划使用 `CronSchedule(hour=0, minute=0)`，在容器本地时间每天 `00:00:00` 向默认队列投递 `CleanupExpiredSessionsJob`。Job 调用认证应用服务，使用现有 `UserUnitOfWork` 删除 `expires_at <= now` 的数据库会话；Scheduler 不直接访问数据库。发现器自动调用 `sessions.py` 中的 `register_schedules(registry)`。

## 4. Trigger 语义

Cron 使用容器操作系统本地时区：

```python
CronSchedule(hour=3, minute=0)
CronSchedule(minute="*/5")
CronSchedule(hour=9, minute=0, day_of_week="mon-fri")
```

`day_of_week` 只接受 `mon`–`sun` 英文名称及其组合表达式，不接受数字星期，避免第三方调度版本对数字起点的不同解释。计划不提供任务级时区覆盖；HTTP、Console、Worker 和 Scheduler 应运行在相同容器本地时区。

固定间隔计划显式声明首次触发方式：

```python
IntervalSchedule(
    seconds=300,
    start=IntervalStartPolicy.AFTER_INTERVAL,
)

IntervalSchedule(
    seconds=30,
    start=IntervalStartPolicy.IMMEDIATELY,
)
```

`AFTER_INTERVAL` 在一个完整间隔后首次触发，`IMMEDIATELY` 在引擎启动后立即到期。适配器显式计算 `start_date`，不依赖第三方库默认值。

## 5. 错过执行与投递失败

`misfire_grace_seconds` 定义计划晚于原触发时间多久仍允许投递。`CoalescePolicy.LATEST` 把多个错过时间合并为一次，`CoalescePolicy.ALL` 为每个允许执行的错过时间触发一次投递。

Scheduler 的 `max_instances=1` 只限制同一计划的投递回调并发，不限制消息到达 Worker 后的业务执行并发。需要避免重复副作用时，应在应用服务、数据库约束或所属基础设施中建立业务幂等边界。

队列投递异常记录 `scheduler.dispatch_failed`，details 只包含计划 ID、安全异常类型和栈位置。发布结果可能不确定，因此 Scheduler 不自动盲目重投；后续计划时间仍正常触发。成功投递记录 `scheduler.job_dispatched` 及消息 ID。

## 6. 生命周期和日志

Scheduler 复用 `ApplicationRuntime`，启动顺序为容器、计划目录、队列路由校验、调度引擎；关闭时先暂停新触发，等待已经提交给调度执行器的投递结束，再关闭调度引擎和应用容器。停机因此可能等待当前队列发布完成；队列发布失败仍按 `scheduler.dispatch_failed` 记录。SIGINT 和 SIGTERM 转换为协作式停止请求。调度引擎与容器关闭都得到尝试，多个关闭根因通过异常组保留。

生命周期事件：

- `scheduler.starting`；
- `scheduler.schedules_discovered`；
- `scheduler.started`；
- `scheduler.start_failed`；
- `scheduler.stopping`；
- `scheduler.stopped`；
- `scheduler.stop_failed`；
- `scheduler.failed`。

异常日志遵循项目统一安全诊断规则，不记录异常消息、运行时局部变量或任务 payload。
