# 数据库

数据库基础设施以“命名连接 + Provider + 延迟资源”为核心，向组合根提供 `DatabaseManager`，向业务上下文提供 Repository 与 Unit of Work。当前支持 MySQL、PostgreSQL 和 SQLite，全部使用 SQLAlchemy 异步接口。

## 1. 最小可运行配置

首次使用推荐 SQLite：

```dotenv
DB_DEFAULT=main
DB_CONNECTIONS__MAIN__DRIVER=sqlite
DB_CONNECTIONS__MAIN__DATABASE=data/database.sqlite
DB_CONNECTIONS__MAIN__ECHO=false
DB_CONNECTIONS__MAIN__SLOW_QUERY_MS=500
```

迁移和启动：

```bash
uv run alembic -c database/main/alembic.ini upgrade head
uv run uvicorn app.main:app --reload
```

相对数据库路径解析到 `storage/`。`:memory:` 只适合受控测试：不同连接的内存数据库生命周期和可见性容易与预期不一致，不建议作为常规开发配置。

## 2. 命名连接

```dotenv
DB_DEFAULT=main
DB_CONNECTIONS__MAIN__DRIVER=mysql
DB_CONNECTIONS__LEGACY__DRIVER=postgresql
DB_CONNECTIONS__LOCAL__DRIVER=sqlite
```

`DatabaseManager` 提供：

- `default_name`：默认连接名；
- `connection_names`：声明顺序下的连接名；
- `get(name)`：获取 `DatabaseResource`；
- `get_engine(name)`：获取异步 Engine；
- `session(name)`：创建并管理一个 `AsyncSession`；
- `is_initialized(name)`：资源是否已经创建；
- `aclose()`：逆序关闭已创建 Engine。

省略 `name` 时使用 `DB_DEFAULT`。但用户上下文在 `app.contexts.user.composition` 中显式指定 `main`，所以改变 `DB_DEFAULT` 不会改变用户数据源。这个设计让上下文的数据所有权显式，避免部署配置无意把业务切到错误数据库。

若希望切换用户数据库，应修改组合策略并配套检查迁移、测试和文档，不能只改环境变量猜测行为。

## 3. Provider 与驱动

| 配置 driver | SQLAlchemy 异步驱动 | 用途 |
| --- | --- | --- |
| `mysql` | `mysql+asyncmy` | MySQL |
| `postgresql` / `pgsql` | `postgresql+asyncpg` | PostgreSQL |
| `sqlite` | `sqlite+aiosqlite` | SQLite |

Provider 负责把严格校验后的配置转换为与 SQLAlchemy 有关的 Engine spec。业务上下文不应识别 driver 字符串，也不应构造数据库 URL。

连接模型禁止额外字段，能尽早暴露拼写错误和跨驱动误配。例如 SQLite 不能配置 `POOL_SIZE`，PostgreSQL 不能配置 MySQL 的 `CHARSET`。

## 4. 延迟生命周期

数据库连接经过三个不同阶段：

1. `DatabaseSettings` 读取 `connections` 原始字典；
2. 首次 `get/session` 时校验目标连接并创建 Engine；
3. SQLAlchemy 在第一次真实查询/事务时从池中建立网络连接。

因此：

- 应用启动成功不表示数据库凭据和网络正确；
- `is_initialized()` 为 true 只表示 Engine 资源已创建，不表示最近一次 ping 成功；
- 未使用的错误连接可能不会影响当前请求；
- `/health` 不访问数据库；
- 宿主关闭时只 dispose 已初始化的 Engine。

Manager 进入关闭后是终态：不会创建尚未初始化的 Engine，也不允许再次 `get/session`。需要重新启动时必须由新的应用 Runtime 构建新容器，不能复用已经关闭的 Manager。

如果需要数据库就绪探针，应显式定义就绪语义和超时，并与仅表示进程存活的健康检查区分。

## 5. Engine 与 Session

`DatabaseResource` 保存 `connection_name`、`AsyncEngine` 和 `async_sessionmaker`。Session 使用 `expire_on_commit=False`，提交后 DTO 映射不需要为了读取现有字段再次查询。

基础设施用法示例：

```python
from app.bootstrap.container import ApplicationContainer


async def inspect_connection(container: ApplicationContainer) -> None:
    async with container.databases.session("main") as session:
        # 这里只展示基础设施入口；业务代码应通过 Repository/UoW。
        await session.connection()
```

`DatabaseManager.session()` 只管理 Session 的打开与关闭，不会在正常退出时自动 commit。事务提交属于用例的 Unit of Work，避免“离开 session 就神秘提交”。

