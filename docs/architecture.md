# 架构说明

项目采用模块化单体：一个部署单元内按限界上下文划分业务，并在每个上下文内部保持 Domain、Application、Infrastructure 边界。HTTP、Console 与 Worker 是独立宿主，共享配置、组合根和资源生命周期；HTTP、Console 与 Worker Job 都可以在各自的入站边界选择已装配的应用用例，Worker 通过不可变上下文向动态解析的 QueueJob 提供当前应用容器。

这不是为了堆叠 DDD 名词，而是解决三个实际问题：业务规则不被框架入口绕过，基础设施可以替换/测试，多入口复用同一用例且不会出现行为分叉。

## 1. 总体结构

```text
app/
├── main.py                 # HTTP/ASGI 薄入口
├── console.py              # Console 薄入口
├── worker.py               # Worker 薄入口
├── bootstrap/              # 全局组合根与 HTTP/Console/Worker 启动装配
│   ├── build.py
│   ├── http/
│   ├── console/
│   └── worker/
├── config/                 # 环境配置模型
├── contexts/
│   └── user/
│       ├── domain/         # 聚合、值对象、领域错误、Repository 协议
│       ├── application/    # 用例、Command/DTO、UoW 协议、应用错误
│       ├── infrastructure/ # SQLAlchemy Repository/UoW/Mapper/Model
│       └── composition.py  # 用户上下文装配
├── infrastructure/        # 跨上下文基础设施：数据库、缓存、向量、HTTP 出站、队列、日志
├── interfaces/             # 入站协议适配，不负责启动与全局装配
│   ├── http/               # FastAPI 请求、响应、中间件和路由
│   ├── console/            # Typer 命令、参数、展示和退出码
│   └── worker/             # 队列 Job 动态解析、执行和消费并发
└── runtime/                # 宿主无关的容器、生命周期和进程路径约定

database/main/              # main 数据库的 Alembic 环境与模型注册
tests/                      # 分层测试与架构约束
```

`infrastructure` 不是“所有可复用代码”的杂物目录。只有真正跨上下文的技术能力放在顶层；某个上下文的 ORM Model、Repository 和 UoW 实现留在该上下文内部。

## 2. 依赖方向

核心方向：

```text
入口模块 → bootstrap → interfaces → application → domain
                     ├→ runtime
                     └→ infrastructure

bootstrap/composition 负责选择实现并完成装配
```

更严格地说：

- Domain 只依赖自己的 Domain 和标准库；
- Application 只依赖自己的 Application、Domain 和标准库；
- Infrastructure 可以依赖 Application/Domain 协议并实现它们；
- Interfaces 依赖 Application DTO/错误，不把 FastAPI/Typer 传入业务层；
- Interfaces 不依赖 Bootstrap，避免协议适配器反向控制启动装配；
- Runtime 保存宿主无关的 `ApplicationContainer` 和 `ApplicationRuntime`；
- Bootstrap/Composition 是允许知道具体实现、Interfaces 和 Runtime 的装配边界。

`tests/test_architecture.py` 用 AST 检查 Domain、Application、Infrastructure、Interfaces 与 Bootstrap 的导入。它不仅保护核心层，还禁止共享 Infrastructure 反向依赖业务或宿主、上下文 Infrastructure 跨上下文依赖、Interfaces 依赖 Bootstrap，以及 Interfaces 直接穿透到上下文 Infrastructure。相对导入也会被视为违规，项目统一要求绝对、显式导入。这类测试防止边界在日常迭代中悄悄腐化。

## 3. 用户限界上下文

用户上下文是教学型业务样例，包含：

- 聚合根 `User`；
- 值对象 `UserId`、`Username`、`EmailAddress`、`Password`、`PasswordHash`；
- 状态枚举 `UserStatus`；
- Repository 与 Unit of Work 协议；
- `UserApplicationService` 用例；
- SQLAlchemy mapper/repository/UoW/model 与 pwdlib 密码哈希适配器；
- HTTP 与 Console 入口。

它覆盖用户 CRUD、密码重置和简单会话认证。`AuthApplicationService` 提供登录、当前用户和退出，独立的 `UserSession` 记录令牌摘要与有效期，并通过 `UserUnitOfWork.sessions` 与用户仓储共享事务。用户表没有角色、认证版本或数据版本字段；公开 CRUD 不受登录校验保护，也不包含用户自行修改密码和角色权限体系。它是示例上下文，并非完整 IAM。

## 4. 聚合与不变量

`User` 的状态字段使用私有属性，只暴露只读 property。创建、恢复和更新分别走：

- `User.create()`：生成 ID、设置默认状态和创建/更新时间；
- `User.rehydrate()`：从数据库恢复，同时重新验证规则；
- `User.update_profile()`：原子地校验并更新基本信息与时间；
- `User.change_status()`：独立校验并修改用户状态与时间。
- `User.reset_password()`：用新的密码哈希替换旧哈希并更新时间。

