# 架构说明

项目采用模块化单体：一个部署单元内按限界上下文划分业务，并在每个上下文内部保持 Domain、Application、Infrastructure 边界。HTTP 与 Console 是宿主适配器，共享组合根、应用用例和资源生命周期。

这不是为了堆叠 DDD 名词，而是解决三个实际问题：业务规则不被框架入口绕过，基础设施可以替换/测试，多入口复用同一用例且不会出现行为分叉。

## 1. 总体结构

```text
app/
├── bootstrap/              # 设置、组合根、容器和运行时生命周期
├── config/                 # 环境配置模型
├── contexts/
│   └── user/
│       ├── domain/         # 聚合、值对象、领域错误、Repository 协议
│       ├── application/    # 用例、Command/DTO、UoW 协议、应用错误
│       ├── infrastructure/ # SQLAlchemy Repository/UoW/Mapper/Model
│       └── composition.py  # 用户上下文装配
├── infrastructure/        # 跨上下文基础设施能力：数据库、缓存、HTTP 出站、日志
├── interfaces/
│   ├── http/               # FastAPI 宿主
│   └── console/            # Typer 宿主
└── runtime/                # 项目路径等进程运行约定

database/main/              # main 数据库的 Alembic 环境与模型注册
tests/                      # 分层测试与架构约束
```

`infrastructure` 不是“所有可复用代码”的杂物目录。只有真正跨上下文的技术能力放在顶层；某个上下文的 ORM Model、Repository 和 UoW 实现留在该上下文内部。

## 2. 依赖方向

核心方向：

```text
interfaces ─┐
            ├→ application → domain
infrastructure ┘      ↑
       composition 负责把实现注入协议
```

更严格地说：

- Domain 只依赖自己的 Domain 和标准库；
- Application 只依赖自己的 Application、Domain 和标准库；
- Infrastructure 可以依赖 Application/Domain 协议并实现它们；
- Interfaces 依赖 Application DTO/错误，不把 FastAPI/Typer 传入业务层；
- Bootstrap/Composition 是允许知道具体实现的装配边界。

`tests/test_architecture.py` 用 AST 检查 Domain、Application、Infrastructure 与 Interfaces 的导入。它不仅保护核心层，还禁止共享 Infrastructure 反向依赖业务或宿主、上下文 Infrastructure 跨上下文依赖，以及 Interfaces 直接穿透到上下文 Infrastructure。相对导入也会被视为违规，项目统一要求绝对、显式导入。这类测试防止边界在日常迭代中悄悄腐化。

## 3. 用户限界上下文

用户上下文是教学型业务样例，包含：

- 聚合根 `User`；
- 值对象 `UserId`、`Username`、`EmailAddress`；
- 状态枚举 `UserStatus`；
- Repository 与 Unit of Work 协议；
- `UserApplicationService` 用例；
- SQLAlchemy mapper/repository/UoW/model；
- HTTP 与 Console 入口。

它不包含认证、密码、token、角色和权限。不要因为目录名叫 user 就推断它已经是完整 IAM 上下文；真实系统可能需要把身份、账户、资料、组织成员关系拆成不同边界。

## 4. 聚合与不变量

`User` 的状态字段使用私有属性，只暴露只读 property。创建、恢复和更新分别走：

- `User.create()`：生成 ID、设置默认状态和创建/更新时间；
- `User.rehydrate()`：从数据库恢复，同时重新验证规则；
- `User.update_profile()`：原子地校验并更新资料与时间。

不变量包括用户名格式与归一化、邮箱格式与归一化、显示名称长度、合法状态、值对象类型以及本地无时区 datetime。

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

`Username` 和 `EmailAddress` 在构造时 trim 并转小写，使比较和唯一性使用规范化值。值对象不可变，避免同一个字符串在不同入口拥有不同规则。

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

Application 不知道 FastAPI、Typer、SQLAlchemy 或具体数据库。时钟以 callable 注入，测试可提供固定本地时间。

Application Service 可以做跨聚合的流程编排和权限决策，但不应承载实体自身的核心规则。反过来，Domain 也不应执行数据库/缓存/网络 I/O。

## 7. Repository、UoW 与 Mapper 模式

这些模式各自解决不同问题：

| 模式 | 解决的问题 | 不负责什么 |
| --- | --- | --- |
| Repository | 以领域语言读取/保存聚合 | 不决定事务提交，不返回 ORM 泄漏 |
| Unit of Work | 定义一个用例的事务边界 | 不承载业务规则 |
| Mapper | Domain 与 ORM 的显式转换 | 不编排用例 |
| Provider | 把驱动配置转为资源定义 | 不暴露给业务层 |