## 6. Repository、Mapper 与 Unit of Work

用户示例的数据流：

```text
HTTP / Console
  → UserApplicationService
  → UserUnitOfWork 协议
  → UserRepository 领域协议
  → SqlAlchemyUserUnitOfWork / Repository
  → Mapper
  → UserModel / AsyncSession
```

职责：

- `UserRepository` 是领域层所需的持久化契约，使用聚合和值对象；
- `SqlAlchemyUserRepository` 实现查询和持久化，不决定用例何时提交；
- Mapper 显式完成 Domain ↔ ORM 转换，包括把领域 `PasswordHash` 映射到数据库 `password` 列；
- `UserUnitOfWork` 定义一个用例的事务边界；
- Application Service 编排读取、领域行为、唯一性预检查与 commit。

Repository 的 `update()` 和 `remove()` 使用带主键条件的单条 DML，并返回是否匹配记录。Application Service 将零匹配转换为 `UserNotFoundError`，避免目标在并发期间已经删除时仍返回成功。这个返回值属于领域持久化协议，不向上层暴露 SQLAlchemy result。

用户 ID 在 Domain/Application 中使用 `UUID`，在数据库中统一保存为带连字符的小写 `String(36)`，例如 `019cba13-c9eb-7d22-845e-123456789abc`。Mapper 和 Repository 负责两种类型之间的转换，因此 MySQL、PostgreSQL、SQLite 的物理值与 HTTP 返回值保持一致。这个约定以跨数据库可见格式一致为优先级，PostgreSQL 不使用原生 UUID 列。

不要让领域对象继承 ORM Model，也不要把 SQLAlchemy Session 传进领域方法。显式 mapper 看起来多一层代码，但能避免 ORM 状态、懒加载和数据库字段成为领域模型的隐性 API。

## 7. 事务行为

用户写用例只有显式调用 `unit_of_work.commit()` 才会提交。出现异常时：

- commit 遇到 `IntegrityError` 会先 rollback；
- 事务上下文内其他异常退出时会 rollback；
- Session 最终关闭；
- 只读用例不 commit。

一个应用用例应尽量对应一个明确事务。不要在 Repository 中偷偷 commit，否则多个聚合操作无法被同一个 UoW 原子包裹，错误处理也会碎片化。

当前原子 UPDATE/DELETE 能识别写入时目标已经不存在，但没有乐观锁版本字段，因此不防止两个并发更新互相覆盖。作为使用说明型脚手架，它展示事务边界和聚合更新方式，但不承诺解决并发覆盖。真实业务若存在并发写，应按冲突语义选择版本号、条件更新、悲观锁或事件模型，并补充 409 映射与并发测试。

## 8. 唯一性与异常映射

应用服务会先查询用户名和邮箱是否存在，以提供快速、可读的冲突结果。但“先查再写”不能替代数据库唯一约束：两个并发事务都可能通过预检查。

最终一致性保护来自数据库约束。commit 捕获 `IntegrityError` 后，仅当驱动错误详情包含已知标记时才映射：

- 用户名：`uq_users_username`、`users_username_key`、`users.username`；
- 邮箱：`uq_users_email`、`users_email_key`、`users.email`。

无法识别的完整性错误原样抛出，最终按内部错误处理。这样做很重要：外键失败、非空约束、check constraint 或未知唯一约束都不应该被谎报为“用户名已存在”。

增加或重命名约束时，必须同时检查：

1. SQLAlchemy naming convention 和生成后的物理约束名；
2. MySQL/PostgreSQL/SQLite 的实际错误文本或结构化字段；
3. `_USER_UNIQUE_CONSTRAINT_MARKERS`；
4. UoW 和 HTTP/Console 错误映射测试。

## 9. 聚合不变量为什么不会交给 ORM

数据库读取通过 `User.rehydrate()` 恢复聚合，创建通过 `User.create()`，基本信息更新通过 `user.update_profile()`，状态修改通过 `user.change_status()`。聚合状态是私有的，对外提供只读属性。

“不变量被绕过”是指调用方若能直接写 `user.status = "whatever"`、直接构造半初始化实体、或 controller 直接更新 ORM 字段，就能跳过用户名、邮箱、状态、时间类型与时区等领域规则。当前结构要求外部通过命名行为改变聚合，mapper 只承担持久化转换。

基础设施 mapper 是受信任边界，但仍应调用 `rehydrate()`，让持久化脏数据尽早暴露，而不是生成一个领域层认为合法的假对象。

## 10. 多数据库边界

命名连接允许一个进程访问多个数据库，但不提供跨数据库原子事务。两个独立 Engine/Session 依次 commit 时，第二次失败无法自动撤销第一次提交。