不变量包括用户名格式与归一化、邮箱格式与归一化、密码长度、密码哈希有效性、合法状态、值对象类型以及本地无时区 datetime。

“聚合不变量容易被绕过”具体指以下坏路径：

```text
Controller 直接改 ORM Model
Repository 接收任意 dict 并 update
调用方直接给 user._status 赋值
从数据库恢复时绕过 rehydrate
```

这些路径会让某个入口接受非法状态，而另一个入口拒绝，最终数据库与领域认知不一致。当前结构通过命名行为、只读公开状态、mapper 和架构边界降低绕过风险。

Python 无法提供绝对私有性；下划线是协作契约。真正的保证来自代码结构、审查和测试，而不是假设技术上完全无法访问 `_field`。

## 5. 值对象

`UserId` 在领域中封装标准 `UUID`，基础设施将它映射为数据库中的带连字符 `String(36)`，使数据库物理值和 HTTP 表达一致。`Username` 和 `EmailAddress` 在构造时 trim 并转小写，使比较和唯一性使用规范化值。`Password` 只检查长度，不 trim 或改变大小写；`PasswordHash` 是聚合持有和持久化的形式。两个密码值对象都隐藏 repr，应用 DTO 和接口响应也不包含密码字段。值对象不可变，避免同一个原始值在不同入口拥有不同规则。

值对象适合：

- 有独立校验/归一化语义；
- 没有独立身份；
- 可按值比较；
- 会在多个领域行为中重复使用。

不要为每个原始字段机械创建类。若一个字段只是展示文本且规则只属于聚合，放在聚合中校验可能更清晰。

## 6. Application Service

`UserApplicationService` 负责用例编排：

```text
接收 Command
  → 创建/加载聚合
  → 调用领域行为
  → 使用 Repository
  → 显式 commit
  → 返回 DTO
```

Application 不知道 FastAPI、Typer、SQLAlchemy、pwdlib 或具体数据库。时钟和 `PasswordHasher` 窄端口由组合根注入，测试可提供固定时间和确定性的假哈希实现。端口提供 `async def hash(self, password: Password) -> PasswordHash` 和 `async def verify(self, password: str, password_hash: PasswordHash) -> bool`。基础设施适配器在线程中执行 Argon2 哈希和验证，两类操作共享同一个默认容量为 2 的限制器；用户服务和认证服务复用该实例。创建用户在哈希前做规范化与唯一性预检查，写入前再次检查；密码重置在确认目标存在后才哈希，并在写入事务中重新读取。这些预检查减少无效请求的计算占用，最终正确性仍由事务内检查和数据库约束保证。取消调用时会等待本次工作结束再传播取消，避免提前释放仍在计算的额度。聚合不会接触明文密码。

会话令牌通过应用层 `SessionTokenCodec` 窄协议注入，基础设施使用 `secrets.token_urlsafe(32)` 和 SHA-256。用户不存在时立即抛出 `LoginUserNotFoundError`，HTTP 映射为 404 和“用户不存在”，不执行密码验证；用户存在时，慢密码验证在数据库事务外执行，签发前重新读取密码哈希与账户状态。没有版本字段或锁定串行化，重新读取不是并发改密撤销保证；已有会话也不会因密码重置失效。完整契约见[认证](authentication.md)。

Application Service 可以做跨聚合的流程编排和权限决策，但不应承载实体自身的核心规则。反过来，Domain 也不应执行数据库/缓存/网络 I/O。

## 7. Repository、UoW 与 Mapper 模式

这些模式各自解决不同问题：

| 模式 | 解决的问题 | 不负责什么 |
| --- | --- | --- |
| Repository | 以领域语言读取/保存聚合 | 不决定事务提交，不返回 ORM 泄漏 |
| Unit of Work | 定义一个用例的事务边界 | 不承载业务规则 |
| Mapper | Domain 与 ORM 的显式转换 | 不编排用例 |
| Provider | 把驱动配置转为资源定义 | 不暴露给业务层 |

用户 UoW 在 commit 阶段和事务体退出阶段处理唯一约束异常，覆盖 INSERT 提交和 UPDATE 立即执行两条路径；执行阶段的异常在回滚、关闭成功后转换。未知 `IntegrityError` 原样保留，因为错误映射是语义承诺，过宽映射会把真实数据缺陷伪装成普通冲突。

## 8. Runtime Container 与 Composition Root

`app.runtime.container.ApplicationContainer` 保存：

- `DatabaseManager`；
- `CacheManager`；
- `HttpClientManager`；
- `QueueManager`；
- `VectorStoreManager`；
- 已组装的 `UserContext`；
- 启动和关闭 callback。

