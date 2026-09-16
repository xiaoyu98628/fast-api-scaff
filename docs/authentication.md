# 认证

用户上下文提供简单数据库会话，用于演示认证用例如何贯穿 Domain、Application、Infrastructure 和 HTTP。没有角色、权限或版本控制，用户表保持原结构。现有用户 CRUD 和 Console 命令保持公开示例行为，`GET /api/v1/auth/me` 是需要登录的示例接口。

## 使用方式

先按[快速开始](getting-started.md)配置数据库。会话模型已注册到 Alembic metadata，维护者已手动生成 `user_sessions` 迁移。检查并执行迁移、创建用户后即可登录：

```bash
uv run alembic -c database/main/alembic.ini upgrade head
```

登录使用 JSON，不是 OAuth2 表单或 JWT：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"password123"}'
```

成功响应的 `data` 包含：

```json
{
  "access_token": "<随机会话令牌>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

复制实际返回的 `access_token` 使用：

```bash
curl http://127.0.0.1:8000/api/v1/auth/me \
  -H 'Authorization: Bearer <access_token>'

curl -X POST http://127.0.0.1:8000/api/v1/auth/logout \
  -H 'Authorization: Bearer <access_token>'
```

`/auth/me` 返回统一响应中的用户 DTO，不包含密码或哈希。退出返回 204，没有 JSON 响应体。OpenAPI 的 `SessionBearer` 安全方案可在 Swagger Authorize 中使用。

登录成功并提交会话后，HTTP 适配器通过后台任务向默认连接配置的默认逻辑队列（`sample.env` 为 `default`）投递 `LoginSucceededJob`。Request ID 中间件建立请求 ID 后，追踪中间件在完整请求及后台任务期间把它绑定为当前 `correlation_id`；Dispatcher 自动写入消息，发布函数不需要接收或传递该 ID。消息以 `user_id` 参数标识登录用户，并包含固定文案“用户登录成功，队列任务已执行。”，不包含用户名、密码或 Token。独立 Worker 消费后使用当前 `JobExecutionContext` 调用任务的 `handle(context)`，通过用户应用服务从数据库读取执行时的最新用户 DTO，并记录该文案、结构化用户 ID 和状态，使任务调用链日志能够与原请求关联：

```bash
uv run python -m app.worker
```

该通知是尽力而为的示例副作用：Redis 未配置、不可用或发布结果不确定时会记录 `user.login_succeeded.dispatch_failed`，但不改变已经成功的登录响应。数据库会话提交与消息发布不是原子事务，通知可能丢失或重复，不能据此实现审计、计费或安全控制。Job 查询的是消费时数据，可能与登录时不同；用户已经删除时记录 `user.login_succeeded.user_missing` 并正常结束，其他数据库故障继续进入队列重试和失败存储。日志只保留用户 ID 和状态，不包含用户名、邮箱、密码、密码哈希或 Token。

## 输入与错误

- 登录用户名允许 1–128 字符输入，随后按用户值对象规则 trim、转小写和校验。
- 登录密码允许 1–1024 字符，原值验证；不套用创建密码时的最小长度规则，也不 trim。
- 用户名不存在、不符合领域格式规则、密码错误、禁用账户，或密码验证后用户已被删除时，统一按登录失败处理，不创建会话。启用限制且尚未锁定时返回 401、认证错误码 `1101`、动态剩余尝试次数；未启用限制时不返回次数。
- 用户不存在或用户名格式错误时，密码组件使用固定占位哈希完成一次验证；占位哈希由基础设施持有且永远不能认证成功，避免 Application 层依赖 Argon2 格式。
- JSON 结构、长度或额外字段不合法返回统一 422，响应不包含输入值。
- `/auth/me` 缺少凭据、格式错误、Token 不存在、已过期、用户不存在或禁用时返回 401。
- `/auth/logout` 要求格式正确的 Bearer Token；不存在、已退出或已过期的会话也返回 204。
- 认证 401 附带 `WWW-Authenticate: Bearer` 和 `Cache-Control: no-store`；登录、当前用户和退出的成功响应也禁止缓存。
- 所有登录凭据失败都附带 `WWW-Authenticate: Bearer` 和 `Cache-Control: no-store`，不通过状态码或公开文案区分账户是否存在。
- 同一规范化用户名达到失败阈值时，当次及锁定期内的登录返回 429、认证错误码 `1102`、`Retry-After` 和 `Cache-Control: no-store`；正文同时返回剩余锁定秒数，429 不附带 `WWW-Authenticate`。

只接受 Authorization 请求头，不从 URL、查询参数或 Cookie 读取 Token。示例 curl 使用本地 HTTP；实际网络传输应使用 HTTPS。应用访问日志不记录密码、请求凭据或响应 Token。

## 登录失败限制

`AUTH_LOGIN_LIMIT_CACHE` 指定保存登录安全状态的命名缓存连接。未配置时关闭限制；`sample.env` 将它设为 `session`。该连接必须使用 Redis，因为计数依赖原子 `INCR` 和 TTL。组合根在构建容器时检查驱动，选择 Memcached、其他驱动或不存在的连接会直接报告配置错误，检查过程不会建立网络连接。

默认规则如下：

- `AUTH_LOGIN_MAX_FAILURES=5`；
- `AUTH_LOGIN_FAILURE_WINDOW_SECONDS=300`，从第一次失败开始计算固定窗口；
- `AUTH_LOGIN_LOCK_SECONDS=900`，第 5 次失败把计数 key 延长为 15 分钟锁定并立即返回 429；
- 用户名不存在、领域格式无效、密码错误、账户禁用，以及慢哈希后重新核对失败都会计数；
- 锁定预检查先于数据库查询和密码哈希，锁定期内即使密码正确也直接返回 429；
- 阈值前通过最终凭据核验后，会在数据库会话提交前删除失败计数；删除失败时回滚新会话。

启用限制后的第一次失败示例：

```json
{
  "code": "4010011101",
  "success": false,
  "message": "用户名或密码错误，还可尝试 4 次",
  "data": {"remaining_attempts": 4},
  "request_id": "..."
}
```

触发锁定或锁定期间的示例：

```json
{
  "code": "4290011102",
  "success": false,
  "message": "登录失败次数过多，已临时锁定，请在 900 秒后重试",
  "data": {"retry_after_seconds": 900},
  "request_id": "..."
}
```

完整响应码仍由 HTTP 状态、服务码和认证局部码拼接，以上示例使用默认服务码 `001`。锁定响应的 `Retry-After` 头与 `data.retry_after_seconds` 使用同一个值。用户名不存在、格式无效、密码错误和账户禁用都会生成相同结构，不通过文案、状态码或数据字段暴露账户是否存在。

Redis key 只包含 `username.strip().lower()` 的 SHA-256 摘要，不保存原始用户名、密码或 Token。首次递增与固定窗口 TTL 由 Redis Lua 脚本原子完成；达到阈值后更新同一 key 的 TTL。多个应用进程共享计数。Redis 读取、递增、TTL 更新或成功后的清理失败都按安全状态不可确认处理，登录返回通用 500，不把故障当作未命中，也不自动回退到进程内计数。成功凭据的失败计数在新会话数据库事务提交前清理，因此清理失败会回滚会话，不会留下调用方未收到 Token 的有效记录。Redis 与数据库之间没有分布式事务：若计数已经清理而随后数据库提交失败，该次登录不会产生有效会话，但先前失败计数不会自动恢复。该路径只发生在密码及最终账户状态均已核验通过之后，避免为此引入 Saga 或额外持久化协调状态。

限流维度只有规范化用户名，因此攻击者可以针对已知用户名主动触发临时锁定。增加 IP 维度前必须先明确可信反向代理和客户端地址解析规则；当前实现不读取未经确认的转发头。

## 会话存储与生命周期

`user_sessions` 位于 `main` 数据库，只保存随机 Token 的 SHA-256 摘要。Token 由 `secrets.token_urlsafe(32)` 生成，密码继续使用 Argon2；两者不混用。令牌摘要为主键，用户 ID 和过期时间有索引。

`AUTH_SESSION_TTL_SECONDS` 默认 3600，允许 1–2592000 秒。签发时使用 `datetime.now()`，以本地无时区 `datetime` 写入 `issued_at/expires_at`，ORM 字段使用 `DateTime()`。过期时间通过 `issued_at + timedelta(seconds=session_ttl_seconds)` 计算，到 `expires_at` 即失效；无滑动续期或刷新 Token。配置变更只影响新会话，HTTP 响应的 `expires_in` 仍表示有效期秒数。

会话和用户资料遵循同一时间约定，所有宿主必须保持相同的 `TZ`。数据库记录本身不携带时区，已有会话存在时修改 `TZ` 会改变时间解释；不应直接切换时区。领域模型拒绝带时区的签发时间、过期时间和比较时钟。

每次登录建立独立会话，并在写入新会话的同一事务中删除全局已过期会话；退出只删除当前会话。没有登录活动时不会主动运行清理。请求认证时读取当前用户状态，因此：

| 事件 | 已有会话的行为 |
| --- | --- |
| 密码重置 | 在密码写入的同一事务中全部撤销 |
| 用户禁用 | 在状态写入的同一事务中全部撤销 |
| 用户重新启用 | 旧会话不会恢复，必须重新登录 |
| 用户删除 | 认证失败 |
| 会话过期或退出 | 认证失败 |

密码重置、用户禁用及其会话撤销使用同一个 `UserUnitOfWork` 和数据库事务，任一步骤失败都会整体回滚；启用账户不创建或恢复会话。外键声明删除级联；SQLite Provider 会为每个新连接启用外键约束，因此删除用户会同步删除其会话。过期会话由后续成功登录清理，不依赖后台任务。数据库不可用会作为运行故障处理，不会降级成匿名身份。

登录慢哈希在事务外执行，随后重新核对用户、密码哈希和状态再保存会话。这不提供与并发密码重置严格串行的保证；用户数据版本只保护聚合写入。密码重置完成后会撤销当时已有的全部会话，但当前方案没有认证版本，因此不能把它表述为跨并发请求的严格认证代际屏障。

创建用户会先校验用户名、邮箱和密码，并在 Argon2 哈希前执行用户名、邮箱占用预检查；哈希后仍会重新检查并依赖数据库唯一约束处理并发竞争。密码重置先确认目标用户存在，哈希完成后再重新读取并按数据版本更新，因此重复创建和不存在用户的重置请求不会占用 Argon2 额度，版本冲突则返回 409。

## 应用入口与边界

宿主通过已经启动的 `ApplicationContainer` 调用公开服务：

```python
from app.runtime.container import ApplicationContainer
from app.contexts.user.application.auth_dto import LoginCommand
from app.contexts.user.application.dto import UserDTO
from app.contexts.user.application.session_token import SessionCredential


async def demonstrate_login(container: ApplicationContainer) -> UserDTO:
    token = await container.users.auth.login(
        LoginCommand(username="alice", password="password123"),
    )
    credential = SessionCredential(token=token.access_token)
    user = await container.users.auth.current_user(credential)
    await container.users.auth.logout(credential)
    return user
```

Domain/Application 不持有容器、数据库 Manager 或缓存 Manager。认证服务依赖 `UserUnitOfWorkFactory`、`PasswordHasher`、`SessionTokenCodec`、`LoginAttemptLimiter` 窄协议和可注入时钟。Redis 适配器由用户上下文组合点注入。用户与会话 Repository 共享同一个 SQLAlchemy Session，由用例显式提交，退出时沿用现有 UoW 的回滚、取消与资源清理。

本示例不提供角色权限、IP 登录限流、客户端 Token 存储策略、自助改密、刷新令牌或会话后台清理。现有公开用户 CRUD 不能因为增加了登录示例就被视为受保护接口。