不要这样设计：

```text
main commit
  → legacy commit
  → 假设两者原子成功
```

需要跨边界一致性时，应根据业务选择：

- 合并到同一事务所有者；
- 本地事务 + Outbox；
- 幂等事件消费者；
- 补偿流程/Saga；
- 接受并监控最终一致性。

不要为了复用而把 `DatabaseManager` 注入 domain/application 任意位置。组合根可以持有管理器，具体基础设施适配器可以按名称使用；业务层依赖的是用例需要的窄协议。

## 11. 模型注册与 Alembic

`main` 数据库使用独立目录：

```text
database/main/
├── alembic.ini
├── model_registry.py
└── migrations/
```

`model_registry.py` 显式导入所有属于 main metadata 的 ORM Model。新增模型后若忘记注册，`--autogenerate` 看不到它。

常用命令：

```bash
uv run alembic -c database/main/alembic.ini current
uv run alembic -c database/main/alembic.ini revision --autogenerate -m "create todos table"
uv run alembic -c database/main/alembic.ini upgrade head
uv run alembic -c database/main/alembic.ini downgrade -1
```

迁移环境的 `connection_name = main`，它显式读取 `DB_CONNECTIONS__MAIN__...`，不跟随 `DB_DEFAULT`。迁移使用独立 Engine 和 `NullPool`，结束时 dispose。

## 12. 迁移工作流

1. 修改 ORM Model 和领域/mapper；
2. 把新 Model 加入对应 `model_registry.py`；
3. 生成 revision；
4. 人工审查 upgrade 和 downgrade，不能盲信 autogenerate；
5. 在临时 SQLite 执行 upgrade → downgrade，并由 CI 在 MySQL/PostgreSQL 执行 upgrade → downgrade → upgrade；
6. 用实际数据库执行 upgrade；
7. 再启动依赖新 schema 的应用版本。

特别检查：

- 数据丢失型操作是否可接受；
- 新非空字段如何回填；
- 唯一约束在历史数据上是否可建立；
- 索引、默认值、时区和字符串长度的方言差异；
- downgrade 是否真实可逆；
- 约束名是否仍能被异常映射识别。

用户表的 `password` 列保存密码哈希而不是明文。它是非空字段，因此从已有用户表演进时必须明确历史数据回填或重置策略；不能在生产数据上直接生成一个无法审计的占位密码。

## 13. 方言差异

SQLite 适合快速反馈，但不能代替目标数据库验证：

- 锁与并发模型不同；
- 类型、默认值、DDL 和约束错误文本不同；
- MySQL 字符集/排序规则会影响大小写和唯一性；
- PostgreSQL 错误通常提供 constraint name，其他驱动可能主要依赖消息文本；
- SQLite migration 开启 batch rendering，生成的 DDL 方式不同；
- UUID、日期时间和字符串比较行为需要目标方言确认。

若生产使用 MySQL/PostgreSQL，关键迁移、唯一约束和并发场景必须在相同方言上测试。

## 14. 连接池和查询日志

MySQL/PostgreSQL 支持 `pool_size`、`max_overflow`、`pool_pre_ping`、`pool_recycle`。池越大不等于越快：总连接数约等于进程/worker 数乘以每个 Engine 的池容量，还要加 overflow。部署前应按数据库上限计算。

`ECHO=true` 会让 SQLAlchemy 输出 SQL；项目查询日志则提供：

- connection 名；
- duration；
- operation；
- 归一化 SQL 的 `statement_id`；
- 是否 executemany；
- 慢查询事件或失败 error code。

默认普通查询不包含 SQL 文本，慢查询也只记录可关联的摘要；开启 echo/查询明文前要评估敏感数据和日志量。

## 15. 故障定位

| 症状 | 首先检查 |
| --- | --- |
| `/health` 成功但用户接口 500 | `main` 配置、数据库可达性、迁移版本 |
| 提示连接 `main` 未配置 | 环境变量双下划线和连接名 |
| 改了 `DB_DEFAULT` 仍访问 main | 用户组合根显式连接名 |
| `no such table: users` | 是否用正确 ini 执行 `upgrade head`，SQLite 文件是否一致 |
| autogenerate 没有变化 | Model 是否加入 main model registry |
| 重复数据返回 500 | 物理约束名/驱动错误是否与精确 marker 匹配 |
| 连接耗尽 | worker 数、pool size、overflow、长事务/Session 泄漏 |
| SQLite 正常而生产失败 | 目标方言约束、DDL、排序规则和并发差异 |

综合排查步骤见[故障排查](troubleshooting.md)。