`app.bootstrap.build.build_application_container()` 是全局组合根，`build_user_context()` 是上下文组合点。它们可以依赖具体实现，因为“选择实现并接线”就是它们的职责。

`UserContext.service` 保留用户 CRUD，`UserContext.auth` 提供认证用例。`build_user_context(databases, *, session_ttl_seconds=3600)` 由全局组合根传入认证配置；构建时不连接数据库、不计算密码哈希，也不新增需要关闭的资源。

容器不是业务 Service Locator。若 application service 接收整个容器，它可以在任意地方获取任何数据库、缓存和上下文，真实依赖无法从构造签名看出。这就是“容器抽象诱导边界穿透”：工具本身合理，滥用方式会让边界失效。

规则：入口使用容器选择公开服务；上下文组合根把窄依赖注入具体服务；业务对象不持有容器。

## 9. ApplicationRuntime 与宿主

`app.runtime.lifecycle.ApplicationRuntime` 管理非特定宿主的容器生命周期：

- 防止同一 runtime 重复启动；
- 构建容器并执行 startup callbacks；
- 启动失败时尝试关闭；若启动与清理同时失败，以异常组完整保留两侧根因；
- 关闭时先清空当前引用，再聚合资源关闭错误；
- 支持 `async with`。

HTTP lifespan、ConsoleHost 和 WorkerHost 都复用 runtime。这样资源的初始化、失败清理和关闭顺序不会在不同入口重复实现。数据库、缓存、向量和 HTTP 出站资源都由管理器延迟创建，并由容器 callback 逆序关闭；未初始化资源不会在关闭阶段被创建。关闭进入不可取消清理区间，单个 callback 失败或收到取消后仍会尝试剩余 callback，最后通过异常组保留全部根因。Manager/延迟资源是一次性生命周期对象，关闭开始后拒绝新获取，也不能通过再次调用 `get()` 隐式重建。数据库、缓存和向量 Manager 在第一次等待前统一禁止所有资源获取，再逐个释放；已经开始的初始化允许完成，但结果只交给关闭流程，不再返回调用方。宿主必须先停止使用已经借出的资源，再关闭 Manager。

顶层 HTTP 出站能力只负责驱动无关请求、连接池、超时、传输错误和日志，不知道具体上游协议。上下文若需要调用外部服务，应在自己的 application 层定义业务窄端口，在 infrastructure 层使用公共 HTTP 客户端实现，并由 composition 注入；application service 不应持有整个容器，也不应直接导入 HTTPX2。

未来增加常驻 Scheduler 时，也应建立独立宿主：读取同一 Settings、配置适合 Scheduler 的日志、通过 Runtime 获取容器、响应终止信号并优雅关闭。它不应通过 HTTP 请求或系统 cron 间接触发，也不应把无限循环塞进 Console 命令。但当前仓库尚未实现 Scheduler，以上只是扩展边界，不是现有功能。

## 10. 时间约定

当前项目默认使用本地无时区 datetime：

用户资料和会话的 `issued_at/expires_at` 都遵循下述约定。会话使用 `datetime.now()` 签发，通过 `timedelta(seconds=...)` 计算过期时间，并映射为 `DateTime()`；认证配置和响应中的有效期仍以秒数表示。

- application clock 默认为 `datetime.now`；
- domain 拒绝带 offset 的 datetime；
- ORM 使用不带 timezone 的 `DateTime()`；
- `TZ` 规定进程本地时区语义。

这种方案适合明确以单一业务时区表达“墙上时间”的脚手架，但代价是值本身无法证明属于哪个时区。所有宿主必须保持同一 `TZ`，变更时区需要数据迁移。

如果业务跨时区、需要精确时间线或与外部系统交换绝对时间，应重新设计为 UTC aware datetime/instant，并同步领域、DTO、数据库列、序列化、迁移和测试；不能只改某一层。

## 11. HTTP、Console 与 Worker 适配器

HTTP 与 Console 都调用 `UserApplicationService`，Worker 则解析消息携带的 QueueJob 类型，并通过 `WorkerContext` 调用其 `handle(context)`：

- HTTP 负责 schema、status、统一 JSON 和异常到 HTTP 映射；
- Console 负责 Typer 参数、JSON stdout、错误 stderr 和退出码；
- Worker 负责消息解码、宿主上下文注入、执行策略、并发消费和确认；
- 三者都不实现业务规则，不直接操作 ORM，也不负责全局启动装配。

HTTP 独立定义 `page/limit` 查询协议和 `items + meta` 分页响应，并在调用应用服务前把页码换算为 `offset/limit`。Console 的 `users list` 也在宿主边界约束 `page` 和 `limit`，但直接输出应用 DTO；后台批处理应根据任务语义使用 `batch_size`、进度、stdout/stderr 和退出码，而不是复用 HTTP 分页响应。

