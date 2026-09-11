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

登录成功并提交会话后，HTTP 适配器通过后台任务向默认连接配置的默认逻辑队列（`sample.env` 为 `default`）投递 `LoginSucceededJob`。Request ID 中间件建立请求 ID 后，追踪中间件在完整请求及后台任务期间把它绑定为当前 `correlation_id`；Dispatcher 自动写入消息，发布函数不需要接收或传递该 ID。消息以 `user_id` 参数标识登录用户，并包含固定文案“用户登录成功，队列任务已执行。”，不包含用户名、密码或 Token。独立 Worker 消费后使用当前 `JobExecutionContext` 调用任务的 `handle(context)`，记录该文案和结构化用户 ID，并使任务调用链日志能够与原请求关联：

```bash
uv run python -m app.worker
```

该通知是尽力而为的示例副作用：Redis 未配置、不可用或发布结果不确定时会记录 `user.login_succeeded.dispatch_failed`，但不改变已经成功的登录响应。数据库会话提交与消息发布不是原子事务，通知可能丢失或重复，不能据此实现审计、计费或安全控制。

## 输入与错误

- 登录用户名允许 1–128 字符输入，随后按用户值对象规则 trim、转小写和校验。
- 登录密码允许 1–1024 字符，原值验证；不套用创建密码时的最小长度规则，也不 trim。
- 用户名不存在、不符合领域格式规则、密码错误、禁用账户，或密码验证后用户已被删除时，统一返回 401 和“用户名或密码错误”，不创建会话。
- 用户不存在或用户名格式错误时，密码组件使用固定占位哈希完成一次验证；占位哈希由基础设施持有且永远不能认证成功，避免 Application 层依赖 Argon2 格式。
- JSON 结构、长度或额外字段不合法返回统一 422，响应不包含输入值。
- `/auth/me` 缺少凭据、格式错误、Token 不存在、已过期、用户不存在或禁用时返回 401。
- `/auth/logout` 要求格式正确的 Bearer Token；不存在、已退出或已过期的会话也返回 204。
- 认证 401 附带 `WWW-Authenticate: Bearer` 和 `Cache-Control: no-store`；登录、当前用户和退出的成功响应也禁止缓存。
- 所有登录凭据失败都附带 `WWW-Authenticate: Bearer` 和 `Cache-Control: no-store`，不通过状态码或公开文案区分账户是否存在。

只接受 Authorization 请求头，不从 URL、查询参数或 Cookie 读取 Token。示例 curl 使用本地 HTTP；实际网络传输应使用 HTTPS。应用访问日志不记录密码、请求凭据或响应 Token。

## 会话存储与生命周期

`user_sessions` 位于 `main` 数据库，只保存随机 Token 的 SHA-256 摘要。Token 由 `secrets.token_urlsafe(32)` 生成，密码继续使用 Argon2；两者不混用。令牌摘要为主键，用户 ID 和过期时间有索引。

`AUTH_SESSION_TTL_SECONDS` 默认 3600，允许 1–2592000 秒。签发时使用 `datetime.now()`，以本地无时区 `datetime` 写入 `issued_at/expires_at`，ORM 字段使用 `DateTime()`。过期时间通过 `issued_at + timedelta(seconds=session_ttl_seconds)` 计算，到 `expires_at` 即失效；无滑动续期或刷新 Token。配置变更只影响新会话，HTTP 响应的 `expires_in` 仍表示有效期秒数。

会话和用户资料遵循同一时间约定，所有宿主必须保持相同的 `TZ`。数据库记录本身不携带时区，已有会话存在时修改 `TZ` 会改变时间解释；不应直接切换时区。领域模型拒绝带时区的签发时间、过期时间和比较时钟。

每次登录建立独立会话，并在写入新会话的同一事务中删除全局已过期会话；退出只删除当前会话。没有登录活动时不会主动运行清理。请求认证时读取当前用户状态，因此：

| 事件 | 已有会话的行为 |
| --- | --- |
| 密码重置 | 继续有效；之后登录必须使用新密码 |
| 用户禁用 | 认证失败 |
| 用户重新启用 | 未过期、未删除的会话恢复可用 |
| 用户删除 | 认证失败 |
| 会话过期或退出 | 认证失败 |

外键声明删除级联；SQLite Provider 会为每个新连接启用外键约束，因此删除用户会同步删除其会话。过期会话由后续成功登录清理，不依赖后台任务。数据库不可用会作为运行故障处理，不会降级成匿名身份。

登录慢哈希在事务外执行，随后重新核对用户、密码哈希和状态再保存会话。这不提供与并发密码重置严格串行的保证；用户数据版本只保护聚合写入，当前方案没有认证版本或改密全设备退出能力。

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

Domain/Application 不持有容器或数据库 Manager。认证服务依赖 `UserUnitOfWorkFactory`、`PasswordHasher`、`SessionTokenCodec` 和可注入时钟。用户与会话 Repository 共享同一个 SQLAlchemy Session，由用例显式提交，退出时沿用现有 UoW 的回滚、取消与资源清理。

本示例不提供角色权限、登录限流、客户端 Token 存储策略、自助改密、刷新令牌或会话后台清理。现有公开用户 CRUD 不能因为增加了登录示例就被视为受保护接口。