用户 UoW 还在数据库唯一约束冲突时做精确异常翻译。未知 `IntegrityError` 原样保留，因为错误映射是语义承诺，过宽映射会把真实数据缺陷伪装成普通冲突。

## 8. Container 与 Composition Root

`ApplicationContainer` 保存：

- `DatabaseManager`；
- `CacheManager`；
- `HttpClientManager`；
- 已组装的 `UserContext`；
- 启动和关闭 callback。

`build_application_container()` 是全局组合根，`build_user_context()` 是上下文组合点。它们可以依赖具体实现，因为“选择实现并接线”就是它们的职责。

容器不是业务 Service Locator。若 application service 接收整个容器，它可以在任意地方获取任何数据库、缓存和上下文，真实依赖无法从构造签名看出。这就是“容器抽象诱导边界穿透”：工具本身合理，滥用方式会让边界失效。

规则：入口使用容器选择公开服务；上下文组合根把窄依赖注入具体服务；业务对象不持有容器。

## 9. ApplicationRuntime 与宿主

`ApplicationRuntime` 管理非特定宿主的容器生命周期：

- 防止同一 runtime 重复启动；
- 构建容器并执行 startup callbacks；
- 启动失败时尝试关闭；若启动与清理同时失败，以异常组完整保留两侧根因；
- 关闭时先清空当前引用，再聚合资源关闭错误；
- 支持 `async with`。

HTTP lifespan 和 Console 都复用 runtime。这样资源的初始化、失败清理和关闭顺序不会在不同入口重复实现。数据库、缓存和 HTTP 出站资源都由管理器延迟创建，并由容器 callback 逆序关闭；未初始化资源不会在关闭阶段被创建。关闭进入不可取消清理区间，单个 callback 失败或收到取消后仍会尝试剩余 callback，最后通过异常组保留全部根因。Manager/延迟资源是一次性生命周期对象，关闭开始后拒绝新获取，也不能通过再次调用 `get()` 隐式重建。

顶层 HTTP 出站能力只负责驱动无关请求、连接池、超时、传输错误和日志，不知道具体上游协议。上下文若需要调用外部服务，应在自己的 application 层定义业务窄端口，在 infrastructure 层使用公共 HTTP 客户端实现，并由 composition 注入；application service 不应持有整个容器，也不应直接导入 HTTPX。

未来增加常驻 Scheduler 时，也应建立独立宿主：读取同一 Settings、配置适合 Scheduler 的日志、通过 Runtime 获取容器、响应终止信号并优雅关闭。它不应通过 HTTP 请求或系统 cron 间接触发，也不应把无限循环塞进 Console 命令。但当前仓库尚未实现 Scheduler，以上只是扩展边界，不是现有功能。

## 10. 时间约定

当前项目默认使用本地无时区 datetime：

- application clock 默认为 `datetime.now`；
- domain 拒绝带 offset 的 datetime；
- ORM 使用不带 timezone 的 `DateTime()`；
- `TZ` 规定进程本地时区语义。

这种方案适合明确以单一业务时区表达“墙上时间”的脚手架，但代价是值本身无法证明属于哪个时区。所有宿主必须保持同一 `TZ`，变更时区需要数据迁移。

如果业务跨时区、需要精确时间线或与外部系统交换绝对时间，应重新设计为 UTC aware datetime/instant，并同步领域、DTO、数据库列、序列化、迁移和测试；不能只改某一层。

## 11. HTTP 与 Console 适配器

两个入口都调用 `UserApplicationService`：

- HTTP 负责 schema、status、统一 JSON 和异常到 HTTP 映射；
- Console 负责 Typer 参数、JSON stdout、错误 stderr 和退出码；
- 二者都不实现业务规则，不直接操作 ORM。

HTTP 独立定义 `page/limit` 查询协议和 `items + meta` 分页响应，并在调用应用服务前把页码换算为 `offset/limit`。Console 的 `users list` 仅作为调用应用用例的示例，保留无范围约束的 `--page/--limit` 参数并直接输出应用 DTO；后台批处理应根据任务语义使用 `batch_size`、进度、stdout/stderr 和退出码，而不是复用 HTTP 分页响应。

新增宿主的判断标准不是“能否 import service”，而是是否完整承担自身协议边界、日志、生命周期、取消和错误语义。

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
  → database/cache/logging
  → configuration/lifecycle
  → tests/docs/migrations
```

局部修复若破坏依赖方向、事务边界、时间语义或宿主一致性，应优先调整整体方案。具体质量命令见[开发与质量](development.md)。