新增宿主时，`interfaces` 只承担协议边界，`bootstrap` 负责日志、组合、生命周期、取消和进程入口。不能因为某个适配器能够 import service，就把启动装配重新放回 `interfaces`。

## 12. 跨上下文协作

简单同步协作可以由上层 application workflow 依赖两个上下文公开的窄服务，但要明确事务不一定跨上下文原子。

当出现以下需求时，再考虑领域/集成事件：

- 一个上下文完成后多个下游需要独立响应；
- 允许最终一致性；
- 需要降低同步耦合；
- 需要异步重试与幂等消费。

当数据库提交与消息发布必须可靠关联时再引入 Outbox。当跨多个所有者需要补偿时再考虑 Saga。脚手架当前没有这些机制，不应通过内存回调假装拥有可靠消息语义。

## 13. 新增限界上下文的步骤

1. 明确业务语言、聚合边界、数据所有权和用例；
2. 创建 `app/contexts/<name>/domain`、`application`、`infrastructure` 及空 `__init__.py`；
3. 先定义领域模型、值对象、错误和 Repository 协议；
4. 定义 Command/DTO、应用服务和 UoW/外部端口协议；
5. 在 infrastructure 实现 mapper、ORM、repository/UoW 或外部适配器；
6. 创建 `<context>/composition.py`，只公开宿主需要的 service；
7. 在全局 container 中接线，并同步生命周期 callback；
8. 为 HTTP/Console 建立协议适配器；
9. 注册 ORM metadata 和编写迁移；
10. 增加 domain、application、infrastructure、interface 与 architecture 测试；
11. 同步配置、`sample.env`、README 和专题文档。

上下文名应是业务语言，不要按技术名建立 `services`、`repositories`、`models` 顶级大目录。新顶级包还要避免与 Python 标准库重名。

## 14. 何时不要继续加抽象

当前模式已经覆盖多入口、事务边界、多驱动和业务隔离。以下做法通常过早：

- 只有一个实现却为每个小函数创建 Factory/Strategy；
- 为未来微服务预先增加 RPC 层；
- 没有异步事件需求就引入消息总线；
- 为两个简单步骤引入 Saga；
- 把所有对象塞进全局 container；
- 为追求“纯 DDD”复制没有行为的贫血 DTO 层；
- 把 CRUD 样例包装成大量无业务价值的领域事件。

判断标准是：抽象是否保护了一个真实边界、隔离了变化、让测试/语义更清楚。若只是增加跳转层数，就不应该引入。

## 15. 架构变更检查

任何跨层修改都应沿链路复查：

```text
公开入口
  → schema/command/DTO
  → application workflow
  → domain invariants
  → repository/UoW/mapper
  → database/cache/vector/logging
  → configuration/lifecycle
  → tests/docs/migrations
```

局部修复若破坏依赖方向、事务边界、时间语义或宿主一致性，应优先调整整体方案。具体质量命令见[开发与质量](development.md)。

## 16. 队列与 Worker

共享基础设施 queue 提供 QueueJob、Dispatcher、QueueManager、驱动和 FailedJobStore。ApplicationContainer.queues 与数据库等 Manager 一样按需使用；队列先关闭，数据库后关闭。HTTP 不订阅队列。

独立 `app.worker` 入口由 `app.bootstrap.worker` 完成装配并复用 ApplicationRuntime；`app.interfaces.worker` 负责 Job 类路径解析、宿主上下文注入、消息执行、重试和消费并发。QueueJob 将可序列化数据与 `handle(context)` 收敛在同一类，投递时自动把类路径写入消息，Worker 动态导入并验证该类型；框架不扫描 `contexts`、`jobs` 或其他业务目录，不维护业务注册表，应用组合根也不收集 Job。当前示例把任务放在上下文级 `jobs/` 包并按类名使用蛇形命名模块，但这只是组织习惯。

`WorkerContext` 与 `ConsoleContext` 一样，只在宿主/入站适配边界暴露当前配置和已经启动的 `ApplicationContainer`。Job 应优先从容器选择当前上下文的公开应用服务；需要数据库、缓存或外部服务的业务流程，仍由 Application 层定义窄协议并经 composition 注入实现。Application/Domain 不导入 Worker、具体 Manager、队列驱动或全局容器，共享 Infrastructure 不导入具体业务。所有消费槽共享应用级 Manager，任务级 Session、UoW 和事务不能跨 Job 共享。内置 `LoginSucceededJob` 由登录 HTTP 适配器在会话提交后尽力投递，作为默认队列和 `handle(context)` 日志输出的最小示例，不进入认证 Application/Domain，也不参与登录事务。

SQL 失败表属于共享技术能力，在 main metadata 注册；失败写入使用独立短事务，不借用业务 UoW。任务执行和消息确认不是跨系统原子事务。详见[队列](queue.md)、[Worker](worker.md)。
