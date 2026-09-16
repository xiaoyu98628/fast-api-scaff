# fast-api-scaff

面向 Python 3.14+ 的 FastAPI 模块化单体脚手架。项目以限界上下文组织业务，以 Domain/Application/Infrastructure 分层保护依赖方向，并让 HTTP、Console、Worker 等宿主复用同一套应用用例、配置和资源生命周期。

## 已实现能力

- FastAPI HTTP API、OpenAPI、统一 JSON 响应与 SSE 事件工厂；提供 `GET /api/v1/streams/events` 有限事件流及模拟失败（[调用规则](docs/http.md#12-统一-sse-响应)）；
- Typer Console，一次性命令共享应用容器；
- 用户限界上下文 CRUD、状态修改与密码重置示例，密码哈希和验证在线程中执行并共享并发限制；
- 数据库会话认证：登录、当前用户、退出，随机 Bearer Token 只保存摘要，并用 Redis 限制连续登录失败；
- MySQL、PostgreSQL、SQLite 异步 SQLAlchemy；
- Repository、Mapper、Unit of Work 与 Alembic migration；
- Redis、Memcached 字节级 KV 缓存，Redis Storage 按数据类型组织适配器；
- 可选的 Redis HTTP IP 限流：默认关闭，同一 IP 的 API 请求共享 1000 次/60 秒配额，超限返回 429；
- Milvus（本地 Lite/远程）、Chroma（本地持久化/远程）和 Elasticsearch 统一异步向量存储；
- 普通与流式 HTTP 出站请求、独立连接池、阶段超时、池压力诊断和结构化日志；
- Redis Streams、Kafka、RabbitMQ 队列适配器和独立 Worker；
- QueueJob 约定发现与不可变任务目录、稳定引用、显式历史版本解码、投递内重试、SQL 失败存储及 Console 诊断/重放；
- JSON/Text 结构化日志、HTTP request ID、Console command ID、Worker 任务关联、访问日志和数据库查询日志；
- 架构依赖测试、pytest、Ruff、ty 与 GitHub Actions 质量检查；
- CI 使用临时 MySQL/PostgreSQL 服务验证 Alembic upgrade、downgrade 和再次 upgrade。

当前不包含角色/权限体系、刷新令牌、常驻 Scheduler、领域事件/Outbox/Saga、跨数据库原子事务、Redis 高级数据结构、缓存自动降级或通用 HTTP 自动重试。它们需要按实际业务边界设计，不能把规划项当作现有功能。用户 CRUD 仍是公开示例，`GET /api/v1/auth/me` 演示登录校验。

HTTP 请求限流通过 `RATE_LIMIT_ENABLED=true` 启用；`RATE_LIMIT_CACHE` 选择已有 Redis 连接，省略时使用默认缓存连接。配额由 `RATE_LIMIT_MAX_REQUESTS=1000` 和 `RATE_LIMIT_WINDOW_SECONDS=60` 配置，独立于登录失败限制。Redis 操作失败默认返回 503，只有显式设置 `RATE_LIMIT_FAIL_OPEN=true` 才故障放行。代理部署必须保证 ASGI 客户端地址可信，应用不直接解析转发头。详见 [HTTP 限流规则](docs/http.md#13-http-请求限流)和[配置参考](docs/configuration.md#http-请求限流)。

向量 `upsert` 覆盖完整元数据，省略的旧字段会被删除。Chroma 每次写入额外读取一次旧元数据，并在同一客户端内串行执行读后写；多个独立客户端或进程覆盖同一 ID 时，调用方需协调写入顺序，不保证跨进程原子覆盖。详见[向量存储](docs/vector.md)。

当前公共调用边界：出站 HTTP 不保存上游 Cookie，空 `params` 保留 URL 查询，非空 `params` 替换原查询，详见[出站 HTTP](docs/outbound-http.md)。向量 Collection 名称统一为 3–63 位小写字母、数字或下划线，以小写字母开头且以字母或数字结尾；本地同步操作取消会等待线程结束，Elasticsearch 批量读取的部分错误会明确失败，详见[向量存储](docs/vector.md)。

## 五分钟启动

安装依赖并复制配置：

```bash
uv sync --extra dev
cp sample.env .env
```

首次运行建议把 `.env` 中 main 数据库改为 SQLite，并让本地与部署环境都使用 Redis 缓存。切换 main 的 driver 时，必须先删除原 MySQL 的 `HOST`、`PORT`、`USERNAME`、`PASSWORD`、连接池等字段；连接配置禁止携带当前驱动不支持的额外字段。

```dotenv
TZ=Asia/Shanghai

DB_DEFAULT=main
DB_CONNECTIONS__MAIN__DRIVER=sqlite
DB_CONNECTIONS__MAIN__DATABASE=data/database.sqlite
DB_CONNECTIONS__MAIN__ECHO=false
DB_CONNECTIONS__MAIN__SLOW_QUERY_MS=500

CACHE_DEFAULT=session
CACHE_NAMESPACE=fast-api-scaff
CACHE_DEFAULT_TTL=300
CACHE_CONNECTIONS__SESSION__DRIVER=redis
CACHE_CONNECTIONS__SESSION__HOST=127.0.0.1
CACHE_CONNECTIONS__SESSION__PORT=6379
CACHE_CONNECTIONS__SESSION__DATABASE=0
CACHE_CONNECTIONS__SESSION__KEY_PREFIX=session

AUTH_LOGIN_LIMIT_CACHE=session
AUTH_LOGIN_MAX_FAILURES=5
AUTH_LOGIN_FAILURE_WINDOW_SECONDS=300
AUTH_LOGIN_LOCK_SECONDS=900
```

执行迁移并启动：

```bash
uv run alembic -c database/main/alembic.ini upgrade head
uv run uvicorn app.main:app --reload
```

验证：

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/v1/users \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"password123"}'
curl 'http://127.0.0.1:8000/api/v1/users?page=1&limit=20'
```

CORS 预检由跨域中间件直接处理，不生成 Request ID 或应用访问日志；普通请求的错误响应同样按来源执行 CORS 规则。

`/health` 不主动访问数据库或远程缓存。用户接口成功才表示 `main` 数据库配置、迁移和实际查询链路可用。

## Console

```bash
uv run python -m app.console --help
uv run python -m app.console app info
uv run python -m app.console queue jobs
uv run python -m app.console users create \
  --username alice \
  --email alice@example.com
uv run python -m app.console users list --page 1 --limit 20
```

`users create` 会交互式读取并确认密码，输入不回显。每次 Console 调用通过与 HTTP 相同的生成器创建 32 位 UUID4 十六进制 `command_id`，并自动作为当前 `correlation_id` 附加到调用链日志和新发布的队列消息；命令结果写 stdout，日志和错误写 stderr，结果 JSON 不额外包裹该 ID。退出码 0/1/2 分别表示成功、运行失败和用法错误。

## 登录示例

会话表迁移已由维护者手动生成。执行迁移、创建用户后，再调用：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"password123"}'
```

将响应 `data.access_token` 放入 `Authorization: Bearer <token>`，即可访问 `GET /api/v1/auth/me`；`POST /api/v1/auth/logout` 删除该会话并返回 204。会话默认有效期为 3600 秒，可通过 `AUTH_SESSION_TTL_SECONDS` 配置。

用户名不存在、格式错误、密码错误或账户禁用时统一计为失败。未锁定时返回认证错误码 `4010011101`，正文同时提供动态文案和 `data.remaining_attempts`。`sample.env` 使用 `session` Redis 连接：同一规范化用户名 5 分钟内第 5 次失败会触发 15 分钟临时锁定，返回认证错误码 `4290011102`，正文的 `data.retry_after_seconds` 与 `Retry-After` 响应头给出剩余秒数；锁定期间不再查询数据库或执行密码哈希。成功凭据会在数据库会话提交前清除未达到阈值的失败记录；清理失败会回滚新会话并返回通用 500，不绕过限制，也不会留下未返回给调用方的有效会话。

失败计数 key 只保存规范化用户名的 SHA-256 摘要。登录限制必须选择 Redis 连接；配置成 Memcached 或其他驱动时，容器组合阶段会明确报错，且不会为通用 `CacheClient` 增加伪原子接口。对于无法取得用户哈希的未锁定请求，密码组件仍执行固定占位哈希校验，避免直接暴露账户是否存在。

认证使用独立的 `user_sessions` 表，签发时间和过期时间采用与用户资料一致的本地无时区 `datetime`，用户表不增加角色或认证版本字段。用户聚合使用从 1 开始递增的内部 `version` 执行乐观并发控制，陈旧写入返回 409，不把版本暴露到 HTTP DTO；数据库迁移将该字段定义为非空整数并默认初始化为 1。每次成功登录会清理已过期会话；密码重置和用户禁用会在用户写入的同一数据库事务中撤销该用户全部会话，重新启用不会恢复旧会话。详细契约见[认证](docs/authentication.md)。

## Docker

```bash
docker compose up --build
# 只启动 HTTP 应用
docker compose up --build service
```

默认命令同时启动 HTTP 应用和独立 Worker；指定 `service` 时只启动 HTTP 应用。Compose 不提供 MySQL、PostgreSQL、Redis、Kafka、RabbitMQ、Memcached、Milvus、Chroma Server 或 Elasticsearch。容器内 `127.0.0.1` 指向容器自身；应用可以使用 SQLite、Milvus Lite 或 Chroma 本地持久化，但缓存必须配置容器可访问的 Redis 或 Memcached，队列 Worker 必须配置容器可访问的 Redis、Kafka 或 RabbitMQ 地址。Compose 使用 Uvicorn reload，仅适合本地开发。

Worker 复用应用镜像、`.env` 和网络且不暴露端口。镜像本身不声明健康检查，Compose 只为 HTTP 服务配置 `/health` 检测。脚手架内置登录成功日志 Job；Worker 启动时自动发现 `app/**/jobs.py` 与 `app/**/jobs/**/*.py` 中直接定义的具体 QueueJob，校验后建立不可变任务目录，不需要在组合根逐项注册。Worker 持有与 HTTP、Console 同样完整且按需初始化的应用容器，Job 可以使用已装配的数据库、缓存、HTTP、队列和向量能力；Application/Domain 仍只接收明确的窄依赖。

生产镜像以 UID/GID 1000 的非 root 用户运行。镜像中的应用代码和虚拟环境由 root 持有，运行用户只对 `storage/data`、`storage/logs` 和自己的 home 目录拥有写权限。Compose 会把项目目录挂载到 `/app`；若使用 SQLite、Milvus Lite 或 Chroma 本地持久化，请确保宿主机对应目录允许该用户写入。本地向量模式只用于单进程开发和小规模数据，不要让 HTTP 多 worker、HTTP 与 Worker 或多个容器共享同一路径。需要适配其他运行平台时，可通过 `APP_UID`、`APP_GID` 构建参数覆盖镜像用户。

## 文档

- [完整手册导航](docs/index.md)
- [快速开始](docs/getting-started.md)
- [配置参考](docs/configuration.md)
- [HTTP 接口](docs/http.md)
- [认证](docs/authentication.md)
- [Console 命令](docs/console.md)
- [队列](docs/queue.md)
- [独立 Worker](docs/worker.md)
- [数据库](docs/database.md)
- [缓存](docs/cache.md)
- [向量存储](docs/vector.md)
- [HTTP 出站请求](docs/outbound-http.md)
- [日志](docs/logging.md)
- [架构说明](docs/architecture.md)
- [开发与质量](docs/development.md)
- [故障排查](docs/troubleshooting.md)

配置时以 [`sample.env`](sample.env) 为可复制模板，以[配置参考](docs/configuration.md)解释字段、默认值和校验时机。

## 开发验证

```bash
uv run python -m pytest -q
uv run ruff check app tests database
uv run ruff format --check app tests database
uv run ty check app tests database
git diff --check
```

GitHub Actions 还会在 MySQL 和 PostgreSQL 上执行迁移往返验证。HTTPX2/httpcore2 由 `uv.lock` 固定到当前已验证版本；升级时必须运行出站 HTTP 取消测试和全量质量检查。

修改公开配置、入口、依赖、目录或调用方式时，必须同步 README、专题文档和 `sample.env`；文档只能描述已经实现并验证的能力。

## 队列与独立 Worker

```bash
uv run python -m app.worker --help
uv run python -m app.worker
# 只在需要隔离连接或逻辑队列时显式覆盖
uv run python -m app.worker --connection redis --queue reports --concurrency 4
docker compose up --build worker
```

内置 `LoginSucceededJob` 由登录接口尽力投递到默认连接配置的默认队列（`sample.env` 为 `default`），消息以 `user_id` 参数标识登录用户，不包含用户名、密码或 Token；HTTP request ID 由运行时上下文自动作为 correlation ID 写入消息。Worker 收到后通过 `context.container.users.service.get(user_id)` 查询执行时的最新用户数据，证明 Job 可以经应用服务使用数据库，并只记录固定文案、结构化用户 ID 和状态，不把用户名或邮箱写入日志。用户在消费前已删除时记录稳定警告并结束；数据库连接池超时、断连和驱动明确标记的失效连接按现有策略重试；其他数据库错误直接进入失败存储。每条消息获得不可变 `JobExecutionContext`，其中既有当前配置和正在运行的 `ApplicationContainer`，也有任务、队列和关联元数据；Job 可以像 Console operation 一样选择已装配的应用服务以及数据库、缓存、HTTP、队列和向量能力。业务 Job 应优先调用应用服务，不把容器继续传入 Application/Domain。新增任务放入带独立 `jobs` 路径段的模块即可，无需修改组合根；Worker 在开始消费前完成发现、导入和契约校验，具体规则见[QueueJob 自动发现](docs/queue.md#2-queuejob-与自动发现)。HTTP 与 Console 负责发布，独立 Worker 通过 Redis、Kafka 或 RabbitMQ 消费。

失败任务固定使用 SQL 存储，需配置 QUEUE_FAILED__DATABASE 并执行对应 Alembic migration。外部适配器目前由模拟客户端测试覆盖，未进行真实 Redis/Kafka/RabbitMQ 服务集成验证。重试是投递内重试，不包含持久延迟调度或 exactly-once 保证。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
